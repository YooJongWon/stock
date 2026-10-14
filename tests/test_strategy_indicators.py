import numpy as np
import pandas as pd
import pytest
from indicators import technical_snapshot, spy_market_regime


def rising_frame(n=280):
    idx=pd.bdate_range("2025-01-01",periods=n)
    close=pd.Series(np.linspace(30,120,n),index=idx)
    frame=pd.DataFrame({"Open":close-.3,"High":close+1,"Low":close-1,"Close":close,"Volume":1_200_000},index=idx)
    return frame


def test_ema_trend_stack_rising_roc_and_rs():
    frame=rising_frame()
    t=technical_snapshot(frame,frame.index[-1].date(),spy_roc63=5,market_regime="BULL")
    assert t["ema20"]==pytest.approx(frame.Close.ewm(span=20,adjust=False).mean().iloc[-1])
    assert t["trend_stack"] is True
    assert t["sma50_rising"] is True
    assert t["roc63"]==pytest.approx((frame.Close.iloc[-1]/frame.Close.iloc[-64]-1)*100)
    assert t["relative_strength"]==pytest.approx(t["roc63"]-5)


def test_spy_regime_requires_all_three_trend_conditions():
    bull=rising_frame(280)
    assert spy_market_regime(bull,bull.index[-1].date())["market_regime"]=="BULL"
    bear=bull.copy(); bear["Close"]=np.linspace(120,30,len(bear)); bear["Open"]=bear.Close-.2; bear["High"]=bear.Close+1; bear["Low"]=bear.Close-1
    assert spy_market_regime(bear,bear.index[-1].date())["market_regime"]=="RISK_OFF"


def test_recent_volume_dryup_expansion_bull_candle_and_risk_math():
    frame=rising_frame()
    frame.iloc[-2,frame.columns.get_loc("Volume")]=500_000
    frame.iloc[-1,frame.columns.get_loc("Volume")]=2_000_000
    previous_high=frame.High.iloc[-2]
    frame.iloc[-1,frame.columns.get_loc("Open")]=frame.Close.iloc[-1]-3
    frame.iloc[-1,frame.columns.get_loc("Close")]=previous_high+1
    frame.iloc[-1,frame.columns.get_loc("High")]=previous_high+1.5
    frame.iloc[-1,frame.columns.get_loc("Low")]=previous_high-3
    t=technical_snapshot(frame,frame.index[-1].date(),spy_roc63=0)
    assert t["volume_dryup_recent"] is True
    assert t["volume_expansion"] is True
    assert t["strong_bull_candle"] is True
    assert t["distance_from_50_atr"]==pytest.approx((t["price"]-t["sma50"])/t["atr14"])
    assert t["atr_stop_pct"]==pytest.approx(t["atr14"]*1.5/t["price"]*100)
    assert t["atr_stop_price"]==pytest.approx(t["price"]-t["atr14"]*1.5)
