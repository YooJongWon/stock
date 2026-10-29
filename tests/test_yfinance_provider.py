import pandas as pd

import providers.yfinance_provider as yfinance_provider
from providers.yfinance_provider import YFinanceProvider


def test_empty_yahoo_history_retries_before_failing(monkeypatch):
    calls = {"count": 0}

    class FakeTicker:
        def __init__(self, ticker):
            self.ticker = ticker

        def history(self, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                return pd.DataFrame()
            index = pd.to_datetime(["2026-10-27", "2026-10-28"])
            return pd.DataFrame(
                {
                    "Open": [100.0, 101.0],
                    "High": [102.0, 103.0],
                    "Low": [99.0, 100.0],
                    "Close": [101.0, 102.0],
                    "Volume": [1_000_000, 1_100_000],
                },
                index=index,
            )

    monkeypatch.setattr(yfinance_provider.yf, "Ticker", lambda ticker: FakeTicker(ticker))
    monkeypatch.setattr(yfinance_provider.time, "sleep", lambda seconds: None)
    provider = YFinanceProvider(retries=1, history_delay=0)

    frame = provider.history("ABC", "2026-10-28")

    assert calls["count"] == 2
    assert len(frame) == 2
    assert str(frame.index[-1])[:10] == "2026-10-28"
