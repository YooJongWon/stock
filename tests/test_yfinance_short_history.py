import pandas as pd
from providers import yfinance_provider

def test_short_but_current_history_is_returned_without_retry(monkeypatch):
    dates=pd.bdate_range("2026-09-01",periods=30)
    frame=pd.DataFrame({"Open":10,"High":11,"Low":9,"Close":10,"Volume":1_000_000},index=dates)
    class Ticker:
        def __init__(self,*args,**kwargs): pass
        def history(self,**kwargs): return frame
    monkeypatch.setattr(yfinance_provider.yf,"Ticker",Ticker)
    result=yfinance_provider.YFinanceProvider().history("NEW",dates[-1].date())
    assert len(result)==30

def test_stale_short_history_still_fails(monkeypatch):
    dates=pd.bdate_range("2026-08-01",periods=30)
    frame=pd.DataFrame({"Open":10,"High":11,"Low":9,"Close":10,"Volume":1_000_000},index=dates)
    class Ticker:
        def __init__(self,*args,**kwargs): pass
        def history(self,**kwargs): return frame
    monkeypatch.setattr(yfinance_provider.yf,"Ticker",Ticker)
    try: yfinance_provider.YFinanceProvider().history("OLD","2026-10-12")
    except RuntimeError as e: assert "stale OHLCV" in str(e)
    else: raise AssertionError("stale data should still trigger failure")
