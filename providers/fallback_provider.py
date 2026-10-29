from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, quote_plus

import requests

from config import SETTINGS
from .yfinance_provider import YFinanceProvider
from .stooq_provider import StooqProvider


@dataclass
class PriceResult:
    frame: object | None
    source: str | None
    error: str | None


class FallbackMarketDataProvider:
    def __init__(self, primary=None, fallback=None):
        self.primary = primary or YFinanceProvider()
        self.fallback = fallback or StooqProvider()
        self._fallback_auth_failure = None

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

    @staticmethod
    def _looks_like_auth_failure(exc):
        message = str(exc).lower()
        return any(token in message for token in (
            "403", "401", "api key", "apikey", "unauthorized", "access denied", "quota exceeded",
        ))

    def _safe_error(self, exc):
        message = f"{type(exc).__name__}: {exc}"
        secret = str(getattr(self.fallback, "api_key", "") or "").strip()
        if secret:
            for variant in (secret, quote(secret, safe=""), quote_plus(secret)):
                if variant:
                    message = message.replace(variant, "[REDACTED]")
        return message

    def history(self, ticker, reference_date):
        errors = []
        try:
            frame = self.primary.history(ticker, reference_date)
            self._validate_spy_session(ticker, frame, reference_date, "yfinance")
            return PriceResult(frame, "yfinance", None)
        except Exception as first:
            errors.append(f"yfinance: {type(first).__name__}: {first}")

        # Stooq started requiring credentials for automated CSV downloads in some access
        # paths. Do not repeatedly make guaranteed-unusable fallback requests if no key exists.
        needs_stooq_key = getattr(self.fallback, "name", "") == "stooq_fallback"
        if needs_stooq_key and not getattr(self.fallback, "api_key", SETTINGS.stooq_api_key):
            return PriceResult(
                None,
                None,
                "; ".join(errors + ["stooq: not attempted (STOOQ_API_KEY is not configured)"]),
            )

        if self._fallback_auth_failure:
            return PriceResult(
                None,
                None,
                "; ".join(errors + [f"stooq disabled after authorization failure: {self._fallback_auth_failure}"]),
            )

        try:
            frame = self.fallback.history(ticker, reference_date)
            self._validate_spy_session(ticker, frame, reference_date, "Stooq")
            return PriceResult(frame, "stooq_fallback", "; ".join(errors))
        except Exception as second:
            safe_second = self._safe_error(second)
            errors.append(f"stooq: {safe_second}")
            if self._looks_like_auth_failure(second):
                self._fallback_auth_failure = safe_second
            # Do not disable Stooq for the entire run after a timeout/connection reset.
            # Only authorization/quota errors make subsequent attempts pointless.
            return PriceResult(None, None, "; ".join(errors))
