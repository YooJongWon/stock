"""Point-in-time fundamentals: SEC first, Yahoo fallback only when dated use is permitted."""
from __future__ import annotations

import logging

from providers.sec_fundamentals import SECFundamentalProvider
from providers.yahoo_fundamentals import YahooFundamentalProvider

LOG = logging.getLogger(__name__)


class FallbackFundamentalProvider:
    def __init__(self, primary=None, fallback=None, finimpulse=None):
        self.primary = primary or SECFundamentalProvider()
        self.fallback = fallback or YahooFundamentalProvider()

    def get_fundamentals(self, ticker, cik, reference_date, price):
        errors = []
        try:
            if not cik:
                raise ValueError("SEC CIK missing for ticker")
            result = self.primary.get_fundamentals(cik, reference_date, price)
            if isinstance(result, dict) and result.get("fundamental_quality") != "UNAVAILABLE":
                return result
            errors.append(
                "SEC: provider returned unavailable/incomplete data"
                if not isinstance(result, dict)
                else str(result.get("error") or result.get("warning") or "SEC result incomplete")
            )
        except Exception as exc:
            errors.append(f"SEC: {type(exc).__name__}: {exc}")

        try:
            result = self.fallback.get_fundamentals(ticker, reference_date, price)
            if not isinstance(result, dict):
                raise ValueError("Yahoo fallback returned a non-dictionary result")
            combined_diagnostics = list(errors)
            for field in ("warning", "statement_error"):
                value = result.get(field)
                if value:
                    combined_diagnostics.append(f"Yahoo {field}: {value}")
            result_error = result.get("error")
            if result_error:
                combined_diagnostics.append(f"Yahoo: {result_error}")
            return {
                **result,
                "error": "; ".join(dict.fromkeys(combined_diagnostics)) or None,
                "fundamental_source": result.get("fundamental_source") or "yfinance_fallback",
            }
        except Exception as exc:
            errors.append(f"Yahoo: {type(exc).__name__}: {exc}")

        return {
            "market_cap": None,
            "pe": None,
            "roe": None,
            "sales_growth_5y": None,
            "fundamental_source": None,
            "fundamental_quality": "UNAVAILABLE",
            "error": "; ".join(errors),
        }
