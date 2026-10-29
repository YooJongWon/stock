from dataclasses import replace

import data_provider as data_provider_module
from config import SETTINGS
from data_provider import NasdaqTraderUniverseProvider, UniverseProvider

SAMPLE="""Nasdaq Traded|Symbol|Security Name|Listing Exchange|Market Category|ETF|Round Lot Size|Test Issue|Financial Status|CQS Symbol|NASDAQ Symbol|NextShares
Y|AAA|Acme Corp - Common Stock|Q|Q|N|100|N|N||AAA|N
Y|ETF|Sample Equity ETF|Q|Q|Y|100|N|N||ETF|N
Y|WARR|Acme Warrants|Q|Q|N|100|N|N||WARR|N
Y|PREF|Acme Series A Preferred Stock|N||N|100|N||PREF|PREF|N
Y|TEST|Test Corp - Common Stock|Q|Q|N|100|Y|N||TEST|N
Y|OUT|Out Corp - Common Stock|X||N|100|N||OUT|OUT|N
Y|PREFD|Sample Bank 5.50% Series D Preferred Stock|N||N|100|N||PREFD|PREFD|N
Y|BAC$E|Bank of America Depositary Shares, 5.875% Non-Cumulative Preferred Stock, Series E|N||N|100|N||BACpE|BAC-E|N
"""

def test_nasdaq_directory_filters_funds_and_non_common_instruments():
    items=NasdaqTraderUniverseProvider.parse(SAMPLE)
    assert [x["ticker"] for x in items]==["AAA"]
    assert items[0]["cik"] is None and items[0]["exchange"]=="NASDAQ"

def test_sec_403_falls_back_to_nasdaq_directory():
    class Response:
        text=SAMPLE
        def raise_for_status(self): pass
    class Session:
        def get(self,url,**kwargs):
            if "sec.gov" in url:
                class Forbidden:
                    def raise_for_status(self): raise RuntimeError("403")
                return Forbidden()
            return Response()
    class Cache:
        def get(self,*a): return None
        def set(self,*a): pass
    items=UniverseProvider(cache=Cache(),session=Session()).get()
    assert items[0]["ticker"]=="AAA" and items[0]["cik"] is None
    assert items[0]["universe_source"]=="Nasdaq Trader (no SEC CIK match)"

def test_sec_exchange_mapping_is_used_when_primary_mapping_fails(monkeypatch):
    # The live app must provide a descriptive SEC User-Agent. This isolated fixture
    # uses a synthetic contact string so the request path can be tested without secrets.
    monkeypatch.setattr(
        data_provider_module,
        "SETTINGS",
        replace(SETTINGS, sec_user_agent="stock-screener-test contact@example.test"),
    )
    exchange_payload={
        "fields":["cik","name","ticker","exchange"],
        "data":[[320193,"Apple Inc.","AAPL","Nasdaq"],[1045810,"NVIDIA Corp.","NVDA","Nasdaq"]],
    }
    class Response:
        def __init__(self,payload=None,text=""): self.payload=payload; self.text=text
        def raise_for_status(self): pass
        def json(self): return self.payload
    class Session:
        def get(self,url,**kwargs):
            if url.endswith("company_tickers_exchange.json"):
                return Response(exchange_payload)
            if "nasdaqtrader" in url:
                return Response(text=SAMPLE.replace("AAA|Acme Corp - Common Stock", "AAPL|Apple Inc. - Common Stock") +
                    "Y|NVDA|NVIDIA Corporation - Common Stock|Q|Q|N|100|N|N||NVDA|N\n")
            return Response(text=SAMPLE)
    class Cache:
        def get(self,*a): return None
        def set(self,*a): pass

    items=UniverseProvider(cache=Cache(),session=Session()).get()
    assert [item["ticker"] for item in items]==["AAPL","NVDA"]
    assert items[0]["cik"]=="0000320193"
    assert all(item["universe_source"]=="SEC company_tickers_exchange + Nasdaq Trader" for item in items)
