from __future__ import annotations
from datetime import date
import requests
from config import SETTINGS
from utils.cache import JsonCache
from utils.rate_limiter import RateLimiter

REVENUE_TAGS=("RevenueFromContractWithCustomerExcludingAssessedTax","Revenues","SalesRevenueNet")
NET_INCOME_TAGS=("NetIncomeLoss","ProfitLoss")
EQUITY_TAGS=("StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
SHARES_TAGS=("EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding")

class SECFundamentalProvider:
    name="SEC"
    def __init__(self, user_agent=None, cache=None, session=None, limiter=None):
        self.user_agent=user_agent or SETTINGS.sec_user_agent
        self.cache=cache or JsonCache(SETTINGS.cache_dir/"sec")
        self.session=session or requests.Session()
        self.limiter=limiter or RateLimiter(SETTINGS.sec_requests_per_second)
    def _get_json(self,url,cache_key,ttl):
        hit=self.cache.get("facts",cache_key,ttl)
        if hit is not None: return hit
        if "example.com" in self.user_agent:
            raise RuntimeError("Set SEC_USER_AGENT to a descriptive app name and contact email in .env")
        self.limiter.wait()
        response=self.session.get(url,headers={"User-Agent":self.user_agent,"Accept-Encoding":"gzip, deflate"},timeout=25)
        response.raise_for_status(); data=response.json(); self.cache.set("facts",cache_key,data); return data
    @staticmethod
    def _facts(facts, tags):
        for namespace in ("us-gaap","dei"):
            obj=facts.get(namespace,{})
            for tag in tags:
                if tag in obj: return tag,obj[tag]
        return None,None
    @staticmethod
    def _records(fact, ref):
        if not fact: return []
        out=[]
        for unit,items in fact.get("units",{}).items():
            for x in items:
                try:
                    filed=date.fromisoformat(x["filed"]); end=date.fromisoformat(x["end"])
                    if filed<=ref and x.get("form") in ("10-K","10-Q","20-F","40-F"):
                        out.append({**x,"filed":filed,"end":end,"unit":unit})
                except (ValueError,KeyError): continue
            if out: break
        return out
    @staticmethod
    def _quarters(records):
        """Extract discrete quarters from duration facts; YTD values are differenced within FY."""
        normalized=[]
        for item in records:
            try:
                r=dict(item)
                if isinstance(r.get("end"),str): r["end"]=date.fromisoformat(r["end"])
                if isinstance(r.get("filed"),str): r["filed"]=date.fromisoformat(r["filed"])
                normalized.append(r)
            except ValueError:
                continue
        durations=[r for r in normalized if r.get("start") and 70 <= (r["end"]-date.fromisoformat(r["start"])).days <= 380]
        candidates=[]
        for r in durations:
            days=(r["end"]-date.fromisoformat(r["start"])).days
            if 70<=days<=110: candidates.append({**r,"quarter_value":float(r["val"])})
            elif 150<=days<=290 and r.get("fp") in ("Q2","Q3"):
                year_q1=[x for x in durations if x.get("fy")==r.get("fy") and x.get("fp")=="Q1" and x["end"]<r["end"] and 70<=(x["end"]-date.fromisoformat(x["start"])).days<=110]
                if year_q1:
                    prev=max(year_q1,key=lambda x:x["end"])
                    candidates.append({**r,"quarter_value":float(r["val"])-float(prev["val"])})
            elif 240<=days<=380 and r.get("fp")=="FY":
                prior=[x for x in durations if x.get("fy")==r.get("fy") and x.get("fp")=="Q3" and x["end"]<r["end"]]
                if prior:
                    prev=max(prior,key=lambda x:x["end"])
                    candidates.append({**r,"quarter_value":float(r["val"])-float(prev["val"])})
        # Per quarter end, preserve the latest filing known as of reference date.
        by_end={}
        for q in candidates:
            old=by_end.get(q["end"])
            if old is None or q["filed"]>old["filed"]: by_end[q["end"]]=q
        ordered=sorted(by_end.values(),key=lambda q:q["end"])
        # Convert YTD records to discrete-quarter date spans as well as values.
        for i,item in enumerate(ordered):
            if i and 70 <= (item["end"]-ordered[i-1]["end"]).days <= 110:
                item["period_start"] = ordered[i-1]["end"].toordinal()+1
                item["period_start"] = date.fromordinal(item["period_start"])
            elif item.get("start"):
                item["period_start"] = date.fromisoformat(item["start"]) if isinstance(item["start"],str) else item["start"]
        return ordered
    def get_fundamentals(self,cik, reference_date, price):
        ref=date.fromisoformat(str(reference_date)[:10]); cik=str(cik).zfill(10)
        facts=self._get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",cik,86400)
        tag_rev,rev_obj=self._facts(facts.get("facts",{}),REVENUE_TAGS)
        tag_ni,ni_obj=self._facts(facts.get("facts",{}),NET_INCOME_TAGS)
        tag_eq,eq_obj=self._facts(facts.get("facts",{}),EQUITY_TAGS)
        _,shares_obj=self._facts(facts.get("facts",{}),SHARES_TAGS)
        rev=self._records(rev_obj,ref); ni=self._records(ni_obj,ref); eq=self._records(eq_obj,ref); shares=self._records(shares_obj,ref)
        rev_q=self._quarters(rev); ni_q=self._quarters(ni)
        if len(ni_q)<4: raise ValueError("SEC has fewer than four usable discrete net-income quarters")
        trailing=ni_q[-4:]
        if (trailing[-1]["end"]-trailing[0]["end"]).days>430: raise ValueError("SEC TTM periods are not contiguous enough")
        ttm_ni=sum(q["quarter_value"] for q in trailing)
        if ttm_ni<=0: raise ValueError("TTM net income is nonpositive; P/E not meaningful")
        eq_inst=sorted((x for x in eq if not x.get("start")),key=lambda x:x["end"])
        if not eq_inst: raise ValueError("SEC stockholders equity unavailable")
        latest_eq=eq_inst[-1]
        prior_eq=[x for x in eq_inst if x["end"]<trailing[0]["end"]]
        start_equity=prior_eq[-1]["val"] if prior_eq else None
        # Need opening and closing equity to compute average-equity ROE without inventing a value.
        roe=None
        if start_equity is not None and float(start_equity)>0 and float(latest_eq["val"])>0:
            roe=ttm_ni/((float(start_equity)+float(latest_eq["val"]))/2)
        annual={}
        for x in rev:
            days=(x["end"]-date.fromisoformat(x["start"])).days if x.get("start") else 0
            if x.get("fp")=="FY" and days>=330:
                old=annual.get(x["end"].year)
                if old is None or x["filed"]>old["filed"]: annual[x["end"].year]=x
        years=sorted(annual)
        sales_growth=None; sales_period=None
        if years:
            latest=years[-1]; target=min(years,key=lambda y:abs(y-(latest-5)))
            if latest-target>=4 and latest-target<=6 and float(annual[target]["val"])>0 and float(annual[latest]["val"])>0:
                period=latest-target
                sales_growth=(float(annual[latest]["val"])/float(annual[target]["val"]))**(1/period)-1
                sales_period={"latest_period_end":str(annual[latest]["end"]),"latest_filing_date":str(annual[latest]["filed"]),"base_period_end":str(annual[target]["end"]),"base_filing_date":str(annual[target]["filed"]),"tag":tag_rev}
        valid_shares=[x for x in shares if not x.get("start")]
        latest_share_record=max(valid_shares,key=lambda x:(x["end"],x["filed"])) if valid_shares else None
        latest_shares=float(latest_share_record["val"]) if latest_share_record else None
        market_cap=float(price)*latest_shares if latest_shares and price else None
        market_cap_source="SEC" if market_cap else None
        if not market_cap:
            raise ValueError("SEC shares outstanding unavailable; market cap cannot be calculated without dated shares")
        latest_revenue=max(rev_q,key=lambda x:(x["end"],x["filed"])) if rev_q else None
        latest_net_income=max(trailing,key=lambda x:(x["end"],x["filed"]))
        return {"market_cap":market_cap,"pe":market_cap/ttm_ni,"roe":roe,"sales_growth_5y":sales_growth,
          "fundamental_source":"SEC","fundamental_quality":"HIGH" if roe is not None and sales_growth is not None else "LOW",
          "market_cap_source":market_cap_source,"tags":{"revenue":tag_rev,"net_income":tag_ni,"equity":tag_eq},
          "ttm_net_income":ttm_ni,"ttm_period_end":str(trailing[-1]["end"]),"filing_date":str(max(q["filed"] for q in trailing)),
          "period_start":str(trailing[0].get("period_start",trailing[0]["end"])),"period_end":str(trailing[-1]["end"]),
          "form":latest_net_income.get("form"),"fundamental_basis":"SEC companyfacts; filing_date <= reference_date",
          "source_detail":"SEC EDGAR XBRL companyfacts", "equity_period_end":str(latest_eq["end"]),
          "shares_period_end":str(latest_share_record["end"]) if latest_share_record else None,
          "shares_filing_date":str(latest_share_record["filed"]) if latest_share_record else None,
          "revenue_period_end":str(latest_revenue["end"]) if latest_revenue else None,
          "sales_growth_periods":sales_period}
