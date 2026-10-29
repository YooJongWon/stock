from __future__ import annotations

import pandas as pd
import pytest

from providers.yahoo_fundamentals import _five_year_revenue_cagr


def test_yahoo_annual_revenue_computes_five_year_cagr():
    statement = pd.DataFrame(
        [[200.0, 100.0]],
        index=["Total Revenue"],
        columns=[pd.Timestamp("2025-12-31"), pd.Timestamp("2020-12-31")],
    )
    growth, periods = _five_year_revenue_cagr(statement, "2026-10-28")

    assert growth == pytest.approx((200.0 / 100.0) ** (1 / 5) - 1)
    assert periods["years"] == 5
    assert periods["base_period_end"] == "2020-12-31"
    assert periods["latest_period_end"] == "2025-12-31"


def test_yahoo_annual_revenue_does_not_use_periods_after_reference_date():
    statement = pd.DataFrame(
        [[220.0, 100.0]],
        index=["Total Revenue"],
        columns=[pd.Timestamp("2027-12-31"), pd.Timestamp("2020-12-31")],
    )
    growth, periods = _five_year_revenue_cagr(statement, "2026-10-28")

    assert growth is None
    assert periods is None


def test_yahoo_annual_revenue_does_not_fabricate_growth_when_history_too_short():
    statement = pd.DataFrame(
        [[140.0, 120.0]],
        index=["Total Revenue"],
        columns=[pd.Timestamp("2025-12-31"), pd.Timestamp("2023-12-31")],
    )
    growth, periods = _five_year_revenue_cagr(statement, "2026-10-28")

    assert growth is None
    assert periods is None
