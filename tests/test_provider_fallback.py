import pandas as pd

from providers.fallback_provider import FallbackMarketDataProvider


class Good:
    def history(self, *args):
        return pd.DataFrame({"Close": [1]})


class Bad:
    def history(self, *args):
        raise RuntimeError("offline")


def test_yahoo_success():
    result = FallbackMarketDataProvider(Good()).history("ABC", "2026-01-01")
    assert result.source == "yfinance"
    assert result.error is None


def test_yahoo_failure_is_reported_without_calling_another_provider():
    result = FallbackMarketDataProvider(Bad()).history("ABC", "2026-01-01")
    assert result.frame is None
    assert result.source is None
    assert "yfinance" in result.error
    assert "offline" in result.error
    assert "stooq" not in result.error.lower()
