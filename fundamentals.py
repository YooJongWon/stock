"""Point-in-time fundamentals: SEC first, and fill missing fields only with permitted Yahoo data."""
from __future__ import annotations

import logging

from providers.sec_fundamentals import SECFundamentalProvider
from providers.yahoo_fundamentals import YahooFundamentalProvider

LOG = logging.getLogger(__name__)
REQUIRED_FIELDS = ("market_cap", "pe", "roe", "sales_growth_5y")


class FallbackFundamentalProvider:
    def __init__(self, primary=None, fallback=None, finimpulse=None):
        self.primary = primary or SECFundamentalProvider()
        self.fallback = fallback or YahooFundamentalProvider()

    def get_fundamentals(self, ticker, cik, reference_date, price):
        errors = []
        primary_result = None
        try:
            if not cik:
                raise ValueError("SEC CIK missing for ticker")
            result = self.primary.get_fundamentals(cik, reference_date, price)
            if isinstance(result, dict):
                primary_result = result
                # A nonpositive TTM net income is a real financial condition, not a
                # provider outage. P/E is legitimately undefined in this case, so do
                # not try to overwrite it with an undated Yahoo snapshot.
                if result.get("fundamental_status") == "NON_POSITIVE_TTM_EARNINGS":
                    return result
                missing = [field for field in REQUIRED_FIELDS if result.get(field) is None]
                if result.get("fundamental_quality") != "UNAVAILABLE" and not missing:
                    return result
                if missing:
                    errors.append("SEC missing required fields: " + ", ".join(missing))
                else:
                    errors.append(str(result.get("error") or "SEC result marked unavailable"))
            else:
                errors.append("SEC returned an unexpected result")
        except Exception as exc:
            errors.append(f"SEC: {type(exc).__name__}: {exc}")

        try:
            yahoo = self.fallback.get_fundamentals(ticker, reference_date, price)
            if not isinstance(yahoo, dict):
                raise ValueError("Yahoo fallback returned a non-dictionary result")
            combined = dict(primary_result or {})
            yahoo_filled = []
            for field in REQUIRED_FIELDS:
                if combined.get(field) is None and yahoo.get(field) is not None:
                    combined[field] = yahoo[field]
                    yahoo_filled.append(field)

            # Preserve SEC as the primary source, but disclose when Yahoo filled a gap.
            if primary_result:
                source = "SEC+Yahoo" if yahoo_filled else "SEC"
                if yahoo_filled:
                    combined["fallback_fields"] = yahoo_filled
                    combined["fundamental_quality"] = "MEDIUM"
                    combined["source_detail"] = (
                        str(primary_result.get("source_detail") or "SEC EDGAR")
                        + "; missing fields filled from same-session Yahoo snapshot: "
                        + ", ".join(yahoo_filled)
                    )
                else:
                    combined["source_detail"] = primary_result.get("source_detail")
            else:
                source = yahoo.get("fundamental_source") or "yfinance_fallback"
                combined.update(yahoo)

            combined["fundamental_source"] = source
            diagnostics = list(errors)
            for field in ("warning", "statement_error"):
                value = yahoo.get(field)
                if value:
                    diagnostics.append(f"Yahoo {field}: {value}")
            if yahoo.get("error"):
                diagnostics.append(f"Yahoo: {yahoo['error']}")
            combined["error"] = "; ".join(dict.fromkeys(diagnostics)) or None
            missing_after_fallback = [field for field in REQUIRED_FIELDS if combined.get(field) is None]
            if missing_after_fallback:
                combined["fundamental_quality"] = "LOW" if any(
                    combined.get(field) is not None for field in REQUIRED_FIELDS
                ) else "UNAVAILABLE"
                combined["warning"] = (
                    "Required fundamental fields still missing after fallback: "
                    + ", ".join(missing_after_fallback)
                )
            return combined
        except Exception as exc:
            errors.append(f"Yahoo: {type(exc).__name__}: {exc}")
            if primary_result:
                partial = dict(primary_result)
                missing = [field for field in REQUIRED_FIELDS if partial.get(field) is None]
                partial["fundamental_source"] = "SEC"
                partial["fundamental_quality"] = (
                    "LOW" if any(partial.get(field) is not None for field in REQUIRED_FIELDS) else "UNAVAILABLE"
                )
                partial["warning"] = "Yahoo fallback failed; SEC fields preserved. Missing: " + ", ".join(missing)
                partial["error"] = "; ".join(errors)
                return partial

        return {
            "market_cap": None,
            "pe": None,
            "roe": None,
            "sales_growth_5y": None,
            "fundamental_source": None,
            "fundamental_quality": "UNAVAILABLE",
            "error": "; ".join(errors),
        }
