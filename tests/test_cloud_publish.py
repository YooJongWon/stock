import json
from pathlib import Path

import pandas as pd
import pytest

import market_calendar
import screener
from scripts import run_cloud


REFERENCE_DATE = "2026-10-09"


class StubScreener:
    stats = {
        "universe_count": 2,
        "universe_scanned_count": 2,
        "technical_prefilter_count": 1,
        "fundamental_candidate_count": 1,
        "buy_count": 1,
        "watch_count": 0,
        "data_failures": 0,
        "fundamental_unavailable": 0,
        "spy_regime": "BULL",
        "spy_reference_date": REFERENCE_DATE,
        "run_timestamp": "2026-10-10T00:00:00+00:00",
    }
    candidate_rows = [{"Ticker": "ABC", "Final": "BUY", "Score": 8,
                       "Filter Results": json.dumps({"Price >= $10": True, "Score >= 7": True})}]

    def run(self, reference_date):
        assert str(reference_date) == REFERENCE_DATE
        output = Path(__import__("os").environ["SCREENER_OUTPUT_DIR"])
        pd.DataFrame(self.candidate_rows, columns=["Ticker", "Final", "Score", "Filter Results"]).to_csv(
            output / "final_candidates.csv", index=False, encoding="utf-8-sig")
        (output / "final_candidates.md").write_text(
            "# Test candidates\n\n| Ticker | Final | Score | Filter Results |\n|---|---|---:|---|\n| ABC | BUY | 8 | checks pass |\n",
            encoding="utf-8",
        )
        return [], {**self.stats}


@pytest.fixture
def isolated_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(run_cloud, "ROOT", tmp_path)
    monkeypatch.setattr(market_calendar, "latest_completed_session", lambda: pd.Timestamp(REFERENCE_DATE).date())
    monkeypatch.setattr(market_calendar, "is_exchange_session", lambda _: True)
    monkeypatch.setattr(screener, "Screener", StubScreener)
    data = tmp_path / "web" / "public" / "data"
    data.mkdir(parents=True)
    return data


def test_cloud_publishes_actual_checks_and_distinguishes_empty_from_not_run(isolated_publish):
    assert run_cloud.main([]) == 0
    result = json.loads((isolated_publish / "latest-results.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["data_date"] == REFERENCE_DATE
    assert result["candidates"][0]["filter_results"] == {"Price >= $10": True, "Score >= 7": True}
    assert (isolated_publish / "latest-candidates.csv").is_file()
    assert json.loads((isolated_publish / "latest-run-status.json").read_text())["status"] == "success"


def test_cloud_refuses_stale_spy_close_and_preserves_last_good_files(isolated_publish, monkeypatch):
    result_file = isolated_publish / "latest-results.json"
    csv_file = isolated_publish / "latest-candidates.csv"
    result_file.write_text('{"status":"success","data_date":"2026-10-08","saved":"old"}', encoding="utf-8")
    csv_file.write_text("previous good csv\n", encoding="utf-8")

    class StaleScreener(StubScreener):
        stats = {**StubScreener.stats, "spy_reference_date": "2026-10-08"}

    monkeypatch.setattr(screener, "Screener", StaleScreener)
    with pytest.raises(RuntimeError, match="SPY close is not confirmed"):
        run_cloud.main([])
    assert json.loads(result_file.read_text(encoding="utf-8"))["saved"] == "old"
    assert csv_file.read_text(encoding="utf-8") == "previous good csv\n"


def test_scheduled_repeat_skips_without_replacing_existing_result(isolated_publish, monkeypatch):
    result_file = isolated_publish / "latest-results.json"
    result_file.write_text(json.dumps({"status": "success", "data_date": REFERENCE_DATE, "saved": "old"}), encoding="utf-8")

    class MustNotRun:
        def __init__(self):
            raise AssertionError("unchanged scheduled session should be skipped")

    monkeypatch.setattr(screener, "Screener", MustNotRun)
    assert run_cloud.main(["--skip-unchanged"]) == 0
    assert json.loads(result_file.read_text(encoding="utf-8"))["saved"] == "old"



def test_cloud_diagnostics_keep_counts_and_examples_in_their_own_categories(isolated_publish, monkeypatch):
    class DiagnosticScreener(StubScreener):
        stats = {
            **StubScreener.stats,
            "fundamental_no_usable_data": 2,
            "fundamental_source_failures": 2,
            "fundamental_source_failure_examples": [
                {"ticker": "SRC1", "reason": "No usable required fundamental fields"},
                {"ticker": "SRC2", "reason": "No usable required fundamental fields"},
            ],
            "fundamental_incomplete": 44,
            "fundamental_missing_fields": {"roe": 18, "sales_growth_5y": 25},
            "fundamental_incomplete_examples": [
                {"ticker": "INC1", "missing_fields": ["roe"]},
                {"ticker": "INC2", "missing_fields": ["sales_growth_5y"]},
                {"ticker": "INC3", "missing_fields": ["roe", "sales_growth_5y"]},
                {"ticker": "INC4", "missing_fields": ["market_cap"]},
            ],
            "fundamental_sec_failures": 1,
            "fundamental_sec_failure_examples": [
                {"ticker": "SECERR", "reason": "SEC API timeout"},
            ],
            "fundamental_fallback_withheld": 3,
            "fundamental_fallback_withheld_examples": [
                {"ticker": "HOLD1", "reason": "reference date is not the current New York market date"},
            ],
            "fundamental_fallback_failures": 1,
            "fundamental_fallback_failure_examples": [
                {"ticker": "FAIL1", "reason": "Yahoo API timeout"},
            ],
            # This legacy mixed list intentionally contains unrelated tickers.
            "fundamental_failure_examples": [
                {"ticker": "SRC1", "error": "source failure"},
                {"ticker": "INC1", "error": "missing roe"},
                {"ticker": "INC2", "error": "missing growth"},
                {"ticker": "INC3", "error": "missing two fields"},
            ],
        }

    monkeypatch.setattr(screener, "Screener", DiagnosticScreener)
    assert run_cloud.main([]) == 0
    result = json.loads((isolated_publish / "latest-results.json").read_text(encoding="utf-8"))
    warnings = result["warnings"]

    unavailable_warning = next(item for item in warnings if item.startswith("필수 재무정보를 확보하지 못한"))
    incomplete_warning = next(item for item in warnings if item.startswith("재무 데이터 일부 누락"))
    sec_warning = next(item for item in warnings if item.startswith("SEC 재무정보 조회 실패"))
    withheld_warning = next(item for item in warnings if item.startswith("기준일 검증으로 Yahoo"))
    fallback_failure_warning = next(item for item in warnings if item.startswith("Yahoo 재무 보충 조회 실제 실패"))

    assert "2종목" in unavailable_warning
    assert "SRC1" in unavailable_warning and "SRC2" in unavailable_warning
    assert "INC1" not in unavailable_warning and "INC2" not in unavailable_warning
    assert "44" in incomplete_warning
    assert "INC1(roe)" in incomplete_warning and "INC2(sales_growth_5y)" in incomplete_warning
    assert "SRC1" not in incomplete_warning
    assert "1종목" in sec_warning and "SECERR" in sec_warning
    assert "3종목" in withheld_warning and "HOLD1" in withheld_warning
    assert "API 실패가 아니라" in withheld_warning
    assert "1종목" in fallback_failure_warning and "FAIL1" in fallback_failure_warning
    assert result["fundamental_fallback_withheld"] == 3
    assert result["fundamental_fallback_failures"] == 1
