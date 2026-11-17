"use client";

import { useEffect, useRef, useState } from "react";

type Check = { feature: string; label: string; value: number; threshold: number; direction: number; passed: boolean };
type Item = { ticker: string; name: string; exchange?: string; close: number; dollar_volume30: number; technical_pass_count: number; technical_total: number; checks: Check[]; warnings: string[]; market_cap_status: string; stage: string };
export type Observation = { version: number; status: string; reference_date?: string; research_generated_at?: string; stages: { key: string; label: string; count: number }[]; items: Item[]; diagnostics?: { ticker?: string; error: string }[]; market_cap_unknown_count?: number; known_small_cap_excluded?: number; note?: string };

function chartUrl(item: Item) {
  const exchange = item.exchange === "NYSE American" || item.exchange === "NYSE Arca" ? "AMEX" : item.exchange === "NYSE" ? "NYSE" : item.exchange === "NASDAQ" ? "NASDAQ" : null;
  return `https://kr.tradingview.com/chart/QaUkvTii/?symbol=${encodeURIComponent(`${exchange ? exchange + ":" : ""}${item.ticker.replace(/-/g,".")}`)}`;
}
const value = (name: string, v: number) => ["rsi14","rvol"].includes(name) ? `${v.toFixed(2)}${name === "rvol" ? "x" : ""}` : `${(v*100).toFixed(2)}%`;

export default function MomentumObservations({ observation, referenceDate, researchGeneratedAt, generatedAt, finalCount, validationExpectancy }: { observation?: Observation; referenceDate?: string; researchGeneratedAt?: string; generatedAt?: string; finalCount: number; validationExpectancy?: number | null }) {
  const [open,setOpen] = useState(false);
  const [search,setSearch] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const fresh = !!generatedAt && Number.isFinite(Date.parse(generatedAt)) && Date.now()-Date.parse(generatedAt)<=96*3600*1000;
  const coherent = observation?.reference_date === referenceDate && observation?.research_generated_at === researchGeneratedAt;
  const usable = !!observation && ["success","degraded"].includes(observation.status) && coherent && fresh;
  const items = usable ? observation.items : [];
  useEffect(()=>{
    if (!open) return;
    const node=dialog.current;
    const old=document.body.style.overflow;
    node?.showModal();
    document.body.style.overflow="hidden";
    return ()=>{node?.close();document.body.style.overflow=old;};
  },[open]);
  const term=search.trim().toLocaleLowerCase();
  const visible=items.filter(item=>`${item.ticker} ${item.name}`.toLocaleLowerCase().includes(term));
  return <section className="momentum-section momentum-observations"><h2>현재 기술조건 통과 · 검증 보류</h2>
    <p className="momentum-muted">현재 기준일 {referenceDate ?? "—"} · 연구 시점에 정한 유동성 상위 최대 200종목을 점검합니다. 각 단계는 바로 앞 단계를 통과한 종목만 집계합니다. 아래 목록은 학습 기술조건을 모두 통과했지만 시총·전략 검증이 남아 있는 관찰 종목이며, 현재 매수·준비 추천은 아닙니다.</p>
    {validationExpectancy != null && <p className="momentum-risk">선택 조건의 과거 검증 거래당 기대수익은 {(validationExpectancy * 100).toFixed(2)}%였습니다. 기술조건 충족이 수익성 검증 통과를 뜻하지 않습니다.</p>}
    {usable ? <><div className="momentum-stage-grid">{observation.stages.filter(stage=>stage.key!=="observations").map(stage=><div className="momentum-stage" key={stage.key}><span>{stage.label}</span><strong>{stage.count.toLocaleString("ko-KR")}종목</strong></div>)}<button className="momentum-stage momentum-stage-observe" type="button" aria-haspopup="dialog" onClick={()=>{setSearch("");setOpen(true);}}><span>기술조건 모두 통과 · 검증 보류</span><strong>{items.length}종목</strong><small>종목·통과 근거 보기 ↗</small></button><div className="momentum-stage"><span>최종 추천</span><strong>{finalCount}종목</strong></div></div>
    <p className="momentum-risk">시총 미확인 {observation.market_cap_unknown_count ?? 0}종목 · 확인된 시총 $1B 미만 제외 {observation.known_small_cap_excluded ?? 0}종목. 이 목록은 기존 과거 검증 거래 67건과 별도로 현재 가격을 점검한 결과입니다.</p>
    <p className="momentum-muted">{observation.note} 목록은 평균 거래대금 내림차순으로 정렬하며 수익 기대 순위가 아닙니다.</p></> : <p className="momentum-risk">현재 관찰 목록이 없거나 가격·연구 버전·갱신 시간을 확인하지 못했습니다. 갱신 전에는 이전 종목을 현재 후보처럼 표시하지 않습니다.</p>}
    {!!observation?.diagnostics?.length && <details><summary>가격·데이터 진단 {observation.diagnostics.length}건</summary><ul>{observation.diagnostics.slice(0,20).map((d,i)=><li key={i}>{d.ticker ? `${d.ticker}: ` : ""}{d.error}</li>)}</ul></details>}
    {open && <dialog ref={dialog} className="candidate-modal momentum-trade-dialog" aria-labelledby="momentum-observation-title" onClose={()=>{if(!dialog.current?.open)setOpen(false);}} onKeyDownCapture={event=>{if(event.key==="Escape"){event.preventDefault();dialog.current?.close();}}} onClick={event=>{if(event.target!==event.currentTarget)return;const bounds=event.currentTarget.getBoundingClientRect();if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)event.currentTarget.close();}}>
      <header className="modal-header"><div><div className="eyebrow">CURRENT TECHNICAL OBSERVATIONS</div><h2 id="momentum-observation-title">현재 기술조건 통과 · 검증 보류</h2></div><button type="button" className="modal-close" autoFocus aria-label="관찰 종목 팝업 닫기" onClick={()=>dialog.current?.close()}>×</button></header>
      <p className="momentum-muted">{referenceDate} 기준 · 기술조건을 전부 통과한 종목만 표시합니다. 학습 선택 조건의 실전 유효성은 확인되지 않았으며 시총 미확인과 과열 위험을 함께 확인하세요.</p>
      <label className="momentum-trade-search">관찰 종목 검색<input type="search" value={search} onChange={event=>setSearch(event.target.value)} placeholder="티커 또는 회사명" /></label>
      <p className="momentum-muted" aria-live="polite">{visible.length}종목 / 전체 {items.length}종목 · 회사명·티커 클릭 시 TradingView 차트 새 탭</p>
      <div className="candidate-list-table-wrap"><table className="candidate-list-table momentum-observation-table"><thead><tr><th>티커 / 회사명</th><th>기준일 종가</th><th>기술조건 통과 근거</th><th>보류·위험 사유</th></tr></thead><tbody>{visible.map(item=><tr key={item.ticker}><td><a href={chartUrl(item)} target="_blank" rel="noopener noreferrer" aria-label={`${item.name} (${item.ticker}) TradingView 차트 새 탭`}><strong>{item.ticker} ↗</strong><span>{item.name}</span></a></td><td>${item.close.toFixed(2)}<small>{item.technical_pass_count}/{item.technical_total}개 통과</small></td><td><ul>{item.checks.map(check=><li key={check.feature}>{check.label}: {value(check.feature,check.value)} {check.direction>0 ? "≥" : "≤"} {value(check.feature,check.threshold)} ✓</li>)}</ul></td><td><ul>{item.warnings.map(w=><li key={w}>{w}</li>)}</ul></td></tr>)}</tbody></table></div>
      {!visible.length && <p className="modal-empty">조건에 맞는 현재 관찰 종목이 없습니다.</p>}
    </dialog>}
  </section>;
}
