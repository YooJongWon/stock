from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pandas as pd
import requests

from config import SETTINGS
from indicators import normalize_ohlcv


class StooqProvider:
    name = "stooq_fallback"
    URL = "https://stooq.com/q/d/l/"

    def __init__(self, session=None, api_key=None):
        self.session = session or requests.Session()
        self.api_key = (SETTINGS.stooq_api_key if api_key is None else api_key).strip()

    def history(self, ticker: str, reference_date, period="2y"):
        if not self.api_key:
            raise RuntimeError(
                "Stooq CSV fallback requires STOOQ_API_KEY; configure it as a GitHub Actions secret"
            )

        ref = pd.Timestamp(reference_date).date()
        start = ref - timedelta(days=850)
        symbol = ticker.replace("-", ".").lower() + ".us"
        params = {
            "s": symbol,
            "d1": start.strftime("%Y%m%d"),
            "d2": ref.strftime("%Y%m%d"),
            "i": "d",
            "apikey": self.api_key,
        }
        response = self.session.get(
            self.URL,
            params=params,
            headers={"User-Agent": "USStockScreener/1.0", "Accept": "text/csv"},
            timeout=15,
        )
        response.raise_for_status()
        body = response.text.lstrip()
        if not body.startswith("Date,"):
            excerpt = " ".join(body[:180].split())
            raise ValueError(
                "Stooq did not return CSV OHLCV data (API key/quota/permission issue): "
                + (excerpt or "empty response")
            )
        raw = pd.read_csv(StringIO(response.text), parse_dates=["Date"]).set_index("Date")
        df = normalize_ohlcv(raw, reference_date)
        if len(df) < 200:
            raise ValueError("Stooq history insufficient for 200-day moving average or is stale")
        return df
