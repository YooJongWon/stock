from datetime import date

import exchange_calendars as xc
import pandas as pd
import pytest

from monthly_momentum import BOOTSTRAP_SOURCE, MonthlyMomentum, MonthlyRiskMonitor, pending_month_end, publish_monthly, rebalance_open


def test_month_end_bootstrap_and_rollover_use_us_exchange_sessions():
    october = {"reference_date": "2026-10-30"}
    assert pending_month_end(date(2026, 11, 23), None) == date(2026, 10, 30)
    assert pending_month_end(date(2026, 11, 23), october) is None
    assert pending_month_end(date(2026, 11, 23), {**october, "source": BOOTSTRAP_SOURCE}) == date(2026, 10, 30)
    assert pending_month_end(date(2026, 11, 30), october) == date(2026, 11, 30)
    assert pending_month_end(date(2026, 12, 1), october) == date(2026, 11, 30)


def test_monthly_ranking_skips_recent_returns_and_requires_confirmed_bars():
    month_end = date(2026, 10, 30)
    scan = MonthlyMomentum(month_end)
    calendar = xc.get_calendar("XNYS")
    days = calendar.sessions_in_range(scan.start, date(2026, 11, 23)).date
    frame = pd.DataFrame({col: 100.0 for col in ("Open", "High", "Low", "Close")}, index=days)
    frame["Volume"] = 1_000_000
    frame.loc[scan.end, "Close"] = 150
    frame.loc[month_end, "Close"] = 200
    frame.loc[date(2026, 11, 23), "Close"] = 300

    scan.observe({"ticker": "B"}, frame)
    scan.observe({"ticker": "A"}, frame)
    scan.observe({"ticker": "NO_ANCHOR"}, frame.drop(scan.end))
    scan.observe({"ticker": "STALE"}, frame.drop(month_end))
    scan.observe({"ticker": "LOW_VOLUME"}, frame.assign(Volume=100))

    result = scan.result()
    assert result["eligible_count"] == 2
    assert result["period_end"] == scan.end.isoformat()
    assert [item["ticker"] for item in result["items"]] == ["A", "B"]
    assert [item["return_pct"] for item in result["items"]] == pytest.approx([50, 50])

def test_rotation_preserves_prior_month_across_daily_runs_and_cache_replacement():
    october = {"reference_date": "2026-10-30", "items": [{"ticker": "A"}]}
    november = {"reference_date": "2026-11-30", "items": [{"ticker": "B"}]}
    combined = publish_monthly(october, november)
    assert combined["previous"] == october
    assert publish_monthly(combined, None) == combined
    assert publish_monthly(combined, {**november, "items": []})["previous"] == october
    assert rebalance_open(date(2026, 10, 30)) == "2026-11-02T14:30:00+00:00"


def test_daily_risk_uses_rebalance_open_and_confirmed_closes():
    ranking = {"reference_date": "2026-10-30", "items": [
        {"ticker": ticker} for ticker in ("OK", "CAUTION", "REVIEW", "STALE", "MISSING")
    ]}
    days = [date(2026, 10, 30), date(2026, 11, 2), date(2026, 11, 3)]
    bars = pd.DataFrame({
        "Open": [200, 100, 99], "High": [210, 150, 120], "Low": [190, 85, 80],
        "Close": [200, 96, 99], "Volume": [1000, 1000, 1000],
    }, index=days)

    monitor = MonthlyRiskMonitor(days[-1], ranking)
    for ticker, closes in (("OK", [200, 110, 108.9]), ("CAUTION", [200, 96, 92]), ("REVIEW", [200, 100, 88])):
        monitor.observe({"ticker": ticker}, bars.assign(Close=closes))
    monitor.observe({"ticker": "STALE"}, bars.iloc[:-1])
    risk = monitor.result(ranking)["daily_risk"]
    assert risk["reference_date"] == "2026-11-03"
    assert risk["start_date"] == "2026-11-02"
    assert risk["items"] == {
        "OK": {"status": "normal", "drawdown_pct": -1.0, "rebalance_return_pct": 8.9},
        "CAUTION": {"status": "warning", "drawdown_pct": -8.0, "rebalance_return_pct": -8.0},
        "REVIEW": {"status": "severe", "drawdown_pct": -12.0, "rebalance_return_pct": -12.0},
        "STALE": {"status": "unavailable"},
        "MISSING": {"status": "unavailable"},
    }


def test_daily_risk_resets_when_new_monthly_list_is_published():
    ranking = {"reference_date": "2026-11-30", "items": [{"ticker": "NEW"}]}
    monitor = MonthlyRiskMonitor(date(2026, 11, 30), None)
    risk = monitor.result(ranking)["daily_risk"]
    assert risk["start_date"] == "2026-12-01"
    assert risk["items"] == {"NEW": {"status": "pending"}}
