import pandas as pd
from indicators import technical_snapshot


def test_recent_50ma_pullback_uses_last_three_confirmed_bars():
    idx=pd.bdate_range("2024-01-01",periods=260)
    close=pd.Series(100.0,index=idx)
    df=pd.DataFrame({"Open":close-.1,"High":close+1,"Low":close-1,"Close":close,"Volume":1_000_000},index=idx)
    df.iloc[-2,df.columns.get_loc("Low")]=99.4
    snap=technical_snapshot(df,idx[-1].date())
    assert snap["pullback_recent"] is True


def test_material_close_below_sma50_invalidates_pullback():
    idx=pd.bdate_range("2024-01-01",periods=260)
    close=pd.Series(100.0,index=idx)
    df=pd.DataFrame({"Open":close-.1,"High":close+1,"Low":close-1,"Close":close,"Volume":1_000_000},index=idx)
    df.iloc[-2,df.columns.get_loc("Low")]=99.4
    df.iloc[-1,df.columns.get_loc("Close")]=98
    df.iloc[-1,df.columns.get_loc("Low")]=97
    snap=technical_snapshot(df,idx[-1].date())
    assert snap["pullback_recent"] is False
