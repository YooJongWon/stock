"""Point-in-time fundamentals: SEC first, and fill missing fields only with permitted Yahoo data."""
from __future__ import annotations

import logging

from providers.sec_fundamentals import SECFundamentalProvider
from providers.yahoo_fundamentals import (
    FundamentalFallbackWithheldError,
    YahooFundamentalProvider,
)

LOG = logging.getLogger(__name__)
REQUIRED_FIELDS = ("market_cap", "pe", "roe", "sales_growth_5y")


class FallbackFundamentalProvider:
    def __init__(self, primary=None, fallback=None, finimpulse=None):
        self.primary = primary or SECFundamentalProvider()
        self.fallback = fallback or YahooFundamentalProvider()

    def get_fundamentals(self, ticker, cik, reference_date, price):
        errors = []
        primary_result = None
        sec_status = "FAILED"

        try:
            if not cik:
                raise ValueError("SEC CIK missing for ticker")
            result = self.primary.get_fundamentals(cik, reference_date, price)
            if isinstance(result, dict):
                primary_result = result
                sec_status = "SUCCESS"
                # Nonpositive earnings are a real financial condition, not a provider outage.
                if result.get("fundamental_status") == "NON_POSITIVE_TTM_EARNINGS":
                    return {
                        **result,
                        "fundamental_sec_status": sec_status,
                        "fundamental_fallback_status": "NOT_NEEDED",
                        "fundamental_fallback_error": None,
                    }
                missing = [field for field in REQUIRED_FIELDS if result.get(field) is None]
                if result.get("fundamental_quality") != "UNAVAILABLE" and not missing:
                    return {
                        **result,
                        "fundamental_sec_status": sec_status,
                        "fundamental_fallback_status": "NOT_NEEDED",
                        "fundamental_fallback_error": None,
                    }
                if missing:
                    errors.append("SEC missing required fields: " + ", ".join(missing))
                else:
                    errors.append(str(result.get("error") or "SEC result marked unavailable"))
            else:
                errors.append("SEC returned an unexpected result")
        except Exception as exc:
            errors.append(f"SEC: {type(exc).__name__}: {exc}")

        def partial_result(fallback_status, fallback_error):
            partial = dict(primary_result or {})
            missing = [field for field in REQUIRED_FIELDS if partial.get(field) is None]
            for field in REQUIRED_FIELDS:
                partial.setdefault(field, None)
            partial["missing_fields"] = missing
            partial["fundamental_source"] = "SEC" if primary_result else None
            partial["fundamental_quality"] = (
                "LOW" if any(partial.get(field) is not None for field in REQUIRED_FIELDS) else "UNAVAILABLE"
            )
            partial["fundamental_status"] = partial.get("fundamental_status") or (
                "INCOMPLETE_FIELDS" if partial["fundamental_quality"] == "LOW" else "UNAVAILABLE"
            )
            partial["fundamental_sec_status"] = sec_status
            partial["fundamental_fallback_status"] = fallback_status
            partial["fundamental_fallback_error"] = fallback_error
            if fallback_status == "WITHHELD":
                partial["warning"] = (
                    "Yahoo fallback withheld by the point-in-time date guard. Missing: "
                    + ", ".join(missing)
                )
            else:
                partial["warning"] = (
                    "Yahoo fallback failed; SEC fields preserved. Missing: " + ", ".join(missing)
                )
            partial["error"] = "; ".join(errors) or None
            return partial

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

            # Cross-derive P/E only when SEC has positive TTM net income.
            if (
                combined.get("pe") is None
                and combined.get("market_cap") is not None
                and combined.get("ttm_net_income") is not None
                and float(combined["ttm_net_income"]) > 0
            ):
                combined["pe"] = float(combined["market_cap"]) / float(combined["ttm_net_income"])
                if "pe" not in yahoo_filled:
                    yahoo_filled.append("pe")

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
            combined["fundamental_sec_status"] = sec_status
            combined["fundamental_fallback_status"] = "SUCCESS"
            combined["fundamental_fallback_error"] = None
            diagnostics = list(errors)
            for field in ("warning", "statement_error"):
                value = yahoo.get(field)
                if value:
                    diagnostics.append(f"Yahoo {field}: {value}")
            if yahoo.get("error"):
                diagnostics.append(f"Yahoo: {yahoo['error']}")
            combined["error"] = "; ".join(dict.fromkeys(diagnostics)) or None

            missing_after_fallback = [field for field in REQUIRED_FIELDS if combined.get(field) is None]
            combined["missing_fields"] = missing_after_fallback
            if missing_after_fallback:
                combined["fundamental_status"] = "INCOMPLETE_FIELDS"
                combined["fundamental_quality"] = "LOW" if any(
                    combined.get(field) is not None for field in REQUIRED_FIELDS
                ) else "UNAVAILABLE"
                combined["warning"] = (
                    "Required fundamental fields still missing after fallback: "
                    + ", ".join(missing_after_fallback)
                )
            else:
                combined["fundamental_status"] = "AVAILABLE"
                combined["warning"] = None
            return combined
        except FundamentalFallbackWithheldError as exc:
            return partial_result("WITHHELD", str(exc))
        except Exception as exc:
            errors.append(f"Yahoo: {type(exc).__name__}: {exc}")
            return partial_result("FAILED", str(exc))
