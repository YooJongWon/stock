from datetime import date

import exchange_calendars as xc
import pandas as pd
import pytest

from monthly_momentum import BOOTSTRAP_SOURCE, MonthlyMomentum, pending_month_end


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
