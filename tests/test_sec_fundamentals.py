from datetime import date
from providers.sec_fundamentals import SECFundamentalProvider
from fundamentals import FallbackFundamentalProvider

def test_sec_filing_cutoff_and_quarter_ytd_difference():
    rows=[{"start":"2025-01-01","end":"2025-03-31","filed":date(2025,5,1),"form":"10-Q","fy":2025,"fp":"Q1","val":20},
          {"start":"2025-01-01","end":"2025-06-30","filed":date(2025,8,1),"form":"10-Q","fy":2025,"fp":"Q2","val":45}]
    q=SECFundamentalProvider._quarters(rows)
    assert [x["quarter_value"] for x in q]==[20,25]
    fact={"units":{"USD":[{"start":"2025-01-01","end":"2025-03-31","filed":"2025-05-01","form":"10-Q","val":4},{"start":"2025-01-01","end":"2025-06-30","filed":"2025-11-01","form":"10-Q","val":9}]}}
    assert len(SECFundamentalProvider._records(fact,date(2025,10,1)))==1

def test_sec_failure_uses_fallback():
    class Fail:
        def get_fundamentals(self,*a): raise ValueError("missing SEC facts")
    class Ok:
        def get_fundamentals(self,*a): return {"fundamental_source":"yfinance_fallback","fundamental_quality":"MEDIUM"}
    assert FallbackFundamentalProvider(Fail(),Ok()).get_fundamentals("ABC","1","2026-01-01",20)["fundamental_source"]=="yfinance_fallback"

def test_sec_failure_uses_yahoo_and_never_calls_finimpulse():
    class Fail:
        def get_fundamentals(self,*a): raise ValueError("missing SEC facts")
    class Yahoo:
        def get_fundamentals(self,*a): return {"fundamental_source":"yfinance_fallback","fundamental_quality":"MEDIUM"}
    class FinImpulse:
        def get_fundamentals(self,*a): raise AssertionError("FinImpulse is not a configured source")
    result=FallbackFundamentalProvider(Fail(),Yahoo(),FinImpulse()).get_fundamentals("ABC",None,"2026-01-01",20)
    assert result["fundamental_source"]=="yfinance_fallback"

def test_both_fundamental_sources_fail():
    class Fail:
        def get_fundamentals(self,*a): raise ValueError("offline")
    result=FallbackFundamentalProvider(Fail(),Fail()).get_fundamentals("ABC","1","2026-01-01",20)
    assert result["fundamental_quality"]=="UNAVAILABLE" and result["market_cap"] is None
