"""Close-of-session features; every rolling window ends at the signal session."""
import numpy as np
import pandas as pd
from indicators import rsi, atr

FEATURES = ["rsi14", "rvol", "atr_pct", "return5", "return10", "return20", "ema20_gap", "sma50_gap", "sma200_gap", "high20_gap", "high252_gap", "relative_strength", "volume_growth", "body_ratio", "upper_wick_ratio"]


def features(bars, spy):
    c, v = bars.Close, bars.Volume
    out = pd.DataFrame(index=bars.index)
    out["close"] = c
    out["dollar_volume30"] = (c * v).rolling(30).mean()
    out["rsi14"] = rsi(c)
    out["rvol"] = v / v.shift(1).rolling(20).mean().replace(0, np.nan)
    out["atr_pct"] = atr(bars) / c
    for n in (5, 10, 20):
        out[f"return{n}"] = c.pct_change(n, fill_method=None)
    out["ema20"] = c.ewm(span=20, adjust=False, min_periods=20).mean()
    out["ema20_gap"] = c / out["ema20"] - 1
    for n in (50, 200):
        out[f"sma{n}"] = c.rolling(n).mean()
        out[f"sma{n}_gap"] = c / out[f"sma{n}"] - 1
    for n in (20, 252):
        out[f"high{n}_gap"] = c / bars.High.rolling(n).max() - 1
    out["relative_strength"] = c.pct_change(20, fill_method=None) - spy.Close.pct_change(20, fill_method=None).reindex(out.index)
    out["volume_growth"] = v.rolling(5).mean() / v.shift(5).rolling(20).mean().replace(0, np.nan) - 1
    span = (bars.High - bars.Low).replace(0, np.nan)
    out["body_ratio"] = (c - bars.Open).abs() / span
    out["upper_wick_ratio"] = (bars.High - pd.concat([c, bars.Open], axis=1).max(axis=1)) / span
    return out.replace([np.inf, -np.inf], np.nan)


def session_windows(bars, spy, lookback=252, horizon=20):
    """Contiguous completed exchange sessions, not merely N available vendor rows.

    Past quality mask uses past dates only. Future quality mask censors missing labels.
    """
    position = pd.Series(np.arange(len(spy)), index=spy.index).reindex(bars.index)
    past = (position - position.shift(lookback - 1)) == lookback - 1
    future = (position.shift(-horizon) - position) == horizon
    return past, future
