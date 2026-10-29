from __future__ import annotations

from dataclasses import dataclass

from .yfinance_provider import YFinanceProvider


@dataclass
class PriceResult:
    frame: object | None
    source: str | None
    error: str | None


class FallbackMarketDataProvider:
    """Yahoo-only market data access.

    The screener deliberately does not call Stooq or another quota-limited
    provider. Yahoo handles bounded retries; exhausted/invalid results are
    returned as a diagnostic data failure and recorded by the screener.
    """

    def __init__(self, primary=None):
        self.primary = primary or YFinanceProvider()

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
            frame = self.primary.history(ticker, reference_date)
            self._validate_spy_session(ticker, frame, reference_date, "yfinance")
            return PriceResult(frame, "yfinance", None)
        except Exception as exc:
            # Do not disguise a source failure as a valid price. Keep enough
            # context for the run summary and candidate table to explain it.
            return PriceResult(None, None, f"yfinance: {type(exc).__name__}: {exc}")
