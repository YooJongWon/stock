"""Record a failed scheduled run without touching the last successful result."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from market_calendar import latest_completed_session

path = ROOT / "web" / "public" / "data" / "latest-run-status.json"
payload = {
    "status": "failed",
    "attempted_at": datetime.now(timezone.utc).isoformat(),
    "reference_date": str(latest_completed_session()),
    "message": "The latest automated run failed. The dashboard continues to show the last successful result.",
}
path.parent.mkdir(parents=True, exist_ok=True)
temporary = path.with_suffix(".json.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
