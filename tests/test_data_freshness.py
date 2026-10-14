from dataclasses import replace
from types import SimpleNamespace

import pandas as pd

import screener as module
from config import SETTINGS


def test_stale_ticker_close_is_recorded_as_data_error(monkeypatch, tmp_path):
    class Universe:
        def get(self):
            return [{"ticker": "OLD", "cik": None, "name": "Old Data Co"}]

    class Prices:
        def history(self, ticker, reference_date):
            return SimpleNamespace(frame=pd.DataFrame({"Close": [1]}), source="fixture", error=None)

    monkeypatch.setattr(module, "SETTINGS", replace(SETTINGS, output_dir=tmp_path))
    monkeypatch.setattr(module, "spy_market_regime", lambda *_a, **_k: {
        "market_regime": "BULL", "spy_roc63": 1, "reference_date": "2026-10-09"})
    monkeypatch.setattr(module, "technical_snapshot", lambda *_a, **_k: {
        "reference_date": "2026-10-08", "price": 25})

    rows, stats = module.Screener(universe=Universe(), prices=Prices()).run("2026-10-09")
    assert stats["data_failures"] == 1
    assert rows[0]["Final"] == "REJECT"
    assert "stale daily close" in rows[0]["Fail Reason"]
    assert stats["technical_prefilter_count"] == 0
