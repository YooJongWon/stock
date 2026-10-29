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


def _dashboard_stage(candidate: dict) -> str:
    """Map the quantitative result to a human-readable dashboard stage."""
    final = str(candidate.get("Final") or "").upper()
    if final == "BUY":
        return "BUY"
    if final == "WATCH":
        return "READY"
    fundamental_status = str(candidate.get("Fundamental Status") or "").upper()
    if fundamental_status == "NON_POSITIVE_TTM_EARNINGS":
        return "REJECT"
    quality = str(candidate.get("Fundamental Quality") or "").upper()
    technical_pass = candidate.get("Technical Prefilter Pass") in (True, 1, "True", "true")
    required_financial_fields = ("Market Cap", "PE", "ROE", "Sales Growth 5Y")
    missing_financials = any(candidate.get(field) is None for field in required_financial_fields)
    if technical_pass and (quality == "UNAVAILABLE" or missing_financials):
        return "WAIT"
    return "REJECT"


def _dashboard_stage_reason(candidate: dict, stage: str) -> str:
    if stage == "BUY":
        return "모든 필수 재무·유동성·기술 조건을 통과했습니다."
    if stage == "READY":
        return "핵심 조건은 통과했지만 일부 진입 타이밍 조건이 부족합니다."
    if stage == "WAIT":
        missing = [
            label for field, label in (
                ("Market Cap", "시가총액"), ("PE", "PER"), ("ROE", "ROE"),
                ("Sales Growth 5Y", "5년 매출 성장률"),
            ) if candidate.get(field) is None
        ]
        if missing:
            return "기술 사전 필터는 통과했지만 필수 재무자료 미확인: " + ", ".join(missing)
        return "기술 사전 필터는 통과했지만 필수 재무자료를 확인하지 못해 판정을 보류합니다."
    return str(candidate.get("Fail Reason") or "필수 조건을 충족하지 못했습니다.")


def _load_dashboard_candidates(path: Path) -> list[dict]:
    """Read candidate CSV and preserve the exact per-row filter results for the UI."""
    if not path.is_file():
        return []
    import pandas as pd

    frame = pd.read_csv(path, encoding="utf-8-sig")
    records = json.loads(frame.to_json(orient="records", date_format="iso"))
    for candidate in records:
        raw_filters = candidate.pop("Filter Results", "{}")
        if isinstance(raw_filters, str):
            try:
                candidate["filter_results"] = json.loads(raw_filters)
            except ValueError:
                candidate["filter_results"] = {}
        elif isinstance(raw_filters, dict):
            candidate["filter_results"] = raw_filters
        else:
            candidate["filter_results"] = {}
        stage = _dashboard_stage(candidate)
        candidate["Stage"] = stage
        candidate["Status Reason"] = _dashboard_stage_reason(candidate, stage)
    return records


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
        technical_candidate_csv = stage / "technical_candidates.csv"
        candidate_markdown = stage / "final_candidates.md"
        if not candidate_csv.is_file():
            raise RuntimeError("The screener did not create final_candidates.csv.")
        if not candidate_markdown.is_file():
            raise RuntimeError("The screener did not create final_candidates.md.")

        candidates = _load_dashboard_candidates(candidate_csv)
        technical_candidates = _load_dashboard_candidates(technical_candidate_csv)
        waiting_candidates = [candidate for candidate in technical_candidates if candidate.get("Stage") == "WAIT"]

        warnings = []
        price_failures = int(stats.get("price_history_failures", stats.get("data_failures", 0)) or 0)
        if price_failures:
            category_text = ", ".join(
                f"{name}={count}" for name, count in sorted((stats.get("data_failure_categories") or {}).items())
            ) or "분류 없음"
            examples = stats.get("data_failure_examples") or []
            example_text = "; ".join(
                f"{item.get('ticker', '-')}: {item.get('error', '')}" for item in examples[:3]
            )
            warnings.append(
                f"가격 데이터 조회 실패 {price_failures}종목. 원인 분류(전체): {category_text}."
                + (f" 예시: {example_text}" if example_text else "")
            )
        metadata_failures = int(stats.get("instrument_lookup_failures", 0) or 0)
        if metadata_failures:
            examples = stats.get("instrument_lookup_examples") or []
            example_text = "; ".join(
                f"{item.get('ticker', '-')}: {item.get('reason', '')}" for item in examples[:3]
            )
            warnings.append(
                f"Yahoo 종목 메타정보 조회 실패/불완전 {metadata_failures}종목. "
                "거래소 디렉터리를 사용해 스크리닝을 계속했으며, 이 항목만으로 종목을 제외하지 않았습니다."
                + (f" 예시: {example_text}" if example_text else "")
            )
        source_failures = int(stats.get("fundamental_source_failures", 0) or 0)
        incomplete = int(stats.get("fundamental_incomplete", stats.get("fundamental_unavailable", 0)) or 0)
        if source_failures:
            examples = stats.get("fundamental_failure_examples") or []
            example_text = "; ".join(
                f"{item.get('ticker', '-')}: {item.get('error', '')}" for item in examples[:4]
            )
            warnings.append(
                f"SEC와 Yahoo 재무 공급자 모두 실패/UNAVAILABLE: {source_failures}종목."
                + (f" 예시: {example_text}" if example_text else "")
            )
        incomplete_only = incomplete
        if incomplete_only:
            missing_fields = stats.get("fundamental_missing_fields") or {}
            missing_text = ", ".join(f"{field}={count}" for field, count in sorted(missing_fields.items()))
            warnings.append(
                f"재무 데이터 일부 누락으로 필수 필드를 모두 채우지 못한 종목: {incomplete_only}."
                + (f" 누락 필드 집계: {missing_text}." if missing_text else "")
            )

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
            "technical_candidate_count": len(technical_candidates) if technical_candidate_csv.is_file() else stats.get("technical_prefilter_count"),
            "fundamental_candidate_count": stats.get("fundamental_candidate_count"),
            "buy_count": stats.get("buy_count"),
            "watch_count": stats.get("watch_count"),
            "ready_count": stats.get("watch_count"),
            "waiting_count": len(waiting_candidates),
            "candidate_count": len(candidates),
            "data_failures": stats.get("data_failures", 0),
            "price_history_failures": stats.get("price_history_failures", stats.get("data_failures", 0)),
            "data_failure_categories": stats.get("data_failure_categories", {}),
            "data_failure_examples": stats.get("data_failure_examples", []),
            "instrument_lookup_failures": stats.get("instrument_lookup_failures", 0),
            "instrument_lookup_examples": stats.get("instrument_lookup_examples", []),
            "instrument_rejections": stats.get("instrument_rejections", 0),
            "fundamental_unavailable": stats.get("fundamental_unavailable", 0),
            "fundamental_source_failures": stats.get("fundamental_source_failures", 0),
            "fundamental_incomplete": stats.get("fundamental_incomplete", 0),
            "fundamental_nonpositive_earnings": stats.get("fundamental_nonpositive_earnings", 0),
            "fundamental_rejection_examples": stats.get("fundamental_rejection_examples", []),
            "mixed_source_fundamentals": stats.get("mixed_source_fundamentals", 0),
            "fundamental_missing_fields": stats.get("fundamental_missing_fields", {}),
            "fundamental_failure_examples": stats.get("fundamental_failure_examples", []),
            "sector_performance": stats.get("sector_performance", []),
            "candidates": candidates,
            "technical_candidates": technical_candidates,
            "waiting_candidates": waiting_candidates,
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
