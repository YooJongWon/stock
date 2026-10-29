from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf


NEW_YORK = ZoneInfo("America/New_York")
REVENUE_ROW_NAMES = (
    "Total Revenue",
    "Operating Revenue",
    "Revenue",
    "Revenues",
    "Sales Revenue",
)


def current_market_date() -> date:
    """Use the US listing market's calendar date, not the runner's UTC date."""
    return datetime.now(NEW_YORK).date()


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
        # the requested session is the current New York calendar date.
        # GitHub Actions runs in UTC, so date.today() can be one day ahead of
        # the US market date during the intended evening ET run.
        ref = date.fromisoformat(str(reference_date)[:10])
        if current_market_date() != ref:
            raise ValueError(
                "Yahoo fundamentals lack point-in-time filing dates; fallback withheld "
                "because reference date is not the current New York market date"
            )

        asset = yf.Ticker(ticker)
        try:
            info = asset.get_info()
        except AttributeError:
            info = asset.info
        if not isinstance(info, dict):
            raise ValueError("Yahoo fundamentals info payload is empty")

        cap = info.get("marketCap")
        pe = info.get("trailingPE")
        roe = info.get("returnOnEquity")
        growth = None
        growth_periods = None
        statement_error = None

        try:
            statement = asset.income_stmt
            growth, growth_periods = _five_year_revenue_cagr(statement, ref)
        except Exception as exc:
            statement_error = f"{type(exc).__name__}: {exc}"

        if cap is None or pe is None or roe is None:
            missing = [
                name for name, value in (
                    ("marketCap", cap), ("trailingPE", pe), ("returnOnEquity", roe)
                ) if value is None
            ]
            raise ValueError("Yahoo fundamentals missing required values: " + ", ".join(missing))

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
