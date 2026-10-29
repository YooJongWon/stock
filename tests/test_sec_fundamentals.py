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


def test_partial_sec_result_is_preserved_and_yahoo_only_fills_missing_fields():
    class PartialSEC:
        def get_fundamentals(self, *args):
            return {
                "market_cap": 3e9,
                "pe": 22.0,
                "roe": 0.20,
                "sales_growth_5y": None,
                "fundamental_source": "SEC",
                "fundamental_quality": "LOW",
                "source_detail": "SEC companyfacts",
            }

    class Yahoo:
        def get_fundamentals(self, *args):
            return {
                "market_cap": 8e9,
                "pe": 30.0,
                "roe": 0.15,
                "sales_growth_5y": 0.08,
                "fundamental_source": "yfinance_fallback",
                "fundamental_quality": "MEDIUM",
                "source_detail": "Yahoo Finance snapshot",
            }

    result = FallbackFundamentalProvider(PartialSEC(), Yahoo()).get_fundamentals(
        "ABC", "0000000001", "2026-01-01", 50
    )

    assert result["fundamental_source"] == "SEC+Yahoo"
    assert result["market_cap"] == 3e9
    assert result["pe"] == 22.0
    assert result["roe"] == 0.20
    assert result["sales_growth_5y"] == 0.08
    assert result["fallback_fields"] == ["sales_growth_5y"]


def test_partial_sec_result_survives_yahoo_fallback_exception():
    class PartialSEC:
        def get_fundamentals(self, *args):
            return {
                "market_cap": 3e9,
                "pe": 22.0,
                "roe": 0.20,
                "sales_growth_5y": None,
                "fundamental_source": "SEC",
                "fundamental_quality": "LOW",
            }

    class FailYahoo:
        def get_fundamentals(self, *args):
            raise RuntimeError("temporarily unavailable")

    result = FallbackFundamentalProvider(PartialSEC(), FailYahoo()).get_fundamentals(
        "ABC", "0000000001", "2026-01-01", 50
    )

    assert result["market_cap"] == 3e9
    assert result["pe"] == 22.0
    assert result["fundamental_source"] == "SEC"
    assert result["fundamental_quality"] == "LOW"
    assert "temporarily unavailable" in result["error"]
