import json
from datetime import date

import pandas as pd

from providers.fallback_provider import PriceResult
from scripts import run_monthly


def quote(values):
    return PriceResult(pd.DataFrame(
        {"Open": 100, "High": 110, "Low": 80, "Close": list(values.values()), "Volume": 1000000},
        index=list(values),
    ), "test", None)


def test_daily_batch_fetches_spy_and_published_tickers_only(tmp_path, monkeypatch):
    trading_day = date(2026, 11, 3)
    data = tmp_path / "web" / "public" / "data"
    initial = {
        "reference_date": "2026-10-30", "items": [{"ticker": "A"}, {"ticker": "MISSING"}],
        "source": "existing_momentum_price_cache",
    }
    data.mkdir(parents=True)
    snapshot = data / "latest-results.json"
    snapshot.write_text(json.dumps({"monthly_momentum": initial}))
    calls = []

    class Prices:
        def history(self, ticker, reference_date):
            calls.append((ticker, reference_date))
            if ticker == "MISSING":
                return PriceResult(None, None, "no close")
            return quote({date(2026, 11, 2): 100, trading_day: 88})

    def unused_universe():
        raise AssertionError("Daily checks must not load the market universe")

    monkeypatch.setattr(run_monthly, "ROOT", tmp_path)
    monkeypatch.setattr(run_monthly, "latest_completed_session", lambda: trading_day)
    monkeypatch.setattr(run_monthly, "DataProvider", Prices)
    monkeypatch.setattr(run_monthly, "UniverseProvider", unused_universe)

    assert run_monthly.main([]) == 0
    assert calls == [(ticker, trading_day) for ticker in ("SPY", "A", "MISSING")]
    result = json.loads(snapshot.read_text())
    assert result["status"] == "degraded"
    assert result["monthly_momentum"]["items"] == initial["items"]
    assert result["monthly_momentum"]["daily_risk"]["items"] == {
        "A": {"status": "severe", "drawdown_pct": -12.0},
        "MISSING": {"status": "unavailable"},
    }


def test_month_end_rebuilds_rankings_and_waits_for_first_close(tmp_path, monkeypatch):
    month_end = date(2026, 11, 30)
    previous = {"reference_date": "2026-10-30", "items": [{"ticker": "OLD"}]}
    data = tmp_path / "web" / "public" / "data"
    data.mkdir(parents=True)
    snapshot = data / "latest-results.json"
    snapshot.write_text(json.dumps({"monthly_momentum": previous}))
    tickers = [f"STOCK{i}" for i in range(11)]
    calls = []

    class Prices:
        def history(self, ticker, reference_date):
            calls.append((ticker, reference_date))
            return quote({month_end: 100})

    class Universe:
        def get(self):
            return [{"ticker": ticker} for ticker in tickers]

    class Ranking:
        def __init__(self, reference_date):
            assert reference_date == month_end
            self.items = []

        def observe(self, member, frame):
            self.items.append(member)

        def result(self):
            return {"reference_date": str(month_end), "items": self.items[:10]}

    monkeypatch.setattr(run_monthly, "ROOT", tmp_path)
    monkeypatch.setattr(run_monthly, "latest_completed_session", lambda: month_end)
    monkeypatch.setattr(run_monthly, "DataProvider", Prices)
    monkeypatch.setattr(run_monthly, "UniverseProvider", Universe)
    monkeypatch.setattr(run_monthly, "MonthlyMomentum", Ranking)

    assert run_monthly.main([]) == 0
    assert calls == [(ticker, month_end) for ticker in ["SPY", *tickers]]
    result = json.loads(snapshot.read_text())
    monthly = result["monthly_momentum"]
    assert monthly["previous"] == previous
    assert monthly["daily_risk"]["items"] == {ticker: {"status": "pending"} for ticker in tickers[:10]}

    calls.clear()
    assert run_monthly.main(["--skip-unchanged"]) == 0
    assert calls == []
