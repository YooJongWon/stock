import numpy as np
import pandas as pd
import pytest
from indicators import normalize_ohlcv, technical_snapshot

def sample(n=260):
    idx=pd.bdate_range("2024-01-01",periods=n)
    close=pd.Series(np.linspace(20,80,n),index=idx)
    return pd.DataFrame({"Open":close-.1,"High":close+1,"Low":close-1,"Close":close,"Volume":1_500_000},index=idx)

def test_sma_windows_and_technical_values():
    df=sample(); s=technical_snapshot(df,df.index[-1].date())
    assert s["sma20"] == pytest.approx(df.Close.iloc[-20:].mean())
    assert s["sma50"] == pytest.approx(df.Close.iloc[-50:].mean())
    assert s["sma200"] == pytest.approx(df.Close.iloc[-200:].mean())
    assert s["average_volume"] == pytest.approx(1_500_000)

def test_filter_future_duplicate_and_naive_date():
    df=sample(220); df=pd.concat([df,df.iloc[[-1]]])
    out=normalize_ohlcv(df,df.index[-1].date())
    assert len(out)==220 and out.index[-1]==df.index[-1].date()

def test_invalid_ohlcv_rejected():
    df=sample(220); df.iloc[-1,1]=df.iloc[-1,2]-1
    with pytest.raises(ValueError,match="High below Low"): normalize_ohlcv(df)
