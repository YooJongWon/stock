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

    @staticmethod
    def _validate_spy_session(ticker, frame, reference_date, source):
        if ticker.upper() != "SPY":
            return
        if frame is None or len(frame.index) == 0:
            raise ValueError(f"{source} returned no SPY bars")
        latest = str(frame.index[-1])[:10]
        expected = str(reference_date)[:10]
        if latest != expected:
            raise ValueError(f"{source} SPY close is stale: expected {expected}, received {latest}")

    def history(self, ticker, reference_date):
        try:
            frame = self.primary.history(ticker,reference_date)
            self._validate_spy_session(ticker,frame,reference_date,"yfinance")
            return PriceResult(frame,"yfinance",None)
        except Exception as first:
            if self._fallback_unavailable:
                return PriceResult(None,None,f"yfinance: {first}; stooq disabled after prior service failure: {self._fallback_unavailable}")
            try:
                frame = self.fallback.history(ticker,reference_date)
                self._validate_spy_session(ticker,frame,reference_date,"Stooq")
                return PriceResult(frame,"stooq_fallback",f"yfinance: {first}")
            except Exception as second:
                if isinstance(second,(requests.Timeout,requests.ConnectionError)) or "did not return CSV" in str(second) or "403" in str(second):
                    self._fallback_unavailable=f"{type(second).__name__}: {second}"
                return PriceResult(None,None,f"yfinance: {first}; stooq: {second}")
