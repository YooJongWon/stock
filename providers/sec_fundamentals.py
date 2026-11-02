from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
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
REVENUE_TAGS = REVENUE_TAGS + (
    "Revenue",
    "RevenueFromContractsWithCustomers",
    "RevenueFromSaleOfGoods",
    "RevenueFromRenderingOfServices",
    "SalesRevenue",
    "NetSales",
    "OperatingRevenue",
    "InterestRevenueExpenseNonoperatingNet",
)
NET_INCOME_TAGS = NET_INCOME_TAGS + (
    "ProfitLossFromContinuingOperations",
    "ProfitLossAttributableToOwnersOfParent",
    "ProfitLossAttributableToNoncontrollingInterests",
)
EQUITY_TAGS = EQUITY_TAGS + (
    "TotalEquity",
    "EquityAttributableToOwnersOfParent",
    "EquityAttributableToOwnersOfTheParent",
    "TotalShareholdersEquity",
)
ASSETS_TAGS = ("Assets", "AssetsTotal")
LIABILITIES_TAGS = ("Liabilities", "LiabilitiesTotal")


class _InlineXBRLParser(HTMLParser):
    """Extract unsegmented Inline XBRL numeric facts and their reporting contexts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.contexts = {}
        self.facts = []
        self._context = None
        self._context_depth = 0
        self._context_field = None
        self._context_text = []
        self._fact = None
        self._fact_depth = 0
        self._exclude_depth = 0

    @staticmethod
    def _local(name):
        return str(name or "").split(":")[-1].lower()

    def handle_starttag(self, tag, attrs):
        local = self._local(tag)
        values = {str(key).lower(): value for key, value in attrs}

        if self._fact is not None:
            self._fact_depth += 1
            if local == "exclude":
                self._exclude_depth += 1
            return

        if self._context is not None:
            self._context_depth += 1
            if local == "segment":
                self._context["segmented"] = True
            elif local in ("startdate", "enddate", "instant"):
                self._context_field = local
                self._context_text = []
            return

        if local == "context":
            context_id = values.get("id")
            if context_id:
                self._context = {"id": context_id, "segmented": False}
                self._context_depth = 1
            return

        if local == "nonfraction":
            self._fact = {
                "name": values.get("name"),
                "context_ref": values.get("contextref"),
                "unit_ref": values.get("unitref"),
                "scale": values.get("scale", "0"),
                "sign": values.get("sign"),
                "format": values.get("format"),
                "nil": values.get("xsi:nil") or values.get("nil"),
                "text": [],
            }
            self._fact_depth = 1
            self._exclude_depth = 0

    def handle_endtag(self, tag):
        local = self._local(tag)
        if self._fact is not None:
            if local == "exclude" and self._exclude_depth:
                self._exclude_depth -= 1
            self._fact_depth -= 1
            if self._fact_depth <= 0:
                self.facts.append(self._fact)
                self._fact = None
                self._fact_depth = 0
                self._exclude_depth = 0
            return

        if self._context is not None:
            if local in ("startdate", "enddate", "instant") and self._context_field == local:
                self._context[local] = "".join(self._context_text).strip()
                self._context_field = None
                self._context_text = []
            self._context_depth -= 1
            if self._context_depth <= 0:
                self.contexts[self._context["id"]] = self._context
                self._context = None
                self._context_depth = 0

    def handle_data(self, data):
        if self._fact is not None:
            if self._exclude_depth == 0:
                self._fact["text"].append(data)
        elif self._context is not None and self._context_field:
            self._context_text.append(data)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


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
    def _inline_number(raw, scale="0", sign=None, format_name=None):
        value = "".join(str(raw or "").replace("\u00a0", " ").split()).replace("$", "")
        if not value or value in {"—", "-", "–"}:
            return None
        negative_parentheses = value.startswith("(") and value.endswith(")")
        if negative_parentheses:
            value = value[1:-1]
        value = value.replace("−", "-")
        number_format = str(format_name or "").split(":")[-1].lower()
        if "comma-decimal" in number_format or "numcommadecimal" in number_format:
            value = value.replace(".", "").replace(",", ".")
        else:
            value = value.replace(",", "")
        try:
            number = Decimal(value)
            number *= Decimal(10) ** int(scale or 0)
        except (InvalidOperation, ValueError, OverflowError):
            return None
        if negative_parentheses or str(sign or "") == "-":
            number = -abs(number)
        try:
            return float(number)
        except (ValueError, OverflowError):
            return None

    def _get_text(self, url, cache_key, ttl=31536000):
        hit = self.cache.get("filings", cache_key, ttl)
        if isinstance(hit, str) and hit:
            return hit
        if "example.com" in self.user_agent:
            raise RuntimeError("Set SEC_USER_AGENT to a descriptive app name and contact email in .env")
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "text/html,application/xhtml+xml",
        }
        for attempt in range(4):
            self.limiter.wait()
            try:
                response = self.session.get(url, headers=headers, timeout=35)
                response.raise_for_status()
                body = response.text
                if not body or len(body) < 1000:
                    raise ValueError("SEC filing document was empty or unexpectedly short")
                self.cache.set("filings", cache_key, body)
                return body
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                retryable = (
                    isinstance(exc, (requests.Timeout, requests.ConnectionError))
                    or status in (429, 500, 502, 503, 504)
                )
                if not retryable or attempt >= 3:
                    raise
                time.sleep(2 ** attempt)
        raise RuntimeError("SEC filing document request exhausted retry attempts")

    @staticmethod
    def _extension_kind(tag, kind):
        local = str(tag or "").split(":")[-1].lower()
        if kind == "revenue":
            blocked = ("cost", "expense", "tax", "receivable", "deferred", "backlog", "order", "discount", "allowance")
            return ("revenue" in local or local.startswith("sales") or local.endswith("sales")) and not any(x in local for x in blocked)
        if kind == "equity":
            blocked = ("method", "investment", "compensation", "sharebased", "option", "security", "instrument")
            return ("equity" in local or "capital" in local) and not any(x in local for x in blocked)
        if kind == "shares":
            return ("sharesoutstanding" in local or "commonsharesoutstanding" in local) and not any(
                x in local for x in ("weightedaverage", "diluted", "basic")
            )
        return False

    def _inline_records_from_filing(self, cik, accession, primary_document, filing_date, form, ref):
        accession_plain = str(accession).replace("-", "")
        cik_number = str(int(str(cik)))
        url = (
            f"https://www.sec.gov/Archives/edgar/data/{cik_number}/"
            f"{accession_plain}/{primary_document}"
        )
        body = self._get_text(url, f"{cik_number}:{accession_plain}:{primary_document}")
        parser = _InlineXBRLParser()
        parser.feed(body)
        filed = date.fromisoformat(str(filing_date)[:10])
        records = []
        for fact in parser.facts:
            name = str(fact.get("name") or "")
            prefix = name.split(":")[0].lower() if ":" in name else ""
            if prefix in ("us-gaap", "dei", "ifrs-full", "srt"):
                continue
            if fact.get("nil") in ("true", "1"):
                continue
            context = parser.contexts.get(fact.get("context_ref"))
            if not context or context.get("segmented"):
                continue
            end_text = context.get("instant") or context.get("enddate")
            start_text = context.get("startdate")
            try:
                end = date.fromisoformat(str(end_text)[:10])
                start = date.fromisoformat(str(start_text)[:10]) if start_text else None
            except (TypeError, ValueError):
                continue
            if filed > ref or end > ref or (start and start > ref):
                continue
            value = self._inline_number(
                "".join(fact.get("text") or []), fact.get("scale"),
                fact.get("sign"), fact.get("format"),
            )
            if value is None:
                continue
            records.append({
                "tag": name,
                "local_tag": name.split(":")[-1],
                "start": start,
                "end": end,
                "filed": filed,
                "form": str(form).split("/")[0],
                "fy": end.year,
                "fp": "FY" if str(form).startswith(("10-K", "20-F", "40-F")) else None,
                "val": value,
                "unit": fact.get("unit_ref"),
                "context_id": fact.get("context_ref"),
                "source": "SEC Inline XBRL filing",
            })
        return records

    def _extension_records(self, cik, ref, need_revenue, need_equity, need_shares):
        """Read point-in-time Inline XBRL facts from a small, targeted set of original SEC filings."""
        if not cik:
            return {
                "revenue": [], "equity": [], "shares": [], "filings": [],
                "tags": {}, "errors": ["SEC CIK를 찾지 못해 원본 공시를 조회할 수 없습니다."],
            }

        payload = self._get_json(
            f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json",
            f"submissions:{str(cik).zfill(10)}",
            86400,
        )
        recent = ((payload.get("filings") or {}).get("recent") or {})
        accessions = recent.get("accessionNumber") or []
        filing_dates = recent.get("filingDate") or []
        forms = recent.get("form") or []
        report_dates = recent.get("reportDate") or []
        primary_docs = recent.get("primaryDocument") or []
        rows = []
        for i, accession in enumerate(accessions):
            try:
                filing_date = date.fromisoformat(filing_dates[i])
                form = str(forms[i])
                primary_doc = str(primary_docs[i] or "")
            except (IndexError, TypeError, ValueError):
                continue
            if filing_date > ref or form not in ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A"):
                continue
            report_date = None
            try:
                report_date = date.fromisoformat(report_dates[i])
            except (IndexError, TypeError, ValueError):
                pass
            if report_date and report_date > ref:
                continue
            if not primary_doc.lower().endswith((".htm", ".html", ".xhtml")):
                continue
            rows.append({
                "accession": accession,
                "filing_date": filing_date,
                "form": form.split("/")[0],
                "report_date": report_date,
                "primary_document": primary_doc,
            })
        rows.sort(key=lambda row: row["filing_date"], reverse=True)
        annual_rows = [row for row in rows if row["form"] in ("10-K", "20-F", "40-F")]
        selected = []
        if (need_equity or need_shares) and rows:
            selected.append(rows[0])
        if need_revenue and annual_rows:
            latest_annual = annual_rows[0]
            selected.append(latest_annual)
            latest_year = (latest_annual["report_date"] or latest_annual["filing_date"]).year
            older = [
                row for row in annual_rows[1:]
                if 4 <= latest_year - (row["report_date"] or row["filing_date"]).year <= 6
            ]
            if not older:
                older = [
                    row for row in annual_rows[1:]
                    if 2 <= latest_year - (row["report_date"] or row["filing_date"]).year <= 3
                ]
            if older:
                selected.append(min(
                    older,
                    key=lambda row: abs(
                        latest_year - (row["report_date"] or row["filing_date"]).year - 5
                    ),
                ))

        unique = {}
        for row in selected:
            unique[row["accession"]] = row
        extracted = []
        used_filings = []
        filing_errors = []
        for row in unique.values():
            try:
                extracted.extend(self._inline_records_from_filing(
                    cik, row["accession"], row["primary_document"],
                    row["filing_date"], row["form"], ref,
                ))
                used_filings.append({
                    "form": row["form"],
                    "filed": str(row["filing_date"]),
                    "period": str(row["report_date"]) if row["report_date"] else None,
                    "accession": row["accession"],
                })
            except Exception as exc:
                # Original companyfacts remain usable; retain the filing error for diagnostics.
                filing_errors.append(
                    f"{row['form']} filed {row['filing_date']}: {type(exc).__name__}: {exc}"
                )
                continue

        extension = {
            row["tag"] for row in extracted
            if str(row["tag"]).split(":")[0].lower() not in ("us-gaap", "dei", "ifrs-full", "srt")
        }
        revenue = [
            row for row in extracted
            if self._extension_kind(row["tag"], "revenue") and row.get("start")
        ] if need_revenue else []
        equity = [
            row for row in extracted
            if self._extension_kind(row["tag"], "equity") and not row.get("start")
        ] if need_equity else []
        shares = [
            row for row in extracted
            if self._extension_kind(row["tag"], "shares") and not row.get("start")
        ] if need_shares else []

        def best_tag(records, minimum=1):
            grouped = {}
            for row in records:
                grouped.setdefault(row["tag"], []).append(row)
            ranked = []
            for tag, items in grouped.items():
                ranked.append((len(items), tag, items))
            ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return ranked[0][2] if ranked and ranked[0][0] >= minimum else []

        revenue = best_tag(revenue, 2)
        equity = best_tag(equity, 1)
        shares = best_tag(shares, 1)
        tags = {
            "revenue": sorted({row["tag"] for row in revenue}),
            "equity": sorted({row["tag"] for row in equity}),
            "shares": sorted({row["tag"] for row in shares}),
            "extension_names_seen": sorted(extension)[:80],
        }
        return {
            "revenue": revenue,
            "equity": equity,
            "shares": shares,
            "filings": used_filings,
            "tags": tags,
            "errors": filing_errors,
        }

    @classmethod
    def _growth_from_annual_records(cls, records):
        annual = cls._annual_records(records)
        years = sorted(year for year, row in annual.items() if float(row["val"]) > 0)
        if len(years) < 2:
            return None, None
        latest_year = years[-1]
        eligible = [year for year in years[:-1] if 4 <= latest_year - year <= 6]
        if not eligible:
            eligible = [year for year in years[:-1] if 2 <= latest_year - year <= 3]
        if not eligible:
            return None, None
        base_year = min(eligible, key=lambda year: abs(year - (latest_year - 5)))
        span = latest_year - base_year
        latest = annual[latest_year]
        base = annual[base_year]
        value = (float(latest["val"]) / float(base["val"])) ** (1 / span) - 1
        return value, {
            "latest_period_end": str(latest["end"]),
            "latest_filing_date": str(latest["filed"]),
            "base_period_end": str(base["end"]),
            "base_filing_date": str(base["filed"]),
            "tag": latest.get("tag"),
            "years": span,
        }

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

        extension_info = {"filings": [], "tags": {}}
        need_extension = {
            "revenue": sales_growth is None,
            "equity": roe is None,
            "shares": market_cap is None,
        }
        if any(need_extension.values()):
            try:
                extension_info = self._extension_records(
                    cik, ref, need_extension["revenue"],
                    need_extension["equity"], need_extension["shares"],
                )
            except Exception as exc:
                extension_info = {
                    "filings": [],
                    "tags": {},
                    "error": f"{type(exc).__name__}: {exc}",
                }

            if sales_growth is None and extension_info.get("revenue"):
                extension_growth, extension_period = self._growth_from_annual_records(
                    extension_info["revenue"]
                )
                if extension_growth is not None:
                    sales_growth = extension_growth
                    sales_period = extension_period
                    revenue_records = extension_info["revenue"] + revenue_records

            if roe is None and extension_info.get("equity"):
                equity_records = extension_info["equity"] + equity_records
                equity_by_end = {}
                for row in equity_records:
                    if not row.get("start"):
                        old = equity_by_end.get(row["end"])
                        if old is None or row["filed"] > old["filed"]:
                            equity_by_end[row["end"]] = row
                equity_instants = sorted(equity_by_end.values(), key=lambda row: row["end"])
                latest_equity = equity_instants[-1] if equity_instants else None
                prior_equity = [row for row in equity_instants if row["end"] < trailing[0]["end"]]
                if not prior_equity and len(equity_instants) >= 2:
                    prior_equity = [equity_instants[-2]]
                opening_equity = prior_equity[-1]["val"] if prior_equity else (
                    latest_equity["val"] if latest_equity else None
                )
                if latest_equity is not None and opening_equity is not None:
                    if float(opening_equity) > 0 and float(latest_equity["val"]) > 0:
                        roe = ttm_net_income / (
                            (float(opening_equity) + float(latest_equity["val"])) / 2
                        )
                    elif float(latest_equity["val"]) > 0:
                        roe = ttm_net_income / float(latest_equity["val"])

            if market_cap is None and extension_info.get("shares"):
                share_records = extension_info["shares"] + share_records
                valid_shares = [row for row in share_records if not row.get("start")]
                latest_shares_record = max(
                    valid_shares,
                    key=lambda row: (row["end"], row["filed"]),
                    default=None,
                )
                latest_shares = float(latest_shares_record["val"]) if latest_shares_record else None
                if latest_shares and latest_shares > 0 and valid_price:
                    market_cap = valid_price * latest_shares
                    pe = market_cap / ttm_net_income if ttm_net_income > 0 else None

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

        field_diagnostics = {}
        if market_cap is None:
            field_diagnostics["market_cap"] = {
                "reason": "기준일까지 제출된 SEC 공시에서 시가총액 계산에 쓸 발행주식 수를 확인하지 못했습니다.",
                "attempted_tags": list(SHARES_TAGS),
                "filings_checked": extension_info.get("filings", []),
            }
        if roe is None:
            field_diagnostics["roe"] = {
                "reason": "기준일까지 확인 가능한 기초·기말 자본총계 또는 자산·부채 자료가 부족해 ROE를 계산하지 못했습니다.",
                "attempted_tags": list(EQUITY_TAGS) + list(ASSETS_TAGS) + list(LIABILITIES_TAGS),
                "filings_checked": extension_info.get("filings", []),
            }
        if sales_growth is None:
            field_diagnostics["sales_growth_5y"] = {
                "reason": "기준일까지 공개된 연간 매출에서 4~6년(가능하면 5년) 비교 구간을 찾지 못했습니다.",
                "attempted_tags": list(REVENUE_TAGS),
                "extension_tags": (extension_info.get("tags") or {}).get("extension_names_seen", []),
                "filings_checked": extension_info.get("filings", []),
            }
        extension_errors = list(extension_info.get("errors") or [])
        if extension_info.get("error"):
            extension_errors.append(extension_info["error"])
        if extension_errors:
            for detail in field_diagnostics.values():
                detail["filing_lookup_error"] = "; ".join(extension_errors)[:1200]

        if market_cap is not None and latest_shares_record is not None and extension_info.get("shares"):
            market_cap_source = "SEC Inline XBRL filing"
        else:
            market_cap_source = "SEC" if market_cap is not None else None

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
            "market_cap_source": market_cap_source,
            "tags": {
                "revenue": tag_rev, "net_income": tag_ni,
                "equity": tag_eq, "shares": tag_shares,
                "inline_extension": (extension_info.get("tags") or {}),
            },
            "field_diagnostics": field_diagnostics,
            "extension_filings": extension_info.get("filings", []),
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
