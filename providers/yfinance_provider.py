from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from indicators import normalize_ohlcv

LOG = logging.getLogger(__name__)


def _retryable_yahoo_error(error: Exception) -> bool:
    message = str(error).lower()
    return isinstance(error, (TimeoutError, ConnectionError)) or any(
        part in message
        for part in ("429", "too many requests", "rate limit", "timed out", "temporarily unavailable", "502", "503", "504")
    )


class YFinanceProvider:
    name = "yfinance"

    def __init__(self, retries=3, history_delay=0.15):
        self.retries = retries
        self.history_delay = history_delay

    def history(self, ticker: str, reference_date, period="2y"):
        errors = []
        for attempt in range(self.retries + 1):
            try:
                if self.history_delay:
                    time.sleep(self.history_delay)
                if attempt:
                    LOG.warning("yfinance retry %d/%d for %s", attempt, self.retries, ticker)
                raw = yf.Ticker(ticker).history(
                    period=period,
                    interval="1d",
                    auto_adjust=True,
                    actions=False,
                    timeout=25,
                )
                # yfinance can log/absorb throttling errors and return an empty frame.
                # Treat that as a retryable provider response instead of a deterministic
                # malformed-symbol error on the very first attempt.
                if raw is None or raw.empty:
                    message = "Yahoo Finance returned an empty daily-history frame"
                    errors.append(message)
                    if attempt < self.retries:
                        delay = min(2 ** attempt, 8)
                        LOG.warning("%s for %s; retrying in %ss", message, ticker, delay)
                        time.sleep(delay)
                        continue
                    break
                df = normalize_ohlcv(raw, reference_date)
                return df
            except ValueError as exc:
                # Most validation failures are deterministic. Empty frames are handled
                # above; malformed non-empty OHLCV should proceed to a different source.
                errors.append(f"{type(exc).__name__}: {exc}")
                break
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if attempt >= self.retries or not _retryable_yahoo_error(exc):
                    break
                delay = min(2 ** attempt, 8)
                LOG.warning("yfinance history failure for %s: %s; retrying in %ss", ticker, exc, delay)
                time.sleep(delay)
        raise RuntimeError("yfinance failed: " + " | ".join(errors))

    def instrument_info(self, ticker: str) -> dict:
        """Yahoo quote metadata is advisory; the universe source remains the listing authority."""
        errors = []
        for attempt in range(self.retries + 1):
            try:
                info = yf.Ticker(ticker).get_info()
                if isinstance(info, dict) and info:
                    return info
                errors.append("Yahoo Finance returned an empty instrument-info payload")
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if attempt >= self.retries or not _retryable_yahoo_error(exc):
                    break
            if attempt < self.retries:
                delay = min(2 ** attempt, 8)
                LOG.warning("yfinance instrument lookup retry for %s in %ss", ticker, delay)
                time.sleep(delay)
        raise RuntimeError("yfinance instrument-info failed: " + " | ".join(errors))


def is_us_common_equity(info: dict) -> bool:
    if not info or info.get("quoteType") != "EQUITY":
        return False
    code = str(info.get("exchange", "")).upper()
    name = str(info.get("fullExchangeName", "")).upper()
    return code in {"NMS", "NGM", "NCM", "NAS", "NYQ", "NYE", "ASE", "PCX", "BTS"} or any(
        x in name for x in ("NASDAQ", "NEW YORK STOCK EXCHANGE", "NYSE AMERICAN", "NYSE ARCA")
    )
