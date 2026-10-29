from scripts.run_cloud import _dashboard_stage, _dashboard_stage_reason


def candidate(**overrides):
    row = {
        "Final": "REJECT",
        "Technical Prefilter Pass": True,
        "Fundamental Quality": "HIGH",
        "Market Cap": 3_000_000_000,
        "PE": 21.0,
        "ROE": 0.18,
        "Sales Growth 5Y": 0.08,
        "Fail Reason": "Recent Volume Dry-up",
    }
    row.update(overrides)
    return row


def test_buy_is_mapped_to_buy_stage():
    assert _dashboard_stage(candidate(Final="BUY")) == "BUY"


def test_watch_is_mapped_to_ready_stage():
    assert _dashboard_stage(candidate(Final="WATCH")) == "READY"


def test_technical_candidate_without_fundamentals_is_waiting():
    row = candidate(**{"Fundamental Quality": "UNAVAILABLE"})
    assert _dashboard_stage(row) == "WAIT"
    assert "재무자료" in _dashboard_stage_reason(row, "WAIT")


def test_missing_one_required_financial_field_is_waiting():
    row = candidate(**{"Sales Growth 5Y": None})
    assert _dashboard_stage(row) == "WAIT"
    assert "5년 매출 성장률" in _dashboard_stage_reason(row, "WAIT")


def test_unavailable_fundamentals_without_technical_prefilter_is_not_waiting():
    row = candidate(**{"Fundamental Quality": "UNAVAILABLE", "Technical Prefilter Pass": False})
    assert _dashboard_stage(row) == "REJECT"


def test_fundamentals_available_but_hard_filter_failed_is_rejected():
    assert _dashboard_stage(candidate()) == "REJECT"
