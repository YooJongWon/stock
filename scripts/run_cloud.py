"""Run the existing screener into a staging folder and publish validated web data."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _read_current_result(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8", newline="\n")
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run and publish a validated US-stock screener snapshot")
    parser.add_argument("--skip-unchanged", action="store_true", help="skip scheduled runs when the same XNYS session is already published")
    parser.add_argument("--scheduled", action="store_true", help="only run when the previous Korea calendar date was an XNYS session")
    args = parser.parse_args(argv)

    # Set this before importing config/screener; local output files remain untouched.
    with tempfile.TemporaryDirectory(prefix="stock-screener-") as scratch:
        os.environ["SCREENER_OUTPUT_DIR"] = scratch
        from market_calendar import is_exchange_session, latest_completed_session, previous_korea_date_session
        from screener import Screener

        if args.scheduled:
            reference_date = previous_korea_date_session()
            if reference_date is None:
                print("No XNYS session on the previous Korea calendar date; skipping the scheduled screener run.")
                return 0
        else:
            reference_date = latest_completed_session()

        if not is_exchange_session(reference_date):
            raise RuntimeError(f"Calculated reference date is not an XNYS session: {reference_date}")

        result_path = ROOT / "web" / "public" / "data" / "latest-results.json"
        current = _read_current_result(result_path)
        if args.skip_unchanged and current.get("data_date") == str(reference_date) and current.get("status") in ("success", "degraded"):
            print(f"No new XNYS session since {reference_date}; keeping the existing published result.")
            return 0

        rows, stats = Screener().run(reference_date)
        if stats.get("universe_error"):
            raise RuntimeError(f"Universe retrieval failed: {stats['universe_error']}")
        if not stats.get("universe_count") or not stats.get("universe_scanned_count"):
            raise RuntimeError("The screener returned no universe rows; refusing to publish an empty error result.")
        if stats.get("spy_reference_date") != str(reference_date):
            raise RuntimeError(
                "SPY close is not confirmed for the latest completed XNYS session "
                f"({reference_date}); received {stats.get('spy_reference_date')!r}."
            )

        stage = Path(scratch)
        candidate_csv = stage / "final_candidates.csv"
        candidate_markdown = stage / "final_candidates.md"
        if not candidate_csv.is_file():
            raise RuntimeError("The screener did not create final_candidates.csv.")
        if not candidate_markdown.is_file():
            raise RuntimeError("The screener did not create final_candidates.md.")

        import pandas as pd

        frame = pd.read_csv(candidate_csv, encoding="utf-8-sig")
        candidates = json.loads(frame.to_json(orient="records", date_format="iso"))
        for candidate in candidates:
            raw_filters = candidate.pop("Filter Results", "{}")
            candidate["filter_results"] = json.loads(raw_filters) if isinstance(raw_filters, str) else {}

        warnings = []
        if stats.get("data_failures"):
            warnings.append(f"{stats['data_failures']} ticker data or instrument checks failed; see the candidate table and run summary.")
        if stats.get("fundamental_unavailable"):
            warnings.append(f"Fundamentals were unavailable for {stats['fundamental_unavailable']} screened candidates.")

        payload = {
            "schema_version": 1,
            "status": "degraded" if warnings else "success",
            "last_successful_run_at": stats["run_timestamp"],
            "data_date": str(reference_date),
            "error": None,
            "warnings": warnings,
            "warning_count": len(warnings),
            "spy_regime": stats.get("spy_regime"),
            "spy_reference_date": stats.get("spy_reference_date"),
            "universe_count": stats.get("universe_count"),
            "universe_scanned_count": stats.get("universe_scanned_count"),
            "technical_candidate_count": stats.get("technical_prefilter_count"),
            "fundamental_candidate_count": stats.get("fundamental_candidate_count"),
            "buy_count": stats.get("buy_count"),
            "watch_count": stats.get("watch_count"),
            "candidate_count": len(candidates),
            "data_failures": stats.get("data_failures", 0),
            "fundamental_unavailable": stats.get("fundamental_unavailable", 0),
            "candidates": candidates,
        }

        # Do not touch the published files until all fatal checks and serialization pass.
        _atomic_write(result_path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        markdown_path = result_path.with_name("latest-candidates.md")
        _atomic_write(markdown_path, candidate_markdown.read_text(encoding="utf-8"))
        csv_path = result_path.with_name("latest-candidates.csv")
        temporary_csv = csv_path.with_suffix(".csv.tmp")
        shutil.copyfile(candidate_csv, temporary_csv)
        temporary_csv.replace(csv_path)
        status_path = result_path.with_name("latest-run-status.json")
        _atomic_write(status_path, json.dumps({
            "status": payload["status"],
            "attempted_at": payload["last_successful_run_at"],
            "reference_date": payload["data_date"],
            "message": None,
        }, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({k: payload[k] for k in ("status", "data_date", "candidate_count", "warning_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
