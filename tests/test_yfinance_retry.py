import pandas as pd
from providers import yfinance_provider

def test_empty_history_is_not_retried(monkeypatch):
    calls={"n":0}
    class Ticker:
        def __init__(self,*args,**kwargs): pass
        def history(self,**kwargs):
            calls["n"]+=1
            return pd.DataFrame()
    monkeypatch.setattr(yfinance_provider.yf,"Ticker",Ticker)
    try: yfinance_provider.YFinanceProvider().history("DELISTED","2026-10-06")
    except RuntimeError as error: assert "empty OHLCV" in str(error)
    else: raise AssertionError("empty history should fail")
    assert calls["n"]==1

def test_transient_failures_allow_three_retries_with_1_2_4_second_backoff(monkeypatch):
    calls={"n":0}; delays=[]
    class Ticker:
        def __init__(self,*args,**kwargs): pass
        def history(self,**kwargs):
            calls["n"]+=1
            raise RuntimeError("temporary service error")
    monkeypatch.setattr(yfinance_provider.yf,"Ticker",Ticker)
    monkeypatch.setattr(yfinance_provider.time,"sleep",lambda value:delays.append(value))
    try: yfinance_provider.YFinanceProvider().history("RETRY","2026-10-06")
    except RuntimeError: pass
    else: raise AssertionError("transient failures should be reported")
    assert calls["n"]==4
    assert delays==[1,2,4]
