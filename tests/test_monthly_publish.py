import json
from datetime import date

import exchange_calendars as xc
import pandas as pd

from monthly_momentum import MonthlyMomentum
from providers.fallback_provider import PriceResult
from scripts import run_monthly
from sector_performance import SECTOR_ETFS, YFinanceProvider


def quote(values):
    return PriceResult(pd.DataFrame(
        {"Open": 100, "High": 110, "Low": 80, "Close": list(values.values()), "Volume": 1000000},
        index=list(values),
    ), "test", None)


def test_scheduled_holiday_publishes_market_status_without_refreshing_prices(tmp_path, monkeypatch):
    holiday = date(2026, 11, 26)
    data = tmp_path / "web" / "public" / "data"
    data.mkdir(parents=True)
    snapshot = data / "latest-results.json"
    published = '{"data_date": "2026-11-25"}\n'
    snapshot.write_text(published)

    def unused_prices():
        raise AssertionError("A market closure must not fetch prices")

    monkeypatch.setattr(run_monthly, "ROOT", tmp_path)
    monkeypatch.setattr(run_monthly, "previous_korea_date", lambda _now: holiday)
    monkeypatch.setattr(run_monthly, "DataProvider", unused_prices)

    assert run_monthly.main(["--scheduled", "--skip-unchanged"]) == 0
    status_file = data / "latest-run-status.json"
    status_text = status_file.read_text()
    status = json.loads(status_text)
    assert status["status"] == "market_closed"
    assert status["reference_date"] == holiday.isoformat()
    assert snapshot.read_text() == published
    assert run_monthly.main(["--scheduled", "--skip-unchanged"]) == 0
    assert status_file.read_text() == status_text


def test_daily_batch_fetches_spy_published_tickers_and_sector_etfs(tmp_path, monkeypatch):
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
            if ticker == "XLV":
                return quote({date(2026, 10, 30): 100, trading_day: 88})
            return quote({date(2026, 11, 2): 100, trading_day: 88})

    def unused_universe():
        raise AssertionError("Daily checks must not load the market universe")

    monkeypatch.setattr(run_monthly, "ROOT", tmp_path)
    monkeypatch.setattr(run_monthly, "latest_completed_session", lambda _now: trading_day)
    monkeypatch.setattr(run_monthly, "DataProvider", Prices)
    monkeypatch.setattr(run_monthly, "UniverseProvider", unused_universe)
    monkeypatch.setattr(YFinanceProvider, "instrument_info",
                        lambda self, ticker: {"sectorKey": "technology"} if ticker == "A" else {})

    assert run_monthly.main([]) == 0
    assert calls == [(ticker, trading_day) for ticker in ("SPY", "A", "MISSING", *(symbol for symbol, _ in SECTOR_ETFS))]
    result = json.loads(snapshot.read_text())
    assert result["status"] == "degraded"
    status = json.loads((data / "latest-run-status.json").read_text())
    assert (status["status"], status["reference_date"]) == ("degraded", str(trading_day))
    assert result["monthly_momentum"]["items"] == initial["items"]
    assert result["sector_reference_date"] == str(trading_day)
    assert result["stock_sectors"] == {"A": "XLK"}
    sectors = {row["symbol"]: row for row in result["sector_performance"]}
    assert sectors[result["stock_sectors"]["A"]] == {"symbol": "XLK", "sector": "정보기술", "change_pct": -12.0}
    assert sectors["XLV"]["change_pct"] is None
    assert result["monthly_momentum"]["daily_risk"]["items"] == {
        "A": {"status": "severe", "drawdown_pct": -12.0, "rebalance_return_pct": -12.0},
        "MISSING": {"status": "unavailable"},
    }


def test_month_end_rebuilds_rankings_and_waits_for_first_close(tmp_path, monkeypatch):
    month_end = date(2026, 11, 30)
    previous = {"reference_date": "2026-10-30", "items": [{"ticker": "OLD"}]}
    data = tmp_path / "web" / "public" / "data"
    data.mkdir(parents=True)
    snapshot = data / "latest-results.json"
    snapshot.write_text(json.dumps({"monthly_momentum": previous}))
    tickers = [f"STOCK{i:02d}" for i in range(15)]
    calls = []
    missing = set(tickers[-4:])
    scan = MonthlyMomentum(month_end)
    sessions = xc.get_calendar("XNYS").sessions_in_range(scan.start, month_end).date
    complete_quote = quote(dict.fromkeys(sessions, 100))
    stale_quote = quote(dict.fromkeys(sessions[:-1], 100))

    class Prices:
        def history(self, ticker, reference_date):
            calls.append((ticker, reference_date))
            if ticker in missing:
                return stale_quote if ticker == tickers[-1] else PriceResult(None, None, "no close")
            return complete_quote

    class Universe:
        def get(self):
            return [{"ticker": ticker} for ticker in tickers]

    monkeypatch.setattr(run_monthly, "ROOT", tmp_path)
    monkeypatch.setattr(run_monthly, "latest_completed_session", lambda _now: month_end)
    monkeypatch.setattr(run_monthly, "DataProvider", Prices)
    monkeypatch.setattr(run_monthly, "UniverseProvider", Universe)
    monkeypatch.setattr(YFinanceProvider, "instrument_info", lambda self, ticker: {})

    assert run_monthly.main([]) == 0
    held = json.loads(snapshot.read_text())
    assert held["status"] == "degraded"
    assert held["monthly_momentum"]["items"] == previous["items"]
    assert held["monthly_ranking_quality"] == {
        "reference_date": str(month_end), "status": "held", "total_count": 15,
        "missing_count": 4, "eligible_count": 11, "min_coverage_pct": 75,
    }

    calls.clear()
    missing.clear()
    assert run_monthly.main(["--skip-unchanged"]) == 0
    assert calls == [(ticker, month_end) for ticker in ["SPY", *tickers, *(symbol for symbol, _ in SECTOR_ETFS)]]
    result = json.loads(snapshot.read_text())
    assert result["monthly_ranking_quality"]["status"] == "published"
    monthly = result["monthly_momentum"]
    assert monthly["previous"] == previous
    assert monthly["daily_risk"]["items"] == {ticker: {"status": "pending"} for ticker in tickers[:10]}

    calls.clear()
    assert run_monthly.main(["--skip-unchanged"]) == 0
    assert calls == []
