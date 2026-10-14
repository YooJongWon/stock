"""Point-in-time fundamentals: SEC first, Yahoo fallback only when verifiable."""
from __future__ import annotations
from providers.sec_fundamentals import SECFundamentalProvider
from providers.yahoo_fundamentals import YahooFundamentalProvider


class FallbackFundamentalProvider:
    def __init__(self, primary=None, fallback=None, finimpulse=None):
        self.primary = primary or SECFundamentalProvider()
        self.fallback = fallback or YahooFundamentalProvider()

    def get_fundamentals(self, ticker, cik, reference_date, price):
        errors=[]
        try:
            if not cik:
                raise ValueError("SEC CIK missing for ticker")
            return self.primary.get_fundamentals(cik, reference_date, price)
        except Exception as exc:
            errors.append(f"SEC: {type(exc).__name__}: {exc}")
        try:
            result=self.fallback.get_fundamentals(ticker, reference_date, price)
            return {**result, "error":"; ".join(errors), "fundamental_source":result.get("fundamental_source", "yfinance")}
        except Exception as exc:
            errors.append(f"yfinance: {type(exc).__name__}: {exc}")
        return {"market_cap":None,"pe":None,"roe":None,"sales_growth_5y":None,
                "fundamental_source":None,"fundamental_quality":"UNAVAILABLE","error":"; ".join(errors)}
