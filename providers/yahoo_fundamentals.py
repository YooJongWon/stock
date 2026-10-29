from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo
import logging
import time as time_module

import pandas as pd
import yfinance as yf


NEW_YORK = ZoneInfo("America/New_York")
LOG = logging.getLogger(__name__)
REVENUE_ROW_NAMES = (
    "Total Revenue",
    "Operating Revenue",
    "Revenue",
    "Revenues",
    "Sales Revenue",
)


def current_market_date() -> date | None:
    """Return the New York date only after the regular-session close has passed."""
    now = datetime.now(NEW_YORK)
    # Yahoo has no field-level filing timestamps. Using its snapshot intraday could
    # include financial information not available at that session close.
    if (now.hour, now.minute) < (16, 30):
        return None
    return now.date()


def _five_year_revenue_cagr(statement, reference_date):
    """Use annual Yahoo revenue history only for a same-market-date snapshot.

    Yahoo's info.revenueGrowth is a one-year rate, not a five-year CAGR, so it
    must not be substituted for the screener's five-year sales-growth filter.
    """
    if statement is None or getattr(statement, "empty", True):
        return None, None

    try:
        ref = date.fromisoformat(str(reference_date)[:10])
    except ValueError:
        return None, None

    row_names = {str(index).strip().lower(): index for index in statement.index}
    for wanted in REVENUE_ROW_NAMES:
        row_index = row_names.get(wanted.lower())
        if row_index is None:
            continue

        periods = []
        row = statement.loc[row_index]
        for column, raw_value in row.items():
            try:
                period_end = pd.Timestamp(column).date()
                value = float(raw_value)
            except (TypeError, ValueError, OverflowError):
                continue
            if period_end <= ref and pd.notna(value) and value > 0:
                periods.append((period_end, value))

        periods.sort(key=lambda item: item[0])
        if len(periods) < 2:
            continue
        newest_date, newest_value = periods[-1]
        eligible = [
            item for item in periods[:-1]
            if 4 <= newest_date.year - item[0].year <= 6
        ]
        if not eligible:
            continue
        oldest_date, oldest_value = min(
            eligible,
            key=lambda item: abs((newest_date.year - item[0].year) - 5),
        )
        years = newest_date.year - oldest_date.year
        if oldest_value <= 0 or newest_value <= 0 or years <= 0:
            continue
        cagr = (newest_value / oldest_value) ** (1 / years) - 1
        return cagr, {
            "latest_period_end": str(newest_date),
            "base_period_end": str(oldest_date),
            "years": years,
            "row": str(row_index),
        }
    return None, None


class YahooFundamentalProvider:
    name = "yfinance_fallback"

    def get_fundamentals(self, ticker, reference_date, price):
        # Yahoo's info payload has no filing date per field. Only use it when
        # the requested session is today in New York and the regular session has closed.
        # GitHub Actions runs in UTC, so date.today() can be one day ahead of ET.
        ref = date.fromisoformat(str(reference_date)[:10])
        if current_market_date() != ref:
            raise ValueError(
                "Yahoo fundamentals lack point-in-time filing dates; fallback withheld "
                "because reference date is not the current New York market date"
            )

        info = None
        asset = None
        info_errors = []
        # Yahoo may respond with an empty payload while rate-limited. Recreate the
        # Ticker object per attempt because yfinance can cache a failed profile request.
        for attempt in range(4):
            try:
                asset = yf.Ticker(ticker)
                try:
                    candidate_info = asset.get_info()
                except AttributeError:
                    candidate_info = asset.info
                if isinstance(candidate_info, dict) and candidate_info:
                    info = candidate_info
                    break
                info_errors.append("Yahoo Finance returned an empty fundamentals info payload")
            except Exception as exc:
                info_errors.append(f"{type(exc).__name__}: {exc}")
                message = str(exc).lower()
                retryable = any(token in message for token in (
                    "429", "too many requests", "rate limit", "timeout", "timed out",
                    "temporarily unavailable", "502", "503", "504",
                ))
                if not retryable:
                    break
            if attempt < 3:
                delay = min(2 ** attempt, 8)
                LOG.warning("Yahoo fundamentals info retry for %s in %ss", ticker, delay)
                time_module.sleep(delay)
        if info is None or asset is None:
            raise RuntimeError("Yahoo fundamentals info lookup failed: " + " | ".join(info_errors))

        cap = info.get("marketCap")
        pe = info.get("trailingPE")
        roe = info.get("returnOnEquity")
        if cap is None or pe is None or roe is None:
            missing = [
                name for name, value in (
                    ("marketCap", cap), ("trailingPE", pe), ("returnOnEquity", roe)
                ) if value is None
            ]
            raise ValueError("Yahoo fundamentals missing required values: " + ", ".join(missing))

        growth = None
        growth_periods = None
        statement_error = None
        statement = None
        statement_errors = []
        for attempt in range(3):
            try:
                statement = asset.income_stmt
                if statement is not None and not getattr(statement, "empty", True):
                    statement_errors.clear()
                    break
                statement_errors.append("Yahoo annual income statement is empty")
            except Exception as exc:
                statement_errors.append(f"{type(exc).__name__}: {exc}")
                message = str(exc).lower()
                retryable = any(token in message for token in (
                    "429", "too many requests", "rate limit", "timeout", "timed out",
                    "temporarily unavailable", "502", "503", "504",
                ))
                if not retryable:
                    break
            if attempt < 2:
                delay = min(2 ** attempt, 4)
                LOG.warning("Yahoo annual income-statement retry for %s in %ss", ticker, delay)
                time_module.sleep(delay)
                asset = yf.Ticker(ticker)
        if statement_errors:
            statement_error = " | ".join(statement_errors)
        growth, growth_periods = _five_year_revenue_cagr(statement, ref)

        return {
            "market_cap": float(cap),
            "pe": float(pe),
            "roe": float(roe),
            "sales_growth_5y": float(growth) if growth is not None else None,
            "fundamental_source": "yfinance_fallback",
            "fundamental_quality": "MEDIUM" if growth is not None else "LOW",
            "market_cap_source": "yfinance_fallback",
            "available_date": str(ref),
            "filing_date": None,
            "sales_growth_periods": growth_periods,
            "source_detail": "Yahoo Finance snapshot; annual income-statement revenue used only when 5Y CAGR could be calculated",
            "warning": (
                "Yahoo annual income-statement data did not contain a usable 4–6 year revenue span"
                if growth is None else None
            ),
            "statement_error": statement_error,
        }
