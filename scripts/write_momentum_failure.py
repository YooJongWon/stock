"""Publish independent momentum failure diagnostics, without touching swing results."""
from datetime import datetime, timezone
import json
from pathlib import Path
from market_calendar import latest_completed_session
from scripts.run_cloud import _atomic_write

ROOT = Path(__file__).resolve().parents[1]


def record_failure(output: Path, research_path: Path):
    try:
        research = json.loads(research_path.read_text(encoding='utf8'))
    except (OSError, ValueError):
        research = {}
    payload = {'schema_version':1, 'status':'failed', 'data_date':str(latest_completed_session()), 'generated_at':datetime.now(timezone.utc).isoformat(), 'research_generated_at':research.get('generated_at'), 'candidates':[], 'universe_count':0, 'diagnostics':[{'error':'모멘텀 스크리닝 실행 실패. GitHub Actions 실행 로그를 확인하세요. 기존 스윙 판정과 독립된 오류입니다.'}]}
    _atomic_write(output, json.dumps(payload,ensure_ascii=False,indent=2)+'\n')


if __name__ == '__main__':
    record_failure(ROOT/'web/public/data/latest-momentum.json', ROOT/'web/public/data/momentum-research.json')
