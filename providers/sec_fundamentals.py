from __future__ import annotations

from datetime import date
import time

import requests

from config import SETTINGS
from utils.cache import JsonCache
from utils.rate_limiter import RateLimiter


REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueServicesNet",
    "SalesRevenueGoodsNet",
    "OperatingRevenues",
    "RevenuesNetOfInterestExpense",
    "TotalRevenuesAndOtherIncome",
    "InterestAndDividendIncomeOperating",
    "RealEstateRevenueNet",
)
NET_INCOME_TAGS = (
    "NetIncomeLoss",
    "ProfitLoss",
    "NetIncomeLossAttributableToParent",
    "NetIncomeLossAvailableToCommonStockholdersBasic",
    "IncomeLossFromContinuingOperations",
)
EQUITY_TAGS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "StockholdersEquityIncludingPortionAttributableToParent",
    "PartnersCapital",
    "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest",
    "CommonStockholdersEquity",
    "MembersEquity",
)
ASSETS_TAGS = ("Assets",)
LIABILITIES_TAGS = ("Liabilities",)
SHARES_TAGS = (
    "EntityCommonStockSharesOutstanding",
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
)


class SECFundamentalProvider:
    name = "SEC"

    def __init__(self, user_agent=None, cache=None, session=None, limiter=None):
        self.user_agent = user_agent or SETTINGS.sec_user_agent
        self.cache = cache or JsonCache(SETTINGS.cache_dir / "sec")
        self.session = session or requests.Session()
        self.limiter = limiter or RateLimiter(SETTINGS.sec_requests_per_second)

    def _get_json(self, url, cache_key, ttl):
        hit = self.cache.get("facts", cache_key, ttl)
        if hit is not None:
            return hit
        if "example.com" in self.user_agent:
            raise RuntimeError("Set SEC_USER_AGENT to a descriptive app name and contact email in .env")

        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }
        for attempt in range(4):
            self.limiter.wait()
            try:
                response = self.session.get(url, headers=headers, timeout=25)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("SEC companyfacts response was not a JSON object")
                self.cache.set("facts", cache_key, data)
                return data
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = (
                    isinstance(exc, (requests.Timeout, requests.ConnectionError))
                    or status in (429, 500, 502, 503, 504)
                )
                if not retryable or attempt >= 3:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("SEC companyfacts request exhausted retry attempts")

    @staticmethod
    def _records(fact, ref):
        """Return filing-dated facts that were both filed and effective by the as-of date."""
        if not fact:
            return []
        out = []
        for unit, items in fact.get("units", {}).items():
            unit_records = []
            for item in items:
                try:
                    filed = date.fromisoformat(item["filed"])
                    end = date.fromisoformat(item["end"])
                    form = item.get("form", "")
                    if (
                        filed <= ref
                        and end <= ref
                        and form in ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A")
                    ):
                        norm_form = form.split("/")[0]
                        unit_records.append({**item, "form": norm_form, "filed": filed, "end": end, "unit": unit})
                except (ValueError, KeyError, TypeError):
                    continue
            if unit_records:
                out.extend(unit_records)
                break
        return out

    @classmethod
    def _merged_records(cls, facts, tags, ref):
        """Merge records across all matching tags so tag transitions don't break multi-year history."""
        merged = []
        for namespace in ("us-gaap", "dei", "ifrs-full"):
            namespace_facts = facts.get(namespace, {})
            for tag in tags:
                fact = namespace_facts.get(tag)
                if fact:
                    merged.extend(cls._records(fact, ref))
        return merged

    @staticmethod
    def _quarters(records):
        """Extract discrete quarters from duration facts; YTD values are differenced within FY."""
        normalized = []
        for item in records:
            try:
                row = dict(item)
                if isinstance(row.get("end"), str):
                    row["end"] = date.fromisoformat(row["end"])
                if isinstance(row.get("filed"), str):
                    row["filed"] = date.fromisoformat(row["filed"])
                if isinstance(row.get("start"), str):
                    row["start_date"] = date.fromisoformat(row["start"])
                else:
                    row["start_date"] = row.get("start")
                normalized.append(row)
            except (ValueError, TypeError):
                continue

        durations = [
            row for row in normalized
            if row.get("start_date")
            and 70 <= (row["end"] - row["start_date"]).days <= 380
        ]
        candidates = []
        for row in durations:
            days = (row["end"] - row["start_date"]).days
            if 70 <= days <= 110:
                candidates.append({**row, "quarter_value": float(row["val"])})
            elif 150 <= days <= 290 and row.get("fp") in ("Q2", "Q3"):
                year_q1 = [
                    item for item in durations
                    if item.get("fy") == row.get("fy")
                    and item.get("fp") == "Q1"
                    and item["end"] < row["end"]
                    and 70 <= (item["end"] - item["start_date"]).days <= 110
                ]
                if year_q1:
                    previous = max(year_q1, key=lambda item: item["end"])
                    candidates.append({
                        **row,
                        "quarter_value": float(row["val"]) - float(previous["val"]),
                    })
            elif 240 <= days <= 380 and row.get("fp") == "FY":
                prior_q3 = [
                    item for item in durations
                    if item.get("fy") == row.get("fy")
                    and item.get("fp") == "Q3"
                    and item["end"] < row["end"]
                ]
                if prior_q3:
                    previous = max(prior_q3, key=lambda item: item["end"])
                    candidates.append({
                        **row,
                        "quarter_value": float(row["val"]) - float(previous["val"]),
                    })

        by_end = {}
        for quarter in candidates:
            old = by_end.get(quarter["end"])
            if old is None or quarter["filed"] > old["filed"]:
                by_end[quarter["end"]] = quarter

        ordered = sorted(by_end.values(), key=lambda row: row["end"])
        for index, item in enumerate(ordered):
            if index and 70 <= (item["end"] - ordered[index - 1]["end"]).days <= 110:
                item["period_start"] = date.fromordinal(ordered[index - 1]["end"].toordinal() + 1)
            elif item.get("start_date"):
                item["period_start"] = item["start_date"]
        return ordered

    @classmethod
    def _best_fact(cls, facts, tags, ref, kind):
        """Select the tag with the most usable history instead of the first tag present."""
        best = None
        for namespace in ("us-gaap", "dei", "ifrs-full"):
            namespace_facts = facts.get(namespace, {})
            for priority, tag in enumerate(tags):
                fact = namespace_facts.get(tag)
                records = cls._records(fact, ref)
                if not records:
                    continue

                if kind == "quarters":
                    useful = len(cls._quarters(records))
                elif kind == "annual":
                    useful = sum(
                        1 for row in records
                        if row.get("start")
                        and 330 <= (
                            row["end"] - (
                                date.fromisoformat(row["start"])
                                if isinstance(row["start"], str) else row["start"]
                            )
                        ).days <= 400
                        and row.get("form") in ("10-K", "20-F", "40-F")
                    )
                elif kind == "instant":
                    useful = sum(1 for row in records if not row.get("start"))
                else:
                    useful = len(records)

                candidate = ((useful, len(records), -priority), tag, fact)
                if best is None or candidate[0] > best[0]:
                    best = candidate
        if best is None or best[0][0] == 0:
            return None, None
        return best[1], best[2]

    @staticmethod
    def _annual_records(records):
        annual = {}
        for row in records:
            start = row.get("start")
            if not start or row.get("form") not in ("10-K", "20-F", "40-F"):
                continue
            try:
                start_date = date.fromisoformat(start) if isinstance(start, str) else start
                days = (row["end"] - start_date).days
            except (TypeError, ValueError, KeyError):
                continue
            if 330 <= days <= 400:
                old = annual.get(row["end"].year)
                if old is None or row["filed"] > old["filed"]:
                    annual[row["end"].year] = row
        return annual

    def get_fundamentals(self, cik, reference_date, price):
        ref = date.fromisoformat(str(reference_date)[:10])
        cik = str(cik).zfill(10)
        facts_payload = self._get_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", cik, 86400
        )
        facts = facts_payload.get("facts", {})

        tag_rev, rev_obj = self._best_fact(facts, REVENUE_TAGS, ref, "annual")
        tag_ni, ni_obj = self._best_fact(facts, NET_INCOME_TAGS, ref, "quarters")
        tag_eq, eq_obj = self._best_fact(facts, EQUITY_TAGS, ref, "instant")
        tag_shares, shares_obj = self._best_fact(facts, SHARES_TAGS, ref, "instant")

        # Use primary tag records first, supplemented by merged records across all candidate tags
        revenue_records = self._records(rev_obj, ref) + self._merged_records(facts, REVENUE_TAGS, ref)
        net_income_records = self._records(ni_obj, ref)
        if len(self._quarters(net_income_records)) < 4:
            net_income_records = self._merged_records(facts, NET_INCOME_TAGS, ref)
        equity_records = self._records(eq_obj, ref) + self._merged_records(facts, EQUITY_TAGS, ref)
        share_records = self._records(shares_obj, ref) or self._merged_records(facts, SHARES_TAGS, ref)

        net_income_quarters = self._quarters(net_income_records)
        trailing = None
        ttm_net_income = None

        if len(net_income_quarters) >= 4:
            candidate_trailing = net_income_quarters[-4:]
            if (candidate_trailing[-1]["end"] - candidate_trailing[0]["end"]).days <= 430:
                trailing = candidate_trailing
                ttm_net_income = sum(row["quarter_value"] for row in trailing)

        # Fallback for 20-F/40-F foreign issuers (e.g., AER) or companies without 4 discrete quarters
        if ttm_net_income is None:
            annual_ni = self._annual_records(net_income_records)
            if annual_ni:
                latest_ni_yr = max(annual_ni)
                latest_ni_row = annual_ni[latest_ni_yr]
                ttm_net_income = float(latest_ni_row["val"])
                start_dt = (
                    date.fromisoformat(latest_ni_row["start"])
                    if isinstance(latest_ni_row.get("start"), str)
                    else latest_ni_row.get("start", latest_ni_row["end"])
                )
                trailing = [{**latest_ni_row, "period_start": start_dt, "quarter_value": ttm_net_income}]
            else:
                if len(net_income_quarters) < 4:
                    raise ValueError("SEC has fewer than four usable discrete net-income quarters")
                raise ValueError("SEC TTM periods are not contiguous enough")

        nonpositive_earnings = ttm_net_income <= 0

        # Build instant equity series; fall back to Assets - Liabilities if direct Equity tags are absent
        equity_by_end = {}
        for row in equity_records:
            if not row.get("start"):
                old = equity_by_end.get(row["end"])
                if old is None or row["filed"] > old["filed"]:
                    equity_by_end[row["end"]] = row

        if len(equity_by_end) < 2:
            asset_records = self._merged_records(facts, ASSETS_TAGS, ref)
            liab_records = self._merged_records(facts, LIABILITIES_TAGS, ref)
            assets_by_end = {r["end"]: r for r in asset_records if not r.get("start")}
            liabs_by_end = {r["end"]: r for r in liab_records if not r.get("start")}
            for end_dt in set(assets_by_end) & set(liabs_by_end):
                if end_dt not in equity_by_end:
                    a_row, l_row = assets_by_end[end_dt], liabs_by_end[end_dt]
                    equity_by_end[end_dt] = {
                        **a_row,
                        "val": float(a_row["val"]) - float(l_row["val"]),
                    }

        equity_instants = sorted(equity_by_end.values(), key=lambda row: row["end"])
        latest_equity = equity_instants[-1] if equity_instants else None
        prior_equity = [
            row for row in equity_instants
            if row["end"] < trailing[0]["end"]
        ]
        if not prior_equity and len(equity_instants) >= 2:
            prior_equity = [equity_instants[-2]]
        opening_equity = prior_equity[-1]["val"] if prior_equity else (latest_equity["val"] if latest_equity else None)

        roe = None
        if (
            latest_equity is not None
            and opening_equity is not None
            and float(opening_equity) > 0
            and float(latest_equity["val"]) > 0
        ):
            roe = ttm_net_income / (
                (float(opening_equity) + float(latest_equity["val"])) / 2
            )
        elif latest_equity is not None and float(latest_equity["val"]) > 0:
            roe = ttm_net_income / float(latest_equity["val"])

        annual_revenue = self._annual_records(revenue_records)
        years = sorted(y for y, r in annual_revenue.items() if float(r["val"]) > 0)
        sales_growth = None
        sales_period = None
        if len(years) >= 2:
            latest_year = years[-1]
            # 1st priority: 4-6 year span; 2nd priority: 3-year span fallback
            eligible_bases = [y for y in years[:-1] if 4 <= latest_year - y <= 6]
            if not eligible_bases:
                eligible_bases = [y for y in years[:-1] if 2 <= latest_year - y <= 3]
            if eligible_bases:
                base_year = min(eligible_bases, key=lambda year: abs(year - (latest_year - 5)))
                year_span = latest_year - base_year
                sales_growth = (
                    float(annual_revenue[latest_year]["val"])
                    / float(annual_revenue[base_year]["val"])
                ) ** (1 / year_span) - 1
                sales_period = {
                    "latest_period_end": str(annual_revenue[latest_year]["end"]),
                    "latest_filing_date": str(annual_revenue[latest_year]["filed"]),
                    "base_period_end": str(annual_revenue[base_year]["end"]),
                    "base_filing_date": str(annual_revenue[base_year]["filed"]),
                    "tag": tag_rev,
                }

        valid_shares = [row for row in share_records if not row.get("start")]
        if not valid_shares:
            valid_shares = share_records
        latest_shares_record = max(
            valid_shares,
            key=lambda row: (row["end"], row["filed"]),
        ) if valid_shares else None
        latest_shares = float(latest_shares_record["val"]) if latest_shares_record else None
        valid_price = float(price) if price is not None and float(price) > 0 else None
        market_cap = valid_price * latest_shares if valid_price and latest_shares and latest_shares > 0 else None
        pe = market_cap / ttm_net_income if market_cap is not None and ttm_net_income > 0 else None

        latest_revenue = max(self._quarters(revenue_records), key=lambda row: (row["end"], row["filed"]), default=None)
        latest_net_income = max(trailing, key=lambda row: (row["end"], row["filed"]))
        missing = [
            field for field, value in (
                ("market_cap", market_cap),
                ("pe", pe),
                ("roe", roe),
                ("sales_growth_5y", sales_growth),
            )
            if value is None and not (field == "pe" and nonpositive_earnings)
        ]
        if nonpositive_earnings:
            fundamental_status = "NON_POSITIVE_TTM_EARNINGS"
            rejection_reason = "TTM net income is nonpositive; P/E not meaningful"
        elif missing:
            fundamental_status = "INCOMPLETE_FIELDS"
            rejection_reason = None
        else:
            fundamental_status = "AVAILABLE"
            rejection_reason = None

        has_usable_metrics = any(value is not None for value in (market_cap, pe, roe, sales_growth))
        quality = "HIGH" if not missing and not nonpositive_earnings else "LOW" if has_usable_metrics else "UNAVAILABLE"
        warnings = []
        if market_cap is None:
            warnings.append("SEC shares outstanding unavailable; market cap cannot be calculated")
        if roe is None:
            warnings.append("SEC opening/closing stockholders equity unavailable for ROE")
        if sales_growth is None:
            warnings.append("SEC annual revenue history insufficient for a 4–6 year growth calculation")

        return {
            "market_cap": market_cap,
            "pe": pe,
            "roe": roe,
            "sales_growth_5y": sales_growth,
            "fundamental_source": "SEC",
            "fundamental_quality": quality,
            "fundamental_status": fundamental_status,
            "fundamental_rejection_reason": rejection_reason,
            "missing_fields": missing,
            "warning": "; ".join(warnings) or None,
            "market_cap_source": "SEC" if market_cap is not None else None,
            "tags": {"revenue": tag_rev, "net_income": tag_ni, "equity": tag_eq, "shares": tag_shares},
            "ttm_net_income": ttm_net_income,
            "ttm_period_end": str(trailing[-1]["end"]),
            "filing_date": str(max(row["filed"] for row in trailing)),
            "period_start": str(trailing[0].get("period_start", trailing[0]["end"])),
            "period_end": str(trailing[-1]["end"]),
            "form": latest_net_income.get("form"),
            "fundamental_basis": "SEC companyfacts; filing_date <= reference_date and period_end <= reference_date",
            "source_detail": "SEC EDGAR XBRL companyfacts",
            "equity_period_end": str(latest_equity["end"]) if latest_equity else None,
            "shares_period_end": str(latest_shares_record["end"]) if latest_shares_record else None,
            "shares_filing_date": str(latest_shares_record["filed"]) if latest_shares_record else None,
            "revenue_period_end": str(latest_revenue["end"]) if latest_revenue else None,
            "sales_growth_periods": sales_period,
        }
