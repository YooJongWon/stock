from __future__ import annotations
from datetime import datetime, timezone
import json, logging, time
import pandas as pd
from config import SETTINGS
from data_provider import UniverseProvider, DataProvider
from fundamentals import FallbackFundamentalProvider
from indicators import technical_snapshot, spy_market_regime
from scoring import classify, score_snapshot
from providers.yfinance_provider import YFinanceProvider, is_us_common_equity

LOG=logging.getLogger(__name__)

SECTOR_ETFS=(
    ("XLB","소재"),("XLC","커뮤니케이션 서비스"),("XLE","에너지"),
    ("XLF","금융"),("XLI","산업재"),("XLK","정보기술"),
    ("XLP","필수소비재"),("XLRE","부동산"),("XLU","유틸리티"),
    ("XLV","헬스케어"),("XLY","임의소비재"),
)


def _price_failure_category(message):
    text=str(message).lower()
    if any(token in text for token in ("429","rate limit","too many requests")):
        return "yahoo_rate_limit"
    if any(token in text for token in ("nonpositive price","nonpositive close","nonpositive ohlc")):
        return "invalid_price_data"
    if "stale" in text or "expected" in text:
        return "stale_or_unconfirmed_close"
    if any(token in text for token in ("empty","no daily bars","no ohlcv","no data")):
        return "empty_price_history"
    if any(token in text for token in ("timeout","timed out","connection")):
        return "network_timeout_or_connection"
    return "other"


def _record_price_failure(stats, ticker, error):
    message=str(error or "Price provider returned no frame")
    stats["data_failures"]+=1
    stats["price_history_failures"]+=1
    category=_price_failure_category(message)
    categories=stats["data_failure_categories"]
    categories[category]=categories.get(category,0)+1
    if len(stats["data_failure_examples"])<12:
        stats["data_failure_examples"].append({"ticker":ticker,"stage":"price_history","category":category,"error":message[:350]})


class Screener:
    def __init__(self,universe=None,prices=None,fundamentals=None,instrument_lookup=None):
        self.universe=universe or UniverseProvider()
        self.prices=prices or DataProvider()
        self.fundamentals=fundamentals or FallbackFundamentalProvider()
        self.instrument_lookup=instrument_lookup or YFinanceProvider().instrument_info

    def run(self,reference_date,limit=None,only_ticker=None):
        started=time.monotonic(); universe_error=None
        try: members=self.universe.get()
        except Exception as exc:
            members=[]; universe_error=f"{type(exc).__name__}: {exc}"; LOG.error("Universe request failed: %s",universe_error)
        if only_ticker: members=[m for m in members if m["ticker"].upper()==only_ticker.upper()]
        if limit is not None: members=members[:limit]
        source=members[0].get("universe_source","unavailable") if members else "unavailable"
        LOG.info("Reference date: %s",reference_date); LOG.info("Total universe: %d (%s)",len(members),source)
        stats={"universe_count":len(members),"universe_scanned_count":0,"technical_prefilter_count":0,
               "fundamental_candidate_count":0,"sec_success":0,"sec_api_success":0,"yfinance_fundamental_success":0,
               "fundamental_unavailable":0,"fundamental_source_failures":0,"fundamental_incomplete":0,
               "fundamental_nonpositive_earnings":0,"fundamental_rejection_examples":[],
               "mixed_source_fundamentals":0,"fundamental_missing_fields":{}, "fundamental_failure_examples":[],
               "data_failures":0,"price_history_failures":0,"instrument_lookup_failures":0,
               "instrument_rejections":0,"instrument_lookup_examples":[],
               "data_failure_examples":[],"data_failure_categories":{},
               "spy_regime":"UNKNOWN","spy_roc63":None}
        rows=[]; candidates=[]; spy=None
        try:
            spy_result=self.prices.history("SPY",reference_date)
            if spy_result.frame is None: raise RuntimeError(spy_result.error or "SPY history unavailable")
            spy=spy_market_regime(spy_result.frame,reference_date)
            stats["spy_regime"],stats["spy_roc63"]=spy["market_regime"],spy["spy_roc63"]
            stats["spy_reference_date"]=spy.get("reference_date")
            if stats["spy_reference_date"] != str(reference_date):
                raise RuntimeError(
                    f"SPY close is stale: expected {reference_date}, received {stats['spy_reference_date']!r}"
                )
        except Exception as exc:
            raise RuntimeError(f"Cannot start screener without a confirmed SPY close for {reference_date}: {exc}") from exc

        stats["sector_performance"] = self._sector_performance(reference_date)

        for index,member in enumerate(members,1):
            ticker=member["ticker"]
            if index==1 or index%100==0 or index==len(members):
                LOG.info("Progress: %d/%d (%.1f%%), %s; %.1fs",index,len(members),100*index/max(1,len(members)),ticker,time.monotonic()-started)
            stats["universe_scanned_count"]+=1
            try:
                result=self.prices.history(ticker,reference_date)
                if result.frame is None:
                    error_text=str(result.error or "Price provider returned no frame")
                    _record_price_failure(stats,ticker,error_text)
                    rows.append(_data_error_row(ticker,reference_date,member,error_text))
                    continue
                tech=technical_snapshot(result.frame,reference_date,spy_roc63=spy.get("spy_roc63"),market_regime=spy.get("market_regime"))
                if tech.get("reference_date") != str(reference_date):
                    error_text=f"stale daily close: received {tech.get('reference_date')!r}, expected {reference_date}"
                    _record_price_failure(stats,ticker,error_text)
                    rows.append(_data_error_row(ticker,reference_date,member,error_text))
                    continue
                tech_candidate=(tech.get("price",0)>=SETTINGS.price_min and
                    tech.get("average_volume") is not None and tech["average_volume"]>=SETTINGS.avg_volume_min and
                    tech.get("average_dollar_volume") is not None and tech["average_dollar_volume"]>=SETTINGS.avg_dollar_volume_min and
                    tech.get("trend_stack") and tech.get("sma50_rising") and
                    tech.get("relative_strength") is not None and tech["relative_strength"]>0 and
                    score_snapshot(tech)>=SETTINGS.watch_score_min)
                if tech_candidate:
                    stats["technical_prefilter_count"]+=1
                    candidates.append((member,result.source,tech))
                else:
                    row=classify(ticker,tech,None,{**member,"data_source":result.source})
                    # Do not claim skipped fundamentals failed: only technical facts were evaluated.
                    untested={"Market Cap >= $2B","PE > 0","PE < 40","ROE > 15%","Sales Growth 5Y > 5%","Fundamental data unavailable"}
                    row["Fail Reason"]="; ".join(x for x in row["Fail Reason"].split("; ") if x not in untested)
                    row["Technical Prefilter Pass"]=False
                    rows.append(row)
            except Exception as exc:
                error_text=f"{type(exc).__name__}: {exc}"
                _record_price_failure(stats,ticker,error_text)
                LOG.warning("%s price screening failed: %s",ticker,error_text)
                rows.append(_data_error_row(ticker,reference_date,member,error_text))

        for index,(member,data_source,tech) in enumerate(candidates,1):
            ticker=member["ticker"]
            try:
                metadata_warning=None
                try:
                    info=self.instrument_lookup(ticker)
                    # The exchange directory is already filtered to US-listed equities.
                    # Treat Yahoo metadata as corroboration, not as a single point of failure.
                    quote_type=str((info or {}).get("quoteType") or "").upper()
                    if quote_type and quote_type != "EQUITY":
                        stats["instrument_rejections"]+=1
                        row=classify(ticker,tech,{"fundamental_quality":"UNAVAILABLE"},
                            {**member,"data_source":data_source,"exchange":(info or {}).get("exchange") or member.get("exchange")})
                        row["Fail Reason"]=f"Non-common instrument according to Yahoo quoteType={quote_type}"
                        row["Technical Prefilter Pass"]=True; rows.append(row); continue
                    if not info or not quote_type:
                        metadata_warning="Yahoo instrument metadata incomplete; trusted filtered exchange directory"
                        stats["instrument_lookup_failures"]+=1
                        if len(stats["instrument_lookup_examples"])<10:
                            stats["instrument_lookup_examples"].append({"ticker":ticker,"reason":metadata_warning})
                    member={**member,"sector":(info or {}).get("sector") or member.get("sector"),
                        "exchange":(info or {}).get("exchange") or member.get("exchange"),
                        "name":(info or {}).get("longName") or (info or {}).get("shortName") or member.get("name")}
                except Exception as exc:
                    metadata_warning=f"{type(exc).__name__}: {exc}"
                    stats["instrument_lookup_failures"]+=1
                    if len(stats["instrument_lookup_examples"])<10:
                        stats["instrument_lookup_examples"].append({"ticker":ticker,"reason":metadata_warning[:350]})
                    LOG.warning("%s Yahoo instrument metadata unavailable; continuing with exchange-directory record: %s",
                        ticker,metadata_warning)
                stats["fundamental_candidate_count"]+=1
                fundamental=self.fundamentals.get_fundamentals(ticker,member.get("cik"),reference_date,tech["price"])
                required_fields=("market_cap","pe","roe","sales_growth_5y")
                fundamental_status=str(fundamental.get("fundamental_status") or "")
                nonpositive_earnings=fundamental_status=="NON_POSITIVE_TTM_EARNINGS"
                if nonpositive_earnings:
                    stats["fundamental_nonpositive_earnings"]+=1
                    if len(stats["fundamental_rejection_examples"])<12:
                        stats["fundamental_rejection_examples"].append({
                            "ticker":ticker,
                            "reason":fundamental.get("fundamental_rejection_reason") or "TTM net income is nonpositive",
                            "ttm_net_income":fundamental.get("ttm_net_income"),
                        })
                    missing_fields=[
                        key for key in required_fields
                        if fundamental.get(key) is None and key!="pe"
                    ]
                else:
                    provider_missing=fundamental.get("missing_fields")
                    missing_fields=(
                        [key for key in provider_missing if key in required_fields]
                        if isinstance(provider_missing,list)
                        else [key for key in required_fields if fundamental.get(key) is None]
                    )
                complete=(
                    not nonpositive_earnings
                    and fundamental.get("fundamental_quality")!="UNAVAILABLE"
                    and not missing_fields
                    and all(fundamental.get(key) is not None for key in required_fields)
                )
                source=str(fundamental.get("fundamental_source") or "UNAVAILABLE")
                if source=="SEC":
                    stats["sec_api_success"]+=1
                    if complete: stats["sec_success"]+=1
                elif source=="SEC+Yahoo":
                    stats["sec_api_success"]+=1
                    if complete:
                        stats["mixed_source_fundamentals"]+=1
                        stats["yfinance_fundamental_success"]+=1
                elif source=="yfinance_fallback" and complete:
                    stats["yfinance_fundamental_success"]+=1
                source_unavailable=(not nonpositive_earnings and fundamental.get("fundamental_quality")=="UNAVAILABLE")
                if source_unavailable:
                    # A missing provider payload is not the same as several independently
                    # diagnosed field gaps. Keep those counters separate.
                    stats["fundamental_unavailable"]+=1
                    stats["fundamental_source_failures"]+=1
                elif missing_fields:
                    stats["fundamental_unavailable"]+=1
                    stats["fundamental_incomplete"]+=1
                    for key in missing_fields:
                        missing=stats["fundamental_missing_fields"]
                        missing[key]=missing.get(key,0)+1
                if not complete and not nonpositive_earnings:
                    reason=str(fundamental.get("error") or fundamental.get("warning") or "No provider error detail")
                    if fundamental.get("warning"):
                        reason += "; " + str(fundamental["warning"])
                    if fundamental.get("statement_error"):
                        reason += "; income statement: " + str(fundamental["statement_error"])
                    if len(stats["fundamental_failure_examples"])<12:
                        stats["fundamental_failure_examples"].append({
                            "ticker":ticker,"source":source,"missing_fields":missing_fields,"error":reason[:500]})
                row=classify(ticker,tech,fundamental,{**member,"data_source":data_source})
                row["Technical Prefilter Pass"]=True
                row["Fundamental Error"]=fundamental.get("error")
                if metadata_warning:
                    row["Instrument Metadata Warning"]=metadata_warning
                rows.append(row)
            except Exception as exc:
                stats["fundamental_unavailable"]+=1
                stats["fundamental_source_failures"]+=1
                error_text=f"{type(exc).__name__}: {exc}"
                LOG.warning("%s fundamental lookup failed: %s",ticker,error_text)
                if len(stats["fundamental_failure_examples"])<12:
                    stats["fundamental_failure_examples"].append({
                        "ticker":ticker,"source":"UNAVAILABLE","missing_fields":["market_cap","pe","roe","sales_growth_5y"],"error":error_text[:500]})
                row=classify(ticker,tech,{"fundamental_quality":"UNAVAILABLE"},{**member,"data_source":data_source})
                row["Technical Prefilter Pass"]=True; row["Fundamental Error"]=error_text
                rows.append(row)

        # Required order: BUY, WATCH, REJECT; BUY ranking follows requested tie-breakers.
        def sort_key(row):
            return ({"BUY":0,"WATCH":1,"REJECT":2}.get(row.get("Final"),3),
                    -(row.get("Score") or 0),-(row.get("Relative Strength") or -999),
                    row.get("ATR Stop %") if row.get("ATR Stop %") is not None else 999,
                    abs((row.get("RSI14") or 62.5)-62.5),-(row.get("Market Cap") or 0))
        rows.sort(key=sort_key)
        buys=sum(r.get("Final")=="BUY" for r in rows); watches=sum(r.get("Final")=="WATCH" for r in rows)
        stats.update({"reference_date":str(reference_date),"buy_count":buys,"watch_count":watches,
            "reject_count":len(rows)-buys-watches,"execution_seconds":round(time.monotonic()-started,3),
            "run_timestamp":datetime.now(timezone.utc).isoformat(),"universe_source":source})
        if universe_error: stats["universe_error"]=universe_error
        self._write(rows,stats)
        LOG.info("Price history failures: %d; instrument metadata warnings: %d",stats["price_history_failures"],stats["instrument_lookup_failures"])
        LOG.info("Fundamental candidates: %d (SEC %d; Yahoo/mixed %d; incomplete %d; provider failures %d)",stats["fundamental_candidate_count"],stats["sec_success"],stats["yfinance_fundamental_success"],stats["fundamental_incomplete"],stats["fundamental_source_failures"])
        LOG.info("Technical prefilter: %d",stats["technical_prefilter_count"])
        LOG.info("Final BUY/WATCH/REJECT: %d/%d/%d",buys,watches,stats["reject_count"])
        return rows,stats

    def _sector_performance(self,reference_date):
        results=[]
        for symbol,sector in SECTOR_ETFS:
            try:
                result=self.prices.history(symbol,reference_date)
                if result.frame is None or len(result.frame)<2:
                    raise ValueError(result.error or "at least two daily closes are required")
                frame=result.frame
                latest=str(frame.index[-1])[:10]
                if latest!=str(reference_date):
                    raise ValueError(f"stale ETF close: expected {reference_date}, received {latest}")
                previous=float(frame["Close"].iloc[-2])
                close=float(frame["Close"].iloc[-1])
                if previous<=0:
                    raise ValueError("previous close is not positive")
                results.append({"symbol":symbol,"sector":sector,"change_pct":round((close/previous-1)*100,2)})
            except Exception as exc:
                LOG.warning("Sector ETF %s unavailable: %s: %s",symbol,type(exc).__name__,exc)
                results.append({"symbol":symbol,"sector":sector,"change_pct":None})
        return results
    @staticmethod
    def _write(rows,stats):
        SETTINGS.output_dir.mkdir(parents=True,exist_ok=True)
        frame=pd.DataFrame(rows)
        frame.to_csv(SETTINGS.output_dir/"all_screened.csv",index=False,encoding="utf-8-sig")
        finals=frame[frame.Final.isin(["BUY","WATCH"])] if "Final" in frame else frame
        finals.to_csv(SETTINGS.output_dir/"final_candidates.csv",index=False,encoding="utf-8-sig")
        rejected=frame[frame.Final.eq("REJECT")] if "Final" in frame else frame
        rejected.to_csv(SETTINGS.output_dir/"rejected.csv",index=False,encoding="utf-8-sig")
        technical=frame[frame["Technical Prefilter Pass"].eq(True)] if "Technical Prefilter Pass" in frame else frame.iloc[0:0]
        technical.to_csv(SETTINGS.output_dir/"technical_candidates.csv",index=False,encoding="utf-8-sig")
        stats["technical_candidate_count"]=stats.get("technical_prefilter_count",0)
        (SETTINGS.output_dir/"run_summary.json").write_text(json.dumps(stats,indent=2,ensure_ascii=False),encoding="utf-8")
        Screener._write_markdown(finals,stats,SETTINGS.output_dir/"final_candidates.md",True)
        Screener._write_markdown(technical,stats,SETTINGS.output_dir/"technical_candidates.md",False)

    @staticmethod
    def _write_markdown(frame,stats,path,final):
        fields=[("Ticker","티커"),("Company Name","회사명"),("Sector","섹터"),("Price","기준봉 종가"),("Score","점수"),("RSI14","RSI14"),("Relative Strength","SPY 대비 강도"),("SMA50","SMA50"),("SMA200","SMA200"),("ATR14","ATR14"),("ATR Stop %","손절폭"),("Entry Plan","진입가 추정"),("Initial Stop","초기 손절가"),("1R","1R 위험폭"),("2R Target","2R 목표가"),("Market Regime","시장 환경"),("Final","판정"),("Fail Reason","미충족 조건")]
        selected=[f for f,_ in fields if f in frame.columns]
        labels=dict(fields)
        title="# 미국주식 스윙 스크리너 — 최종 후보" if final else "# 미국주식 스윙 스크리너 — 기술 후보"
        lines=[title,"",f"- 기준일: {stats.get('reference_date','-')}",f"- 시장 환경: {_korean(stats.get('spy_regime','UNKNOWN'))}",f"- 전체 스캔: {stats.get('universe_scanned_count',0)} / {stats.get('universe_count',0)}",f"- 기술 후보: {stats.get('technical_prefilter_count',0)}",f"- 재무 조회: {stats.get('fundamental_candidate_count',0)} (SEC 성공 {stats.get('sec_success',0)}, 조회 불가 {stats.get('fundamental_unavailable',0)})","", "진입 원칙은 다음 거래일 시가입니다. 가격·손절·목표 값은 신호봉 종가를 진입가로 가정한 추정치입니다.", "BUY는 정량 조건 통과 신호이며 수익을 보장하지 않습니다. 뉴스, 실적 발표, 갭, 거래정지 등은 별도 확인이 필요합니다.",""]
        if frame.empty:
            lines.append("조건에 맞는 결과가 없습니다." if final else "기술 필터 통과 종목이 없습니다.")
        else:
            lines += ["| " + " | ".join(labels[x] for x in selected) + " |","|"+"|".join("---" for _ in selected)+"|"]
            for _,row in frame.iterrows():
                cells=[]
                for col in selected:
                    v=row.get(col)
                    if pd.isna(v): out="—"
                    elif col in ("Price","SMA50","SMA200","ATR14","Entry Plan","Initial Stop","1R","2R Target"): out=f"${float(v):,.2f}"
                    elif col=="ATR Stop %": out=f"{float(v):.2f}%"
                    elif col=="Relative Strength": out=f"{float(v):.2f}%"
                    elif col=="RSI14": out=f"{float(v):.1f}"
                    elif col=="Final": out=_korean(v)
                    elif col=="Market Regime": out=_korean(v)
                    elif col=="Fail Reason": out=_korean_reason(str(v))
                    else: out=str(v).replace("|","\\|").replace("\n"," ")
                    cells.append(out)
                lines.append("| " + " | ".join(cells) + " |")
        path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def _data_error_row(ticker,reference_date,member,error):
    return {"Ticker":ticker,"Company Name":member.get("name"),"Reference Date":str(reference_date),"Final":"REJECT","Fail Reason":f"DATA_ERROR: {error}","Technical Prefilter Pass":False}

def _korean(value):
    return {"BUY":"매수","WATCH":"준비","REJECT":"제외","BULL":"상승장","RISK_OFF":"위험구간","UNKNOWN":"확인 불가"}.get(str(value),str(value))

def _korean_reason(value):
    labels={"Price >= $10":"주가 10달러 이상","Market Cap >= $2B":"시가총액 20억 달러 이상","PE > 0":"PE 양수",
        "PE < 40":"PE 40 미만","ROE > 15%":"ROE 15% 초과","Sales Growth 5Y > 5%":"5년 매출 성장률 5% 초과",
        "Average Volume >= 1M":"30일 평균 거래량 100만 주 이상","Average Dollar Volume >= $30M":"30일 평균 거래대금 3,000만 달러 이상",
        "Market Regime BULL":"시장 상승장 조건","Trend Stack EMA20 > SMA50 > SMA200":"EMA20>SMA50>SMA200 추세 배열",
        "SMA50 Rising":"SMA50 상승","Relative Strength > 0":"SPY 대비 상대강도 양수","RSI >= 55":"RSI 55 이상",
        "RSI < 68":"RSI 68 미만","Recent 50MA Pullback":"최근 3일 SMA50 눌림","Recent Volume Dry-up":"최근 거래량 감소",
        "Volume Expansion":"기준봉 거래량 증가","Strong Bull Candle":"강한 양봉","50MA Distance 0..2 ATR":"SMA50 이격 0~2 ATR",
        "ATR Stop <= 5%":"ATR 손절폭 5% 이하","Score >= 7":"점수 7점 이상","Fundamental data unavailable":"재무 데이터 확인 불가",
        "Instrument type verification unavailable":"종목 유형 확인 불가","Non-common or unverified instrument":"보통주가 아니거나 종목 유형 미확인"}
    return "; ".join(labels.get(x.strip(),x.strip()) for x in value.split(";"))

