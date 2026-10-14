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
               "fundamental_unavailable":0,"data_failures":0,"spy_regime":"UNKNOWN","spy_roc63":None}
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

        for index,member in enumerate(members,1):
            ticker=member["ticker"]
            if index==1 or index%100==0 or index==len(members):
                LOG.info("Progress: %d/%d (%.1f%%), %s; %.1fs",index,len(members),100*index/max(1,len(members)),ticker,time.monotonic()-started)
            stats["universe_scanned_count"]+=1
            try:
                result=self.prices.history(ticker,reference_date)
                if result.frame is None:
                    stats["data_failures"]+=1
                    rows.append(_data_error_row(ticker,reference_date,member,result.error))
                    continue
                tech=technical_snapshot(result.frame,reference_date,spy_roc63=spy.get("spy_roc63"),market_regime=spy.get("market_regime"))
                if tech.get("reference_date") != str(reference_date):
                    stats["data_failures"]+=1
                    rows.append(_data_error_row(ticker,reference_date,member,
                        f"stale daily close: received {tech.get('reference_date')!r}, expected {reference_date}"))
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
                stats["data_failures"]+=1
                LOG.warning("%s screening failed: %s: %s",ticker,type(exc).__name__,exc)
                rows.append(_data_error_row(ticker,reference_date,member,f"{type(exc).__name__}: {exc}"))

        for index,(member,data_source,tech) in enumerate(candidates,1):
            ticker=member["ticker"]
            try:
                try:
                    info=self.instrument_lookup(ticker)
                    if not is_us_common_equity(info):
                        row=classify(ticker,tech,{"fundamental_quality":"UNAVAILABLE"},{**member,"data_source":data_source,"exchange":info.get("exchange")})
                        row["Fail Reason"]="Non-common or unverified instrument"
                        row["Technical Prefilter Pass"]=True; rows.append(row); continue
                    member={**member,"exchange":info.get("exchange") or member.get("exchange"),"name":info.get("longName") or info.get("shortName") or member.get("name")}
                except Exception as exc:
                    stats["data_failures"]+=1
                    row=classify(ticker,tech,{"fundamental_quality":"UNAVAILABLE"},{**member,"data_source":data_source})
                    row["Fail Reason"]="Instrument type verification unavailable"
                    row["Fundamental Error"]=f"{type(exc).__name__}: {exc}"
                    row["Technical Prefilter Pass"]=True; rows.append(row)
                    continue
                stats["fundamental_candidate_count"]+=1
                fundamental=self.fundamentals.get_fundamentals(ticker,member.get("cik"),reference_date,tech["price"])
                complete=(fundamental.get("fundamental_quality")!="UNAVAILABLE" and
                          all(fundamental.get(k) is not None for k in ("market_cap","pe","roe","sales_growth_5y")))
                if fundamental.get("fundamental_source")=="SEC":
                    stats["sec_api_success"]+=1
                    if complete: stats["sec_success"]+=1
                elif fundamental.get("fundamental_source")=="yfinance_fallback" and complete:
                    stats["yfinance_fundamental_success"]+=1
                if not complete:
                    stats["fundamental_unavailable"]+=1
                row=classify(ticker,tech,fundamental,{**member,"data_source":data_source})
                row["Technical Prefilter Pass"]=True; row["Fundamental Error"]=fundamental.get("error")
                rows.append(row)
            except Exception as exc:
                stats["fundamental_unavailable"]+=1
                LOG.warning("%s fundamental lookup failed: %s: %s",ticker,type(exc).__name__,exc)
                row=classify(ticker,tech,{"fundamental_quality":"UNAVAILABLE"},{**member,"data_source":data_source})
                row["Technical Prefilter Pass"]=True; row["Fundamental Error"]=f"{type(exc).__name__}: {exc}"
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
        LOG.info("Technical prefilter: %d",stats["technical_prefilter_count"])
        LOG.info("Fundamental candidates: %d (SEC %d; Yahoo %d; unavailable %d)",stats["fundamental_candidate_count"],stats["sec_success"],stats["yfinance_fundamental_success"],stats["fundamental_unavailable"])
        LOG.info("Final BUY/WATCH/REJECT: %d/%d/%d",buys,watches,stats["reject_count"])
        return rows,stats

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
        fields=[("Ticker","티커"),("Company Name","회사명"),("Price","기준봉 종가"),("Score","점수"),("RSI14","RSI14"),("Relative Strength","SPY 대비 강도"),("SMA50","SMA50"),("SMA200","SMA200"),("ATR14","ATR14"),("ATR Stop %","손절폭"),("Entry Plan","진입가 추정"),("Initial Stop","초기 손절가"),("1R","1R 위험폭"),("2R Target","2R 목표가"),("Market Regime","시장 환경"),("Final","판정"),("Fail Reason","미충족 조건")]
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
    return {"BUY":"매수","WATCH":"관심","REJECT":"제외","BULL":"상승장","RISK_OFF":"위험구간","UNKNOWN":"확인 불가"}.get(str(value),str(value))

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

