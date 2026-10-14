from __future__ import annotations
from dataclasses import dataclass
import requests
from .yfinance_provider import YFinanceProvider
from .stooq_provider import StooqProvider

@dataclass
class PriceResult:
    frame: object | None
    source: str | None
    error: str | None

class FallbackMarketDataProvider:
    def __init__(self, primary=None, fallback=None):
        self.primary=primary or YFinanceProvider(); self.fallback=fallback or StooqProvider(); self._fallback_unavailable=None
    def history(self, ticker, reference_date):
        try: return PriceResult(self.primary.history(ticker,reference_date),"yfinance",None)
        except Exception as first:
            if self._fallback_unavailable:
                return PriceResult(None,None,f"yfinance: {first}; stooq disabled after prior service failure: {self._fallback_unavailable}")
            try: return PriceResult(self.fallback.history(ticker,reference_date),"stooq_fallback",f"yfinance: {first}")
            except Exception as second:
                if isinstance(second,(requests.Timeout,requests.ConnectionError)) or "did not return CSV" in str(second) or "403" in str(second):
                    self._fallback_unavailable=f"{type(second).__name__}: {second}"
                return PriceResult(None,None,f"yfinance: {first}; stooq: {second}")
