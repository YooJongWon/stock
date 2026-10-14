from __future__ import annotations
import time
import logging
import yfinance as yf
import pandas as pd
from indicators import normalize_ohlcv

LOG=logging.getLogger(__name__)

class YFinanceProvider:
    name="yfinance"
    def __init__(self, retries=3): self.retries=retries
    def history(self, ticker: str, reference_date, period="2y"):
        errors=[]
        # `retries=3` means the initial request plus three retries (1s, 2s, 4s).
        for attempt in range(self.retries + 1):
            try:
                if attempt:
                    LOG.warning("yfinance retry %d/%d for %s",attempt,self.retries,ticker)
                # auto_adjust makes OHLC internally consistent with corporate actions.
                raw=yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True, actions=False, timeout=20)
                df=normalize_ohlcv(raw, reference_date)
                ref=pd.Timestamp(reference_date).date()
                return df
            except Exception as e:
                errors.append(f"{type(e).__name__}: {e}")
                # Empty/malformed market data and other validation failures are deterministic;
                # retrying them only delays the Stooq fallback (especially for delisted symbols).
                if isinstance(e, ValueError):
                    break
                if attempt < self.retries: time.sleep(2**attempt)
        raise RuntimeError("yfinance failed: " + " | ".join(errors))

    def instrument_info(self, ticker: str) -> dict:
        """Yahoo quote metadata is used only to exclude non-equity instruments."""
        return yf.Ticker(ticker).get_info()

def is_us_common_equity(info: dict) -> bool:
    if not info or info.get("quoteType") != "EQUITY": return False
    code=str(info.get("exchange","")).upper()
    name=str(info.get("fullExchangeName","")).upper()
    return code in {"NMS","NGM","NCM","NAS","NYQ","NYE","ASE","PCX","BTS"} or any(x in name for x in ("NASDAQ","NEW YORK STOCK EXCHANGE","NYSE AMERICAN","NYSE ARCA"))
