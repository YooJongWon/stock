from __future__ import annotations
import argparse
from datetime import datetime
from dotenv import load_dotenv
from config import ROOT
from market_calendar import latest_completed_session
from screener import Screener
from utils.logger import configure_logging


def main(argv=None):
    load_dotenv(ROOT/".env")
    parser=argparse.ArgumentParser(description="미국주식 스윙 스크리너")
    parser.add_argument("--limit",type=int,default=None,help="테스트용 종목 수 제한")
    parser.add_argument("--ticker",type=str,default=None,help="단일 종목 분석")
    parser.add_argument("--reference-date",type=str,default=None,help="기준일 YYYY-MM-DD")
    args=parser.parse_args(argv); configure_logging()
    ref=datetime.strptime(args.reference_date,"%Y-%m-%d").date() if args.reference_date else latest_completed_session()
    rows,stats=Screener().run(ref,args.limit,args.ticker)
    print("="*40); print("미국주식 스윙 스크리너"); print("="*40)
    print(f"기준일          : {ref}\n시장 환경       : {_kr(stats.get('spy_regime'))}\n전체 종목       : {stats['universe_count']} (스캔 {stats['universe_scanned_count']})\n기술 후보       : {stats['technical_prefilter_count']}\n재무 조회       : {stats['fundamental_candidate_count']} (SEC 성공 {stats['sec_success']}, 조회 불가 {stats['fundamental_unavailable']})\n최종 매수       : {stats['buy_count']}\n관심 종목       : {stats['watch_count']}\n제외            : {stats['reject_count']}\n데이터 오류     : {stats['data_failures']}\n실행 시간       : {stats['execution_seconds']}초")
    print("\n최종 BUY 후보")
    print("티커     회사명             종가추정 점수 RSI   SPY대비  SMA50    SMA200   ATR14 손절% 진입추정 초기손절   1R     2R목표   환경")
    buys=[r for r in rows if r.get("Final")=="BUY"]
    for r in buys:
        name=(r.get("Company Name") or "")[:16]
        print(f"{r.get('Ticker',''):<8} {name:<16} ${_n(r.get('Price')):>7} {r.get('Score',0):>2} {_n(r.get('RSI14'),1):>5} {_n(r.get('Relative Strength'),2):>7}% ${_n(r.get('SMA50')):>7} ${_n(r.get('SMA200')):>7} ${_n(r.get('ATR14')):>5} {_n(r.get('ATR Stop %'),2):>4}% ${_n(r.get('Entry Plan')):>7} ${_n(r.get('Initial Stop')):>7} ${_n(r.get('1R')):>5} ${_n(r.get('2R Target')):>7} {_kr(r.get('Market Regime'))}")
    print(f"\n결과 폴더: {ROOT/'output'}")
    print(f"최종 후보: {ROOT/'output'/'final_candidates.csv'}")
    print(f"요약: {ROOT/'output'/'run_summary.json'}")
    return 2 if stats.get("universe_error") else 0

def _n(value,digits=2):
    return f"{float(value):,.{digits}f}" if value is not None else "N/A"

def _kr(value): return {"BULL":"상승장","RISK_OFF":"위험구간","UNKNOWN":"확인 불가"}.get(value or "UNKNOWN",value)

if __name__=="__main__": raise SystemExit(main())
