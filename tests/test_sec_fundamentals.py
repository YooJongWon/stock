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


def test_nonpositive_ttm_earnings_does_not_trigger_undated_yahoo_fallback():
    class LossMakingSEC:
        def get_fundamentals(self, *args):
            return {
                "market_cap": 3e9,
                "pe": None,
                "roe": -0.04,
                "sales_growth_5y": 0.08,
                "fundamental_source": "SEC",
                "fundamental_quality": "LOW",
                "fundamental_status": "NON_POSITIVE_TTM_EARNINGS",
                "fundamental_rejection_reason": "TTM net income is nonpositive; P/E not meaningful",
                "ttm_net_income": -20e6,
                "missing_fields": [],
            }

    class MustNotUseYahoo:
        def get_fundamentals(self, *args):
            raise AssertionError("loss-making issuer must not need an undated Yahoo fallback")

    result = FallbackFundamentalProvider(LossMakingSEC(), MustNotUseYahoo()).get_fundamentals(
        "ABC", "0000000001", "2026-10-28", 50
    )
    assert result["fundamental_status"] == "NON_POSITIVE_TTM_EARNINGS"
    assert result["pe"] is None
    assert result["market_cap"] == 3e9


def test_sec_keeps_loss_making_company_metrics_and_marks_pe_not_applicable(monkeypatch):
    from providers.sec_fundamentals import SECFundamentalProvider

    def duration(start, end, filed, form, fy, fp, value):
        return {
            "start": start, "end": end, "filed": filed, "form": form,
            "fy": fy, "fp": fp, "val": value,
        }

    net_income = [
        duration("2025-01-01", "2025-03-31", "2025-05-01", "10-Q", 2025, "Q1", -1),
        duration("2025-01-01", "2025-06-30", "2025-08-01", "10-Q", 2025, "Q2", -3),
        duration("2025-01-01", "2025-09-30", "2025-11-01", "10-Q", 2025, "Q3", -6),
        duration("2025-01-01", "2025-12-31", "2026-02-01", "10-K", 2025, "FY", -10),
        duration("2026-01-01", "2026-03-31", "2026-05-01", "10-Q", 2026, "Q1", -3),
        duration("2026-01-01", "2026-06-30", "2026-08-01", "10-Q", 2026, "Q2", -6),
    ]
    revenue = [
        duration("2020-01-01", "2020-12-31", "2021-02-15", "10-K", 2020, "FY", 100),
        duration("2025-01-01", "2025-12-31", "2026-02-15", "10-K", 2025, "FY", 150),
    ]
    equity = [
        {"end": "2024-12-31", "filed": "2025-02-15", "form": "10-K", "val": 100, "fy": 2024, "fp": "FY"},
        {"end": "2025-12-31", "filed": "2026-02-15", "form": "10-K", "val": 120, "fy": 2025, "fp": "FY"},
        {"end": "2026-06-30", "filed": "2026-08-15", "form": "10-Q", "val": 100, "fy": 2026, "fp": "Q2"},
    ]
    shares = [
        {"end": "2026-10-15", "filed": "2026-10-16", "form": "10-Q", "val": 50_000_000, "fy": 2026, "fp": "Q3"},
    ]
    facts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": revenue}},
                "NetIncomeLoss": {"units": {"USD": net_income}},
                "StockholdersEquity": {"units": {"USD": equity}},
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {"units": {"shares": shares}},
            },
        }
    }

    class Cache:
        def get(self, *args): return None
        def set(self, *args): pass

    provider = SECFundamentalProvider(
        user_agent="test-screener contact@example.test",
        cache=Cache(),
        session=object(),
        limiter=type("Limiter", (), {"wait": lambda self: None})(),
    )
    monkeypatch.setattr(provider, "_get_json", lambda *args: facts)

    result = provider.get_fundamentals("0000000001", "2026-10-28", 50.0)

    assert result["fundamental_status"] == "NON_POSITIVE_TTM_EARNINGS"
    assert result["ttm_net_income"] < 0
    assert result["market_cap"] == 2_500_000_000
    assert result["pe"] is None
    assert result["roe"] < 0
    assert result["sales_growth_5y"] > 0
    assert "pe" not in result["missing_fields"]
