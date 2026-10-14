from __future__ import annotations
from datetime import date
import yfinance as yf

class YahooFundamentalProvider:
    name="yfinance_fallback"
    def get_fundamentals(self,ticker,reference_date,price):
        # Yahoo's info payload does not expose filing dates for these fields. Only use it
        # when current date equals the reference date; otherwise it could contain look-ahead.
        ref=date.fromisoformat(str(reference_date)[:10])
        if date.today()!=ref: raise ValueError("Yahoo fundamentals lack point-in-time filing dates; fallback withheld to avoid look-ahead")
        info=yf.Ticker(ticker).info
        cap=info.get("marketCap"); pe=info.get("trailingPE"); roe=info.get("returnOnEquity")
        growth=info.get("revenueGrowth")
        # Yahoo's revenueGrowth is not a 5-year CAGR, so never substitute it for that field.
        if growth is None: growth=None
        if cap is None or pe is None or roe is None: raise ValueError("Yahoo fundamentals incomplete")
        return {"market_cap":float(cap),"pe":float(pe),"roe":float(roe),"sales_growth_5y":None,
            "fundamental_source":"yfinance_fallback","fundamental_quality":"MEDIUM","market_cap_source":"yfinance_fallback",
            "available_date":str(ref),"filing_date":None}
