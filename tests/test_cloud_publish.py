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
