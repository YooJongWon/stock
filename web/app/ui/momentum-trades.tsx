"use client";

import { useEffect, useRef, useState } from "react";

type Trade = {
  ticker: string;
  company_name: string;
  exchange: string | null;
  signal_date: string;
  entry_date: string;
  exit_date: string;
  entry: number;
  exit: number;
  return: number;
  reason: "target" | "stop" | "timeout";
};
type TradeSnapshot = { research_generated_at: string; trades: Trade[] };
type Filter = "all" | "target" | "profit" | "stop" | "timeout";
const reasons = { target: "목표 달성", stop: "손절", timeout: "기간 만료" };
const percent = (value: number) => `${value > 0 ? "+" : ""}${(value * 100).toFixed(2)}%`;
const price = (value: number) => `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function chartUrl(trade: Trade) {
  const exchange = trade.exchange === "NYSE American" || trade.exchange === "NYSE Arca" ? "AMEX"
    : trade.exchange === "NASDAQ" ? "NASDAQ" : trade.exchange === "NYSE" ? "NYSE" : null;
  // An unknown venue stays unqualified rather than silently using the wrong exchange.
  const symbol = `${exchange ? `${exchange}:` : ""}${trade.ticker.replace(/-/g, ".")}`;
  return `https://kr.tradingview.com/chart/QaUkvTii/?symbol=${encodeURIComponent(symbol)}`;
}

export default function MomentumTrades({ researchGeneratedAt, expectedCount, onClose }: { researchGeneratedAt?: string; expectedCount: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [snapshot, setSnapshot] = useState<TradeSnapshot | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const node = dialog.current;
    const previousOverflow = document.body.style.overflow;
    node?.showModal();
    document.body.style.overflow = "hidden";
    return () => { node?.close(); document.body.style.overflow = previousOverflow; };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    fetch("/data/momentum-backtest-trades.json", { cache: "no-store", signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw new Error("missing");
        const result = await response.json() as TradeSnapshot;
        if (!researchGeneratedAt || result.research_generated_at !== researchGeneratedAt || !Array.isArray(result.trades) || result.trades.length !== expectedCount) throw new Error("research mismatch");
        setSnapshot(result);
      }).catch(error => { if (error.name !== "AbortError") setError(true); });
    return () => controller.abort();
  }, [researchGeneratedAt, expectedCount]);
  const trades = snapshot?.trades ?? [];
  const matches = (trade: Trade, value: Filter) => value === "all" || (value === "profit" ? trade.return > 0 : trade.reason === value);
  const term = search.trim().toLocaleLowerCase();
  const visible = trades.filter(trade => matches(trade, filter) && `${trade.ticker} ${trade.company_name}`.toLocaleLowerCase().includes(term));
  const filters: [Filter, string][] = [["all", "전체"], ["target", "목표 달성"], ["profit", "수익 거래"], ["stop", "손절"], ["timeout", "기간 만료"]];
  return <dialog ref={dialog} className="candidate-modal momentum-trade-dialog" aria-labelledby="momentum-trade-title" aria-describedby="momentum-trade-description" onClose={() => { if (!dialog.current?.open) onClose(); }} onKeyDownCapture={event => { if (event.key === "Escape") { event.preventDefault(); dialog.current?.close(); } }} onClick={event => {
    if (event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.currentTarget.close();
  }}>
    <header className="modal-header"><div><div className="eyebrow">HISTORICAL VALIDATION TRADES</div><h2 id="momentum-trade-title">실제 검증 거래</h2></div><button type="button" className="modal-close" autoFocus aria-label="검증 거래 팝업 닫기" onClick={() => dialog.current?.close()}>×</button></header>
    <p id="momentum-trade-description" className="momentum-muted">검증에 사용된 과거 모의 거래입니다. 현재 매수·준비 추천이 아니며, 손실 거래도 포함합니다. 종목명 또는 티커를 누르면 TradingView 차트가 새 탭으로 열립니다.</p>
    {error ? <p role="alert" className="momentum-risk">거래 내역을 불러오지 못했거나 연구 버전이 일치하지 않습니다. 팝업을 닫고 새로고침 후 다시 시도하세요.</p> : !snapshot ? <p role="status">거래 내역을 불러오는 중입니다.</p> : <>
      <div className="momentum-trade-filters" role="group" aria-label="검증 거래 결과 필터">{filters.map(([value, label]) => <button type="button" key={value} aria-pressed={filter === value} onClick={() => setFilter(value)}>{label} {trades.filter(trade => matches(trade, value)).length}건</button>)}</div>
      <label className="momentum-trade-search">종목 검색<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="티커 또는 회사명" /></label>
      <p className="momentum-muted" aria-live="polite">{visible.length}건 / 전체 {trades.length}건 · {new Set(visible.map(trade => trade.ticker)).size}종목 · 동일 종목의 반복 거래는 각각 표시합니다.</p>
      <div className="candidate-list-table-wrap"><table className="candidate-list-table momentum-trade-table"><thead><tr><th>티커 / 회사명</th><th>진입일</th><th>청산일</th><th>매수가</th><th>청산가</th><th>비용 차감 손익</th><th>청산 사유</th></tr></thead><tbody>{visible.map((trade, i) => <tr key={`${trade.ticker}-${trade.entry_date}-${i}`}><td><a href={chartUrl(trade)} target="_blank" rel="noopener noreferrer" aria-label={`${trade.company_name} (${trade.ticker}) TradingView 차트 새 탭`}><strong>{trade.ticker} ↗</strong><span>{trade.company_name}</span></a></td><td>{trade.entry_date}</td><td>{trade.exit_date}</td><td>{price(trade.entry)}</td><td>{price(trade.exit)}</td><td className={trade.return > 0 ? "momentum-profit" : "momentum-loss"}>{percent(trade.return)}</td><td>{reasons[trade.reason]}</td></tr>)}</tbody></table></div>
      {!visible.length && <p className="modal-empty">조건에 맞는 과거 거래가 없습니다.</p>}
      <p className="momentum-muted">매수가·청산가는 슬리피지 반영 가격이며, 손익에는 거래비용까지 반영했습니다. 현재 차트의 가격 조정 방식은 연구 당시 가격과 다를 수 있습니다.</p>
    </>}
  </dialog>;
}
