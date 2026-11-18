"use client";

import { useEffect, useRef, useState } from "react";

type Check = { feature: string; label: string; value: number; threshold: number; direction: number; passed: boolean };
type Item = { ticker: string; name: string; exchange?: string; close: number; dollar_volume30: number; technical_pass_count: number; technical_total: number; checks: Check[]; warnings: string[]; market_cap_status: string; stage: string };
export type UniverseScope = { id: string; limited: boolean; exchange_counts?: Record<string,number> };
export type Observation = { version: number; status: string; reference_date?: string; research_generated_at?: string; stages: { key: string; label: string; count: number }[]; items: Item[]; diagnostics?: { ticker?: string; error: string }[]; market_cap_unknown_count?: number; known_small_cap_excluded?: number; note?: string };

function chartUrl(item: Item) {
  const exchange = item.exchange === "NYSE American" || item.exchange === "NYSE Arca" ? "AMEX" : item.exchange === "NYSE" ? "NYSE" : item.exchange === "NASDAQ" ? "NASDAQ" : null;
  return `https://kr.tradingview.com/chart/QaUkvTii/?symbol=${encodeURIComponent(`${exchange ? exchange + ":" : ""}${item.ticker.replace(/-/g,".")}`)}`;
}
const value = (name: string, v: number) => ["rsi14","rvol"].includes(name) ? `${v.toFixed(2)}${name === "rvol" ? "x" : ""}` : `${(v*100).toFixed(2)}%`;

export default function MomentumObservations({ observation, referenceDate, researchGeneratedAt, generatedAt, finalCount, validationExpectancy, universeScope }: { observation?: Observation; referenceDate?: string; researchGeneratedAt?: string; generatedAt?: string; finalCount: number; validationExpectancy?: number | null; universeScope?: UniverseScope }) {
  const [open,setOpen] = useState(false);
  const [search,setSearch] = useState("");
  const [page,setPage] = useState(0);
  const dialog = useRef<HTMLDialogElement>(null);
  const fresh = !!generatedAt && Number.isFinite(Date.parse(generatedAt)) && Date.now()-Date.parse(generatedAt)<=96*3600*1000;
  const coherent = observation?.reference_date === referenceDate && observation?.research_generated_at === researchGeneratedAt;
  const fullScope = universeScope?.id === "us-common-nasdaq-nyse-american-v1" && universeScope.limited === false;
  const usable = fullScope && !!observation && ["success","degraded"].includes(observation.status) && coherent && fresh;
  const items = usable ? observation.items : [];
  useEffect(()=>{
    if (!open) return;
    const node=dialog.current;
    const old=document.body.style.overflow;
    node?.showModal();
    document.body.style.overflow="hidden";
    return ()=>{node?.close();document.body.style.overflow=old;};
  },[open]);
  useEffect(()=>{if(open)dialog.current?.scrollTo({top:0});},[page,open]);
  const term=search.trim().toLocaleLowerCase();
  const visible=items.filter(item=>`${item.ticker} ${item.name}`.toLocaleLowerCase().includes(term));
  const pageSize=50;
  const pageCount=Math.max(1,Math.ceil(visible.length/pageSize));
  const currentPage=Math.min(page,pageCount-1);
  const pageItems=visible.slice(currentPage*pageSize,(currentPage+1)*pageSize);
  return <>
    <button className="momentum-summary-link" type="button" aria-haspopup="dialog" onClick={()=>{setSearch("");setPage(0);setOpen(true);}}>
      <span>관찰 후보</span><strong>{usable ? `${items.length}종목` : "확인 필요"}</strong><small>현재 후보·통과 근거 보기 ↗</small>
    </button>
    {open && <dialog ref={dialog} className="candidate-modal momentum-trade-dialog" aria-labelledby="momentum-observation-title" onClose={()=>{if(!dialog.current?.open)setOpen(false);}} onKeyDownCapture={event=>{if(event.key==="Escape"){event.preventDefault();dialog.current?.close();}}} onClick={event=>{if(event.target!==event.currentTarget)return;const bounds=event.currentTarget.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)event.currentTarget.close();}}>
      <header className="modal-header"><div><div className="eyebrow">CURRENT TECHNICAL OBSERVATIONS</div><h2 id="momentum-observation-title">현재 기술조건 통과 · 검증 보류</h2></div><button type="button" className="modal-close" autoFocus aria-label="관찰 종목 팝업 닫기" onClick={()=>dialog.current?.close()}>×</button></header>
      <p className="momentum-muted">{referenceDate} 기준 · 기술조건을 전부 통과한 종목만 표시합니다. 학습 선택 조건의 실전 유효성은 확인되지 않았으며 시총 미확인과 과열 위험을 함께 확인하세요.</p>
      <p className="momentum-muted">나스닥·NYSE·NYSE American 보통주를 최신 데이터로 점검한 결과입니다. 이 종목들은 검증된 매수 추천이 아닙니다.</p>
      {!usable && <p role="status" className="momentum-risk">현재 관찰 목록의 최신성·거래소 범위·연구 버전을 확인하지 못했습니다. 오래된 종목은 표시하지 않습니다.</p>}
      {universeScope?.exchange_counts && <p className="momentum-muted">{Object.entries(universeScope.exchange_counts).map(([venue,count])=>`${venue} ${count.toLocaleString("ko-KR")}종목`).join(" · ")}</p>}
      {usable && observation && <><div className="momentum-stage-grid">{observation.stages.filter(stage=>stage.key!=="observations").map(stage=><div className="momentum-stage" key={stage.key}><span>{stage.label}</span><strong>{stage.count.toLocaleString("ko-KR")}종목</strong></div>)}<div className="momentum-stage"><span>관찰 후보</span><strong>{items.length}종목</strong></div><div className="momentum-stage"><span>최종 추천</span><strong>{finalCount}종목</strong></div></div><p className="momentum-risk">시총 미확인 {observation.market_cap_unknown_count ?? 0}종목 · 시총 $1B 미만 제외 {observation.known_small_cap_excluded ?? 0}종목</p><p className="momentum-muted">{observation.note} 거래대금순 표시이며 수익 기대 순위가 아닙니다.</p></>}
      {validationExpectancy != null && <p className="momentum-risk">선택 조건의 과거 검증 거래당 기대수익: {(validationExpectancy * 100).toFixed(2)}%. 기술조건 통과는 수익성 검증 통과를 의미하지 않습니다.</p>}
      {!!observation?.diagnostics?.length && <details><summary>가격·데이터 진단 {observation.diagnostics.length}건</summary><ul>{observation.diagnostics.slice(0,20).map((d,i)=><li key={i}>{d.ticker ? `${d.ticker}: ` : ""}{d.error}</li>)}</ul></details>}
      <label className="momentum-trade-search">관찰 종목 검색<input type="search" value={search} onChange={event=>{setSearch(event.target.value);setPage(0);}} placeholder="티커 또는 회사명" /></label>
      <p className="momentum-muted" aria-live="polite">{visible.length}종목 / 전체 {items.length}종목 · 회사명·티커 클릭 시 TradingView 차트 새 탭</p>
      <div className="candidate-list-table-wrap"><table className="candidate-list-table momentum-observation-table"><thead><tr><th>티커 / 회사명</th><th>기준일 종가</th><th>기술조건 통과 근거</th><th>보류·위험 사유</th></tr></thead><tbody>{pageItems.map(item=><tr key={item.ticker}><td><a href={chartUrl(item)} target="_blank" rel="noopener noreferrer" aria-label={`${item.name} (${item.ticker}) TradingView 차트 새 탭`}><strong>{item.ticker} ↗</strong><span>{item.name}</span></a></td><td>${item.close.toFixed(2)}<small>{item.technical_pass_count}/{item.technical_total}개 통과</small></td><td><ul>{item.checks.map(check=><li key={check.feature}>{check.label}: {value(check.feature,check.value)} {check.direction>0 ? "≥" : "≤"} {value(check.feature,check.threshold)} ✓</li>)}</ul></td><td><ul>{item.warnings.map(w=><li key={w}>{w}</li>)}</ul></td></tr>)}</tbody></table></div>
      {visible.length>pageSize && <div className="momentum-observation-pages" aria-label="관찰 목록 페이지"><button type="button" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>이전</button><span aria-live="polite">{currentPage+1} / {pageCount}페이지 · 페이지당 {pageSize}종목</span><button type="button" disabled={currentPage===pageCount-1} onClick={()=>setPage(currentPage+1)}>다음</button></div>}
      {!visible.length && <p className="modal-empty">조건에 맞는 현재 관찰 종목이 없습니다.</p>}
    </dialog>}
  </>;
}
