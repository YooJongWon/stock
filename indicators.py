"""Validated OHLCV normalization and pure strategy indicator calculations."""
from __future__ import annotations
from datetime import date
import numpy as np
import pandas as pd

REQUIRED = ["Open", "High", "Low", "Close", "Volume"]


def normalize_ohlcv(frame: pd.DataFrame, reference_date=None) -> pd.DataFrame:
    if frame is None or frame.empty:
        raise ValueError("empty OHLCV")
    df = frame.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    lookup = {str(c).strip().lower(): c for c in df.columns}
    df = df.rename(columns={lookup[k.lower()]: k for k in REQUIRED if k.lower() in lookup})
    missing = set(REQUIRED) - set(df.columns)
    if missing:
        raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    idx = pd.to_datetime(df.index, errors="coerce")
    if idx.isna().any():
        raise ValueError("invalid dates")
    df.index = idx.date if idx.tz is None else idx.tz_convert("America/New_York").date
    df.index.name = "Date"
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for col in REQUIRED:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if reference_date is not None:
        ref = pd.Timestamp(reference_date).date()
        if any(d > ref for d in df.index):
            # Future rows are expected from providers; they are filtered from the calculation.
            df = df.loc[df.index <= ref]
    if df.empty:
        raise ValueError("no bars on or before reference date")
    if (df[REQUIRED[:4]].dropna() <= 0).any().any():
        raise ValueError("nonpositive price")
    if (df["High"].dropna() < df["Low"].dropna()).any():
        raise ValueError("High below Low")
    if (df["Volume"].dropna() < 0).any():
        raise ValueError("negative volume")
    if df[REQUIRED].isna().mean().max() > .05:
        raise ValueError("too many missing OHLCV values")
    df = df.dropna(subset=REQUIRED)
    if reference_date is not None and (pd.Timestamp(reference_date).date() - df.index[-1]).days > 7:
        raise ValueError(f"stale OHLCV: latest bar {df.index[-1]} for reference date {reference_date}")
    return df


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.astype(float).diff()
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    def wilder(series):
        out = pd.Series(np.nan, index=series.index, dtype=float)
        if len(series) <= length:
            return out
        out.iloc[length] = series.iloc[1:length + 1].mean()
        for i in range(length + 1, len(series)):
            out.iloc[i] = (out.iloc[i - 1] * (length - 1) + series.iloc[i]) / length
        return out
    avg_gain, avg_loss = wilder(gain), wilder(loss)
    result = 100 - 100 / (1 + avg_gain / avg_loss.replace(0, np.nan))
    result = result.mask((avg_loss == 0) & (avg_gain > 0), 100)
    return result.mask((avg_loss == 0) & (avg_gain == 0), 50)


def atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    prev = frame.Close.shift(1)
    tr = pd.concat([frame.High - frame.Low, (frame.High - prev).abs(), (frame.Low - prev).abs()], axis=1).max(axis=1)
    out = pd.Series(np.nan, index=frame.index, dtype=float)
    if len(tr) >= length:
        out.iloc[length - 1] = tr.iloc[:length].mean()
        for i in range(length, len(tr)):
            out.iloc[i] = (out.iloc[i - 1] * (length - 1) + tr.iloc[i]) / length
    return out


def technical_snapshot(frame: pd.DataFrame, reference_date=None, settings=None, spy_roc63=None, market_regime=None) -> dict:
    from config import SETTINGS
    s = settings or SETTINGS
    df = normalize_ohlcv(frame, reference_date)
    close, last, i = df.Close, df.iloc[-1], len(df) - 1
    ema20, ema10 = close.ewm(span=s.ema_trend, adjust=False).mean(), close.ewm(span=s.ema_entry, adjust=False).mean()
    sma20 = close.rolling(20).mean()
    sma50, sma200 = close.rolling(s.sma_pullback).mean(), close.rolling(s.sma_long).mean()
    r, a = rsi(close, s.rsi_length), atr(df, s.atr_length)
    roc = close / close.shift(s.roc_length) - 1
    vol5, vol20 = df.Volume.rolling(5).mean(), df.Volume.rolling(20).mean()
    avg_volume30 = df.Volume.rolling(30).mean()
    avg_dollar30 = (df.Close * df.Volume).rolling(30).mean()
    def val(series, pos=-1):
        return float(series.iloc[pos]) if len(series) >= abs(pos) and pd.notna(series.iloc[pos]) else None
    atr_now, sma50_now, sma200_now = val(a), val(sma50), val(sma200)
    pullback_recent = False
    if len(df) >= 3:
        for j in range(max(0, i - 2), i + 1):
            if pd.notna(sma50.iloc[j]) and pd.notna(a.iloc[j]) and df.Low.iloc[j] <= sma50.iloc[j] + s.pullback_atr_max*a.iloc[j] and df.Close.iloc[j] >= sma50.iloc[j] - s.pullback_atr_max*a.iloc[j]:
                pullback_recent = True
                break
    # A recent touch is invalid if the latest close has materially lost the 50-day average.
    if atr_now is not None and sma50_now is not None and last.Close < sma50_now - s.pullback_atr_max*atr_now:
        pullback_recent = False
    dryup_recent = any(df.Volume.iloc[j] < vol20.iloc[j]*s.volume_dryup_ratio for j in range(max(0, i-2), i+1) if pd.notna(vol20.iloc[j]))
    span = float(last.High-last.Low)
    bull = bool(i >= 1 and span > 0 and last.Close > last.Open and (last.Close-last.Open)/span >= .40 and (last.Close-last.Low)/span >= .60 and last.Close > df.High.iloc[i-1])
    volume_expansion = bool(pd.notna(vol20.iloc[-1]) and last.Volume > vol20.iloc[-1]*s.volume_expansion_ratio)
    trend_stack = bool(val(ema20) is not None and sma50_now is not None and sma200_now is not None and val(ema20)>sma50_now>sma200_now)
    rising = bool(val(sma50) is not None and val(sma50, -6) is not None and val(sma50)>val(sma50,-6))
    distance = (float(last.Close)-sma50_now)/atr_now if sma50_now is not None and atr_now else None
    stop = float(last.Close)-atr_now*s.atr_stop_mult if atr_now is not None else None
    roc_value = val(roc)
    roc_value = roc_value*100 if roc_value is not None else None
    rs = (roc_value-spy_roc63) if roc_value is not None and spy_roc63 is not None else None
    return {
        "reference_date": str(df.index[-1]), "price":float(last.Close), "open":float(last.Open), "high":float(last.High), "low":float(last.Low), "volume":float(last.Volume),
        "average_volume":val(avg_volume30), "average_dollar_volume":val(avg_dollar30), "average_volume5":val(vol5), "average_volume20":val(vol20),
        "ema10":val(ema10), "ema20":val(ema20), "sma20":val(sma20), "sma50":sma50_now, "sma200":sma200_now, "sma50_5d_ago":val(sma50,-6),
        "rsi14":val(r), "atr14":atr_now, "roc63":roc_value, "spy_roc63":spy_roc63, "relative_strength":rs, "market_regime":market_regime or "UNKNOWN",
        "atr_stop_price":stop, "atr_stop_pct":(atr_now*s.atr_stop_mult/float(last.Close)*100 if atr_now is not None else None),
        "one_r":(float(last.Close)-stop if stop is not None else None), "two_r_target":(float(last.Close)+2*(float(last.Close)-stop) if stop is not None else None),
        "distance_from_50_atr":distance, "pullback_recent":pullback_recent, "pullback":pullback_recent, "volume_dryup_recent":bool(dryup_recent),
        "volume_expansion":volume_expansion, "strong_bull_candle":bull, "trend_stack":trend_stack, "trend_ok":trend_stack,
        "sma50_rising":rising, "bar_count":len(df),
    }


def spy_market_regime(frame: pd.DataFrame, reference_date=None, settings=None) -> dict:
    from config import SETTINGS
    s = settings or SETTINGS
    df = normalize_ohlcv(frame, reference_date)
    close = df.Close
    sma50, sma200 = close.rolling(s.sma_pullback).mean(), close.rolling(s.sma_long).mean()
    bull = bool(len(df)>=s.sma_long+5 and close.iloc[-1]>sma200.iloc[-1] and sma50.iloc[-1]>sma200.iloc[-1] and sma50.iloc[-1]>sma50.iloc[-6])
    roc = float((close.iloc[-1]/close.iloc[-1-s.roc_length]-1)*100) if len(df)>s.roc_length else None
    return {"market_regime":"BULL" if bull else "RISK_OFF", "reference_date":str(df.index[-1]), "spy_roc63":roc, "spy_close":float(close.iloc[-1]), "spy_sma50":float(sma50.iloc[-1]) if pd.notna(sma50.iloc[-1]) else None, "spy_sma200":float(sma200.iloc[-1]) if pd.notna(sma200.iloc[-1]) else None}
