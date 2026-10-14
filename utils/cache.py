from __future__ import annotations
import json, time, hashlib
from pathlib import Path
from typing import Any

class JsonCache:
    def __init__(self, root: Path):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
    def _path(self, namespace: str, key: str) -> Path:
        safe = hashlib.sha256(key.encode()).hexdigest()
        p = self.root / namespace / f"{safe}.json"; p.parent.mkdir(parents=True, exist_ok=True); return p
    def get(self, namespace: str, key: str, ttl_seconds: int) -> Any | None:
        p = self._path(namespace,key)
        try:
            obj=json.loads(p.read_text(encoding="utf-8"))
            if time.time()-obj["cached_at"] <= ttl_seconds: return obj["value"]
        except (OSError, ValueError, KeyError): pass
        return None
    def set(self, namespace: str, key: str, value: Any) -> None:
        p=self._path(namespace,key); tmp=p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"cached_at":time.time(),"value":value}, default=str),encoding="utf-8"); tmp.replace(p)
