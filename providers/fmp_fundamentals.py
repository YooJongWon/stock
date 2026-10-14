from __future__ import annotations

from datetime import date
import logging
import requests

from config import SETTINGS
from utils.cache import JsonCache
from utils.rate_limiter import RateLimiter

LOG = logging.getLogger(__name__)


class FMPPlanAccessError(RuntimeError):
    pass


class FMPFundamentalProvider:
    """Point-in-time fundamentals from FMP standardized statements."""

    name = "FMP"
    base_url = "https://financialmodelingprep.com/stable"
    cache_ttl_seconds = 3 * 24 * 60 * 60

    def __init__(self, api_key=None, cache=None, session=None, limiter=None):
        self.api_key = (api_key if api_key is not None else SETTINGS.fmp_api_key).strip()
        self.cache = cache or JsonCache(SETTINGS.cache_dir / "fmp")
        self.session = session or requests.Session()
        self.limiter = limiter or RateLimiter(1.0)
        self.disabled_reason = None
        self.blocked_queries = set()
        self.api_request_count = 0

    @property
    def configured(self):
        return bool(self.api_key)

    def _get_statements(self, endpoint, ticker, period, limit):
        cache_key = f"{endpoint}:{ticker.upper()}:{period}:{limit}"
        cached = self.cache.get("statements", cache_key, self.cache_ttl_seconds)
        if cached is not None:
            return cached
        query_key = f"{endpoint}:{period}"
        if query_key in self.blocked_queries:
            raise FMPPlanAccessError(f"FMP endpoint is unavailable for this key/plan: {endpoint} ({period})")
        if self.disabled_reason:
            raise RuntimeError(self.disabled_reason)

        self.limiter.wait()
        self.api_request_count += 1
        try:
            response = self.session.get(
                f"{self.base_url}/{endpoint}",
                params={"symbol": ticker, "period": period, "limit": limit, "apikey": self.api_key},
                timeout=30,
            )
        except requests.RequestException as exc:
            message = str(exc).replace(self.api_key, "[redacted]")
            raise RuntimeError(f"FMP request failed for {endpoint}: {message}") from None

        if response.status_code in (402, 403):
            self.blocked_queries.add(query_key)
            detail = response.text[:500].replace(self.api_key, "[redacted]").replace("\r", " ").replace("\n", " ")
            raise FMPPlanAccessError(f"FMP API key/plan denied {endpoint} ({period}) (HTTP {response.status_code}): {detail}")
        if response.status_code in (401, 429):
            reason = {401: "API key invalid or missing", 429: "rate/daily request limit reached"}[response.status_code]
            self.disabled_reason = f"FMP {reason} (HTTP {response.status_code}); cached results remain available"
            raise RuntimeError(self.disabled_reason)
        if not response.ok:
            raise RuntimeError(f"FMP HTTP {response.status_code} for {endpoint}")
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError(f"FMP returned invalid JSON for {endpoint}") from None
        if isinstance(payload, dict):
            detail = payload.get("Error Message") or payload.get("message") or payload.get("error")
            if detail:
                detail = str(detail).replace(self.api_key, "[redacted]")
                if any(token in detail.lower() for token in ("upgrade", "subscription", "plan", "api key", "access denied")):
                    self.blocked_queries.add(query_key)
                    raise FMPPlanAccessError(f"FMP access unavailable for this key/plan: {detail[:180]}")
                raise RuntimeError(f"FMP {endpoint}: {detail[:240]}")
            raise RuntimeError(f"FMP returned an unexpected response for {endpoint}")
        if not isinstance(payload, list) or not payload:
            if period == "quarter":
                self.blocked_queries.add(query_key)
                raise FMPPlanAccessError(f"FMP returned no quarterly data for {ticker}; trying annual statements")
            raise RuntimeError(f"FMP returned no {period} statements for {ticker}")
        self.cache.set("statements", cache_key, payload)
        return payload

    @staticmethod
    def _as_date(value):
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @classmethod
    def _filed_rows(cls, rows, reference_date):
        usable = []
        for row in rows:
            filed = cls._as_date(row.get("filingDate") or row.get("acceptedDate"))
            period_end = cls._as_date(row.get("date"))
            # Do not use rows without a publication date: period end alone can leak future filings.
            if filed is None or period_end is None or filed > reference_date or period_end > reference_date:
                continue
            usable.append({**row, "_filed": filed, "_date": period_end})
        return usable

    @staticmethod
    def _dedupe_periods(rows):
        by_period = {}
        for row in rows:
            key = (str(row.get("fiscalYear", "")), str(row.get("period", "")).upper(), row["_date"])
            old = by_period.get(key)
            if old is None or row["_filed"] > old["_filed"]:
                by_period[key] = row
        return sorted(by_period.values(), key=lambda item: item["_date"])

    @staticmethod
    def _number(row, *keys):
        for key in keys:
            value = row.get(key)
            try:
                if value is not None:
                    return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def get_fundamentals(self, ticker, reference_date, price):
        if not self.configured:
            raise RuntimeError("FMP_API_KEY is not set in the project's .env file")
        ref = date.fromisoformat(str(reference_date)[:10])
        try:
            income_raw = self._get_statements("income-statement", ticker, "quarter", 32)
            balance_raw = self._get_statements("balance-sheet-statement", ticker, "quarter", 32)
            return self._from_quarterly(ticker, ref, price, income_raw, balance_raw)
        except FMPPlanAccessError:
            # FMP's free tier may expose annual statements while restricting quarterly endpoints.
            income_raw = self._get_statements("income-statement", ticker, "annual", 8)
            balance_raw = self._get_statements("balance-sheet-statement", ticker, "annual", 8)
            return self._from_annual(ticker, ref, price, income_raw, balance_raw)

    def _from_quarterly(self, ticker, ref, price, income_raw, balance_raw):
        # Quarterly statements supply TTM earnings, reported shares, equity and enough
        # complete fiscal years to derive a five-year sales CAGR in two API calls.
        income = self._dedupe_periods(self._filed_rows(income_raw, ref))
        balance = self._dedupe_periods(self._filed_rows(balance_raw, ref))
        quarter_income = [row for row in income if str(row.get("period", "")).upper() in {"Q1", "Q2", "Q3", "Q4"}]
        quarter_income = [row for row in quarter_income if row.get("reportedCurrency") == "USD"]
        if len(quarter_income) < 4:
            raise ValueError("FMP has fewer than four usable USD quarterly income statements")

        trailing = quarter_income[-4:]
        if (trailing[-1]["_date"] - trailing[0]["_date"]).days > 430:
            raise ValueError("FMP TTM periods are not contiguous enough")
        ttm_values = [self._number(row, "netIncome", "bottomLineNetIncome") for row in trailing]
        if any(value is None for value in ttm_values):
            raise ValueError("FMP quarterly net income is incomplete")
        ttm_net_income = sum(ttm_values)
        if ttm_net_income <= 0:
            raise ValueError("FMP TTM net income is nonpositive; P/E is not meaningful")

        annual_revenue = {}
        for row in quarter_income:
            period = str(row.get("period", "")).upper()
            try:
                fiscal_year = int(row.get("fiscalYear"))
            except (TypeError, ValueError):
                continue
            revenue = self._number(row, "revenue")
            if period not in {"Q1", "Q2", "Q3", "Q4"} or revenue is None:
                continue
            annual_revenue.setdefault(fiscal_year, {})[period] = revenue
        complete_years = {
            year: sum(periods.values())
            for year, periods in annual_revenue.items()
            if set(periods) == {"Q1", "Q2", "Q3", "Q4"}
        }
        years = sorted(complete_years)
        sales_growth_5y = None
        sales_period = None
        if years:
            latest_year = years[-1]
            target_year = min(years, key=lambda year: abs(year - (latest_year - 5)))
            latest_sales = complete_years[latest_year]
            base_sales = complete_years[target_year]
            elapsed_years = latest_year - target_year
            if 4 <= elapsed_years <= 6 and latest_sales > 0 and base_sales > 0:
                sales_growth_5y = (latest_sales / base_sales) ** (1 / elapsed_years) - 1
                sales_period = {"latest_fiscal_year": latest_year, "base_fiscal_year": target_year}
        if sales_growth_5y is None:
            raise ValueError("FMP lacks two complete reported fiscal years about five years apart")

        balance = [row for row in balance if row.get("reportedCurrency") == "USD"]
        equity_rows = [(row, self._number(row, "totalStockholdersEquity", "totalEquity")) for row in balance]
        equity_rows = [(row, value) for row, value in equity_rows if value is not None]
        if not equity_rows:
            raise ValueError("FMP stockholders' equity is unavailable")
        latest_balance, closing_equity = max(equity_rows, key=lambda item: item[0]["_date"])
        opening_candidates = [(row, value) for row, value in equity_rows if row["_date"] < trailing[0]["_date"]]
        if not opening_candidates:
            raise ValueError("FMP opening stockholders' equity for TTM ROE is unavailable")
        _, opening_equity = max(opening_candidates, key=lambda item: item[0]["_date"])
        if opening_equity <= 0 or closing_equity <= 0:
            raise ValueError("FMP average stockholders' equity is nonpositive")
        roe = ttm_net_income / ((opening_equity + closing_equity) / 2)

        share_row = max(quarter_income, key=lambda row: row["_date"])
        shares = self._number(share_row, "weightedAverageShsOutDil", "weightedAverageShsOut")
        if not shares or not price or price <= 0:
            raise ValueError("FMP diluted weighted-average shares unavailable for market cap")
        market_cap = float(price) * shares
        return {
            "market_cap": market_cap,
            "pe": market_cap / ttm_net_income,
            "roe": roe,
            "sales_growth_5y": sales_growth_5y,
            "fundamental_source": "FMP",
            "fundamental_quality": "HIGH",
            "fundamental_basis": "TTM quarterly statements",
            "market_cap_source": "FMP weighted-average diluted shares x reference price",
            "ttm_net_income": ttm_net_income,
            "ttm_period_end": str(trailing[-1]["_date"]),
            "filing_date": str(max(row["_filed"] for row in trailing)),
            "equity_period_end": str(latest_balance["_date"]),
            "sales_growth_periods": sales_period,
        }

    def _from_annual(self, ticker, ref, price, income_raw, balance_raw):
        income = [row for row in self._dedupe_periods(self._filed_rows(income_raw, ref))
                  if str(row.get("period", "")).upper() in {"FY", "ANNUAL"}
                  and row.get("reportedCurrency") == "USD"]
        balance = [row for row in self._dedupe_periods(self._filed_rows(balance_raw, ref))
                   if str(row.get("period", "")).upper() in {"FY", "ANNUAL"}
                   and row.get("reportedCurrency") == "USD"]
        if not income or len(balance) < 2:
            raise ValueError("FMP annual statements lack the latest income or two balance periods")
        latest_income = max(income, key=lambda row: row["_date"])
        if (ref - latest_income["_filed"]).days > 550:
            raise ValueError("FMP latest annual filing is stale (over 550 days old)")
        latest_net_income = self._number(latest_income, "netIncome", "bottomLineNetIncome")
        if latest_net_income is None or latest_net_income <= 0:
            raise ValueError("FMP latest annual net income is nonpositive or unavailable")

        annual_revenue = {}
        for row in income:
            revenue = self._number(row, "revenue")
            try:
                fiscal_year = int(row.get("fiscalYear"))
            except (TypeError, ValueError):
                fiscal_year = row["_date"].year
            if revenue is not None:
                annual_revenue[fiscal_year] = revenue
        years = sorted(annual_revenue)
        sales_growth_5y = None
        sales_period = None
        if years:
            latest_year = years[-1]
            target_year = min(years, key=lambda year: abs(year - (latest_year - 5)))
            latest_sales, base_sales = annual_revenue[latest_year], annual_revenue[target_year]
            elapsed_years = latest_year - target_year
            if 4 <= elapsed_years <= 6 and latest_sales > 0 and base_sales > 0:
                sales_growth_5y = (latest_sales / base_sales) ** (1 / elapsed_years) - 1
                sales_period = {"latest_fiscal_year": latest_year, "base_fiscal_year": target_year}
        if sales_growth_5y is None:
            raise ValueError("FMP annual statements do not cover a five-year sales CAGR")

        balance.sort(key=lambda row: row["_date"])
        latest_balance = balance[-1]
        prior_balance = next((row for row in reversed(balance[:-1]) if row["_date"] < latest_balance["_date"]), None)
        closing_equity = self._number(latest_balance, "totalStockholdersEquity", "totalEquity")
        opening_equity = self._number(prior_balance or {}, "totalStockholdersEquity", "totalEquity")
        if not opening_equity or not closing_equity or opening_equity <= 0 or closing_equity <= 0:
            raise ValueError("FMP annual stockholders' equity unavailable for ROE")
        roe = latest_net_income / ((opening_equity + closing_equity) / 2)

        shares = self._number(latest_income, "weightedAverageShsOutDil", "weightedAverageShsOut")
        if not shares or not price or price <= 0:
            raise ValueError("FMP annual diluted weighted-average shares unavailable for market cap")
        market_cap = float(price) * shares
        return {
            "market_cap": market_cap,
            "pe": market_cap / latest_net_income,
            "roe": roe,
            "sales_growth_5y": sales_growth_5y,
            "fundamental_source": "FMP",
            "fundamental_quality": "MEDIUM",
            "fundamental_basis": "Latest filed annual statements (quarterly endpoints restricted)",
            "market_cap_source": "FMP weighted-average diluted shares x reference price",
            "annual_net_income": latest_net_income,
            "filing_date": str(latest_income["_filed"]),
            "equity_period_end": str(latest_balance["_date"]),
            "sales_growth_periods": sales_period,
        }
