from __future__ import annotations
from datetime import timedelta
from io import StringIO
import pandas as pd
import requests
from indicators import normalize_ohlcv

class StooqProvider:
    name="stooq_fallback"
    URL="https://stooq.com/q/d/l/"
    def __init__(self,session=None): self.session=session or requests.Session()
    def history(self, ticker: str, reference_date, period="2y"):
        ref=pd.Timestamp(reference_date).date()
        start=ref-timedelta(days=850)
        symbol=ticker.replace("-",".").lower()+".us"
        response=self.session.get(self.URL,params={"s":symbol,"d1":start.strftime("%Y%m%d"),"d2":ref.strftime("%Y%m%d"),"i":"d"},headers={"User-Agent":"USStockScreener/1.0"},timeout=8)
        response.raise_for_status()
        if not response.text.lstrip().startswith("Date,"):
            raise ValueError("Stooq did not return CSV OHLCV data; service may require access approval")
        raw=pd.read_csv(StringIO(response.text),parse_dates=["Date"]).set_index("Date")
        df=normalize_ohlcv(raw, reference_date)
        if len(df)<200:
            raise ValueError("Stooq history insufficient or stale")
        return df
