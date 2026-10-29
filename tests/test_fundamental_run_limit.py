from dataclasses import replace
from types import SimpleNamespace
import pandas as pd
import screener as module
from config import SETTINGS


class FakeUniverse:
    def get(self): return [{"ticker":f"T{i:02d}","cik":"1","universe_source":"test"} for i in range(15)]

class FakePrices:
    def __init__(self): self.tickers=[]
    def history(self,ticker,ref):
        self.tickers.append(ticker)
        return SimpleNamespace(frame=pd.DataFrame(),source="fixture",error=None)

class FakeFundamentals:
    def __init__(self,unavailable=False): self.calls=0; self.unavailable=unavailable
    def get_fundamentals(self,*args):
        self.calls+=1
        if self.unavailable: return {"fundamental_quality":"UNAVAILABLE","fundamental_source":None}
        return {"market_cap":3e9,"pe":20,"roe":.2,"sales_growth_5y":.1,"fundamental_source":"SEC","fundamental_quality":"HIGH"}

def tech(ref,**kwargs):
    return {"price":20,"average_volume":2e6,"average_dollar_volume":50e6,"rsi14":62,
      "trend_stack":True,"sma50_rising":True,"relative_strength":3,"pullback_recent":True,
      "volume_dryup_recent":True,"volume_expansion":True,"strong_bull_candle":True,
      "distance_from_50_atr":1,"atr_stop_pct":3,"atr_stop_price":19,"one_r":1,
      "two_r_target":22,"market_regime":"BULL","reference_date":str(ref)}

def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(module,"technical_snapshot",lambda frame,ref,**kw:tech(ref,**kw))
    monkeypatch.setattr(module,"spy_market_regime",lambda *a,**kw:{"market_regime":"BULL","spy_roc63":.05,"reference_date":str(a[1])})
    monkeypatch.setattr(module,"is_us_common_equity",lambda info:True)
    monkeypatch.setattr(module,"SETTINGS",replace(SETTINGS,output_dir=tmp_path))

def test_screener_scans_entire_universe_and_all_eligible_fundamentals(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path); prices=FakePrices(); fundamentals=FakeFundamentals()
    runner=module.Screener(FakeUniverse(),prices,fundamentals,lambda t:{"quoteType":"EQUITY","exchange":"NMS"})
    _,stats=runner.run("2026-10-07")
    assert len(prices.tickers)==1 + 15 + len(module.SECTOR_ETFS) # SPY + listed symbols + sector ETFs
    assert fundamentals.calls==15
    assert stats["universe_scanned_count"]==15 and "stop_reason" not in stats
    assert stats["buy_count"]==15

def test_unavailable_fundamentals_do_not_abort_other_candidates(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path); prices=FakePrices(); fundamentals=FakeFundamentals(unavailable=True)
    runner=module.Screener(FakeUniverse(),prices,fundamentals,lambda t:{"quoteType":"EQUITY","exchange":"NMS"})
    _,stats=runner.run("2026-10-07")
    assert fundamentals.calls==15
    assert stats["fundamental_unavailable"]==15 and stats["universe_scanned_count"]==15
