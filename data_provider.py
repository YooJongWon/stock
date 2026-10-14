from __future__ import annotations
import requests
import csv
import io
from config import SETTINGS
from utils.cache import JsonCache
from providers.fallback_provider import FallbackMarketDataProvider

def _canonical_ticker(value):
    return str(value or "").strip().upper().replace(".","-").replace("/","-")

class UniverseProvider:
    """SEC's public ticker/CIK mapping with an exchange-file fallback."""
    URL="https://www.sec.gov/files/company_tickers.json"
    EXCHANGE_URL="https://www.sec.gov/files/company_tickers_exchange.json"
    def __init__(self,cache=None,session=None): self.cache=cache or JsonCache(SETTINGS.cache_dir/"universe"); self.session=session or requests.Session()

    def _sec_get(self, url, cache_key):
        cached=self.cache.get("universe",cache_key,86400)
        if cached is not None: return cached
        if "example.com" in SETTINGS.sec_user_agent: raise RuntimeError("Configure SEC_USER_AGENT in .env")
        response=self.session.get(url,headers={"User-Agent":SETTINGS.sec_user_agent,
            "Accept-Encoding":"gzip, deflate","Accept":"application/json"},timeout=25)
        response.raise_for_status()
        data=response.json()
        if not isinstance(data,dict): raise ValueError("SEC ticker mapping was not a JSON object")
        self.cache.set("universe",cache_key,data)
        return data

    @staticmethod
    def _from_exchange_file(payload):
        fields=payload.get("fields",[])
        records=payload.get("data",[])
        if not isinstance(fields,list) or not isinstance(records,list):
            raise ValueError("SEC exchange ticker mapping has an unexpected schema")
        items=[]
        for record in records:
            if not isinstance(record,list) or len(record)!=len(fields): continue
            row=dict(zip(fields,record))
            ticker=str(row.get("ticker") or "").strip().upper()
            try: cik=str(int(row.get("cik"))).zfill(10)
            except (TypeError,ValueError): continue
            if not ticker or any(ch in ticker for ch in ("/","^","$")): continue
            items.append({"ticker":ticker.replace(".","-"),"cik":cik,
                "name":row.get("name"),"exchange":row.get("exchange"),
                "universe_source":"SEC company_tickers_exchange"})
        if not items: raise ValueError("SEC exchange ticker mapping contained no usable rows")
        unique={}
        for item in items: unique.setdefault(item["ticker"],item)
        return sorted(unique.values(),key=lambda item:item["ticker"])

    def get(self):
        errors=[]
        try:
            exchange_payload=self._sec_get(self.EXCHANGE_URL,"sec_company_tickers_exchange")
            sec_items=self._from_exchange_file(exchange_payload)
            source="SEC company_tickers_exchange + Nasdaq Trader"
        except Exception as exc:
            errors.append(f"SEC exchange map: {exc}")
            try:
                cached=self._sec_get(self.URL,"sec_company_tickers")
                sec_items=[]
                for x in cached.values():
                    ticker=str(x.get("ticker","")).upper().strip()
                    if ticker and not any(ch in ticker for ch in ("/","^","$")):
                        sec_items.append({"ticker":ticker.replace(".","-"),"cik":str(x.get("cik_str","")).zfill(10),
                                          "name":x.get("title"),"exchange":None,"universe_source":"SEC company_tickers + Nasdaq Trader"})
                source="SEC company_tickers + Nasdaq Trader"
            except Exception as exc:
                errors.append(f"SEC ticker map: {exc}")
                sec_items=[]; source=""
        try:
            listed=NasdaqTraderUniverseProvider(cache=self.cache,session=self.session).get()
        except Exception as exc:
            if sec_items:
                return sec_items
            raise RuntimeError(f"SEC maps unavailable ({'; '.join(errors)}); Nasdaq Trader directory failed ({exc})") from exc
        sec_by_ticker={_canonical_ticker(x["ticker"]):x for x in sec_items}
        merged=[]
        for member in listed:
            registrant=sec_by_ticker.get(_canonical_ticker(member["ticker"]))
            if registrant:
                merged.append({**member,"cik":registrant["cik"],"name":member.get("name") or registrant.get("name"),"universe_source":source})
            else:
                merged.append({**member,"cik":None,"universe_source":"Nasdaq Trader (no SEC CIK match)"})
        return merged

class NasdaqTraderUniverseProvider:
    """Free exchange directory fallback. ETF/test issues and non-common security types are omitted."""
    URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqtraded.txt"
    EXCHANGES={"N":"NYSE","Q":"NASDAQ","A":"NYSE American","P":"NYSE Arca","Z":"Cboe BZX","V":"IEX"}
    NON_COMMON=(" warrant", " warrants", " unit", " units", " right", " rights", " preferred", " depositary share", " depositary receipt", " senior note", " notes due", " debenture", " when-issued", " closed-end fund", " closed end fund", " investment company", " exchange-traded note", " exchange traded note")
    def __init__(self,cache=None,session=None): self.cache=cache or JsonCache(SETTINGS.cache_dir/"universe"); self.session=session or requests.Session()
    @classmethod
    def parse(cls,raw: str):
        reader=csv.DictReader(io.StringIO(raw),delimiter="|")
        rows=[]
        for row in reader:
            symbol=(row.get("Symbol") or "").strip().upper()
            if not symbol or symbol=="FILE CREATION TIME": continue
            # Nasdaq Trader encodes preferred share classes with '$' (for example BAC$E).
            # These are outside the requested common-stock universe and Yahoo aliases vary.
            if "$" in symbol: continue
            if (row.get("Nasdaq Traded") or "").strip()!="Y" or (row.get("ETF") or "").strip().upper()!="N" or (row.get("Test Issue") or "").strip().upper()!="N": continue
            exchange=(row.get("Listing Exchange") or "").strip().upper()
            if exchange not in cls.EXCHANGES: continue
            name=(row.get("Security Name") or "").strip()
            lname=" "+name.lower()
            if any(kind in lname for kind in cls.NON_COMMON): continue
            # Yahoo Finance uses a hyphen for several exchange share-class symbols.
            ticker=symbol.replace(".","-").replace("/","-")
            rows.append({"ticker":ticker,"cik":None,"name":name,"exchange":cls.EXCHANGES[exchange],"universe_source":"Nasdaq Trader fallback"})
        unique={r["ticker"]:r for r in rows}
        return sorted(unique.values(),key=lambda x:x["ticker"])
    def get(self):
        raw=self.cache.get("universe","nasdaqtrader_nasdaqtraded",86400)
        if raw is None:
            response=self.session.get(self.URL,headers={"User-Agent":"USStockScreener/1.0","Accept":"text/plain"},timeout=30)
            response.raise_for_status(); raw=response.text; self.cache.set("universe","nasdaqtrader_nasdaqtraded",raw)
        result=self.parse(raw)
        if not result: raise ValueError("Nasdaq Trader symbol file contained no eligible equities")
        return result

class DataProvider:
    def __init__(self,prices=None): self.prices=prices or FallbackMarketDataProvider()
    def history(self,ticker,reference_date): return self.prices.history(ticker,reference_date)
