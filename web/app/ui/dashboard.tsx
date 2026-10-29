"use client";

import { useEffect, useState, type ReactNode } from "react";

type Result = {
  status: string;
  last_successful_run_at: string | null;
  data_date: string | null;
  error: string | null;
  warnings: string[];
  warning_count: number;
  buy_count?: number;
  watch_count?: number;
  ready_count?: number;
  waiting_count?: number;
  universe_scanned_count?: number;
  technical_candidate_count?: number;
  candidate_count?: number;
  fundamental_unavailable?: number;
  candidates?: Candidate[];
  technical_candidates?: Candidate[];
  waiting_candidates?: Candidate[];
  sector_performance?: { symbol: string; sector: string; change_pct: number | null }[];
};

type RunStatus = { status: string; attempted_at: string | null; reference_date: string | null; message: string | null };

function count(value: number | undefined) {
  return (typeof value === "number" && Number.isFinite(value) ? value : 0).toLocaleString("ko-KR");
}

function localDate(value: string | null) {
  if (!value) return "—";

  const date = new Date(value);

  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("ko-KR", {
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
        timeZone: "Asia/Seoul",
      }).format(date);
}

function usSessionDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(`${value}T12:00:00Z`);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("ko-KR", {
        year: "numeric",
        month: "long",
        day: "numeric",
        weekday: "long",
        timeZone: "America/New_York",
      }).format(date);
}

function markdownCells(line: string) {
  const escapedPipe = "\u0000";
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .replace(/\\\|/g, escapedPipe)
    .split("|")
    .map((cell) => cell.trim().replaceAll(escapedPipe, "|"));
}

function isTableSeparator(line: string) {
  return /^\|(?:\s*:?-+:?\s*\|)+$/.test(line.trim());
}

type Candidate = {
  Ticker?: string;
  "Company Name"?: string;
  Exchange?: string;
  Final?: string;
  Stage?: string;
  "Status Reason"?: string;
  Score?: number;
  filter_results?: Record<string, boolean>;
  [key: string]: unknown;
};
type DashboardModal = { kind: "list"; title: string; candidates: Candidate[]; description?: string } | { kind: "detail"; candidate: Candidate };

const FILTER_LABELS: Record<string, string> = {
  "Price >= $10": "주가 $10 이상",
  "Market Cap >= $2B": "시가총액 $20억 이상",
  "PE > 0": "PER 양수",
  "PE < 40": "PER 40 미만",
  "ROE > 15%": "ROE 15% 초과",
  "Sales Growth 5Y > 5%": "5년 매출 성장률 5% 초과",
  "Average Volume >= 1M": "30일 평균 거래량 100만 주 이상",
  "Average Dollar Volume >= $30M": "30일 평균 거래대금 $3,000만 이상",
  "Market Regime BULL": "시장 상승장 조건",
  "Trend Stack EMA20 > SMA50 > SMA200": "EMA20 > SMA50 > SMA200 추세 배열",
  "SMA50 Rising": "SMA50 상승",
  "Relative Strength > 0": "SPY 대비 상대강도 양수",
  "RSI >= 55": "RSI 55 이상",
  "RSI < 68": "RSI 68 미만",
  "Recent 50MA Pullback": "최근 3일 SMA50 눌림",
  "Recent Volume Dry-up": "최근 거래량 감소",
  "Volume Expansion": "기준봉 거래량 증가",
  "Strong Bull Candle": "강한 양봉",
  "50MA Distance 0..2 ATR": "SMA50 이격 0~2 ATR",
  "ATR Stop <= 5%": "ATR 손절폭 5% 이하",
  "Score >= 7": "점수 7점 이상",
};

function candidateText(candidate: Candidate, key: string) {
  const value = candidate[key];
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function candidateStage(candidate: Candidate): string {
  const stage = String(candidate.Stage || "").toUpperCase();
  if (stage) return stage;
  if (candidate.Final === "BUY") return "BUY";
  if (candidate.Final === "WATCH") return "READY";
  if (candidate.Final === "REJECT") return "REJECT";
  return "UNKNOWN";
}

function candidateStageLabel(candidate: Candidate): string {
  switch (candidateStage(candidate)) {
    case "BUY": return "매수";
    case "READY": return "준비";
    case "WAIT": return "확인 대기";
    case "REJECT": return "제외";
    default: return candidateText(candidate, "Final");
  }
}

function candidateStageClass(candidate: Candidate): string {
  switch (candidateStage(candidate)) {
    case "BUY": return "buy";
    case "READY": return "ready";
    case "WAIT": return "wait";
    case "REJECT": return "reject";
    default: return "watch";
  }
}


const SECTOR_LABELS: Record<string, string> = {
  "Basic Materials": "소재 (XLB)",
  "Materials": "소재 (XLB)",
  "Communication Services": "커뮤니케이션 서비스 (XLC)",
  "Energy": "에너지 (XLE)",
  "Financial Services": "금융 (XLF)",
  "Financials": "금융 (XLF)",
  "Industrials": "산업재 (XLI)",
  "Technology": "정보기술 (XLK)",
  "Information Technology": "정보기술 (XLK)",
  "Consumer Defensive": "필수소비재 (XLP)",
  "Consumer Staples": "필수소비재 (XLP)",
  "Real Estate": "부동산 (XLRE)",
  "Utilities": "유틸리티 (XLU)",
  "Healthcare": "헬스케어 (XLV)",
  "Health Care": "헬스케어 (XLV)",
  "Consumer Cyclical": "임의소비재 (XLY)",
  "Consumer Discretionary": "임의소비재 (XLY)",
};

function displaySector(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const sector = String(value).trim();
  return SECTOR_LABELS[sector] ?? sector;
}

function tradingViewUrl(candidate: Candidate) {
  const rawExchange = String(candidate.Exchange || "").toUpperCase();
  const exchange = rawExchange.includes("NYSE") || rawExchange === "NYQ" ? "NYSE"
    : rawExchange.includes("NASDAQ") || ["NMS", "NGM", "NCM"].includes(rawExchange) ? "NASDAQ"
    : "NASDAQ";
  return "https://kr.tradingview.com/chart/QaUkvTii/?symbol=" + encodeURIComponent(exchange + ":" + (candidate.Ticker || ""));
}
function renderMarkdown(source: string, candidates: Candidate[], onSelect?: (candidate: Candidate) => void) {
  const tickerColumn = -1;
  const byTicker = new Map(candidates.map((candidate) => [String(candidate.Ticker || ""), candidate]));
  const lines = source.split(/\r?\n/);
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      const Heading = heading[1].length === 1 ? "h2" : "h3";
      blocks.push(<Heading key={index}>{heading[2]}</Heading>);
      index += 1;
      continue;
    }

    if (line.startsWith("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = markdownCells(line);
      const tickerColumn = headers.findIndex((header) => header === "티커" || header.toLowerCase() === "ticker");
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(markdownCells(lines[index]));
        index += 1;
      }
      const sectorColumn = headers.findIndex((header) => header === "섹터" || header.toLowerCase() === "sector");
      if (sectorColumn === -1) headers.push("섹터");
      const visibleSectorColumn = sectorColumn === -1 ? headers.length - 1 : sectorColumn;
      blocks.push(
        <div className="markdown-table-wrap" key={index}>
          <table className="markdown-table">
            <thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{cell}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => {
              const rowCandidate = byTicker.get(row[tickerColumn] ?? "");
              return <tr key={rowIndex}>{headers.map((_, cellIndex) => {
                
              const rawCell =
                cellIndex === visibleSectorColumn && sectorColumn === -1
                  ? (rowCandidate ? candidateText(rowCandidate, "Sector") : "—")
                  : row[cellIndex] ?? "";
              
              const cell =
                cellIndex === visibleSectorColumn
                  ? displaySector(rawCell)
                  : rawCell;

                const candidate = cellIndex === tickerColumn ? byTicker.get(cell) : undefined;
                return candidate && onSelect
                  ? <td key={cellIndex}><button type="button" className="candidate-ticker-button" onClick={() => onSelect(candidate)}>{cell}</button></td>
                  : <td key={cellIndex}>{cell}</td>;
              })}</tr>;
            })}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("- ")) {
        items.push(lines[index].trim().slice(2));
        index += 1;
      }
      blocks.push(<ul key={index}>{items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul>);
      continue;
    }

    const paragraph = [line];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,3})\s+/.test(lines[index].trim()) && !lines[index].trim().startsWith("|") && !lines[index].trim().startsWith("- ")) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={index}>{paragraph.join(" ")}</p>);
  }

  return <div className="markdown-content">{blocks}</div>;
}

export default function Dashboard({ result, runStatus, markdown }: { result: Result; runStatus: RunStatus; markdown: string }) {
  const [activeMenu, setActiveMenu] = useState<"screener" | "calculator">("screener");
  const [modal, setModal] = useState<DashboardModal | null>(null);
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);

  const stale = now !== null && !!result.last_successful_run_at && now - Date.parse(result.last_successful_run_at) > 96 * 60 * 60 * 1000;
  const missing = result.status === "not_run" || result.status === "missing";
  const failed = runStatus.status === "failed";
  const displayedRunAt = runStatus.attempted_at ?? result.last_successful_run_at;
  const displayedSession = runStatus.reference_date ?? result.data_date;
  const candidates = result.candidates ?? [];
  const buyCandidates = candidates.filter((candidate) => candidateStage(candidate) === "BUY");
  const readyCandidates = candidates.filter((candidate) => candidateStage(candidate) === "READY");
  const finalCandidates = candidates.filter((candidate) => ["BUY", "READY"].includes(candidateStage(candidate)));
  const hasStageLists = Array.isArray(result.technical_candidates);
  const technicalCandidates = result.technical_candidates ?? [];
  const waitingCandidates = result.waiting_candidates ?? [];
  const rejectedCandidates = technicalCandidates.filter((candidate) => candidateStage(candidate) === "REJECT");
  const waitingCount = result.waiting_count ?? result.fundamental_unavailable ?? waitingCandidates.length;
  const sectorPerformance = result.sector_performance ?? [
    ["XLB", "소재"], ["XLC", "커뮤니케이션 서비스"], ["XLE", "에너지"], ["XLF", "금융"], ["XLI", "산업재"], ["XLK", "정보기술"],
    ["XLP", "필수소비재"], ["XLRE", "부동산"], ["XLU", "유틸리티"], ["XLV", "헬스케어"], ["XLY", "임의소비재"],
  ].map(([symbol, sector]) => ({ symbol, sector, change_pct: null as number | null }));

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#top"><span className="brand-mark">S</span> US EQUITY SCREENER</a>
        <nav className="menu-tabs" aria-label="주 메뉴" role="tablist">
          <button type="button" role="tab" aria-selected={activeMenu === "screener"} className={activeMenu === "screener" ? "active" : ""} onClick={() => setActiveMenu("screener")}>스크리너</button>
          <button type="button" role="tab" aria-selected={activeMenu === "calculator"} className={activeMenu === "calculator" ? "active" : ""} onClick={() => setActiveMenu("calculator")}>스윙 투자 계산기</button>
        </nav>
        <span className="market-tag"><i /> NYSE · NASDAQ</span>
      </header>

      {activeMenu === "calculator" ? <InvestmentCalculator /> : <>
      <section className="run-meta" aria-label="스크리너 실행 정보">
        <div><span>스크리너 실행 · 한국 시간</span><strong>{localDate(displayedRunAt)}</strong></div>
        <div><span>조회 대상 미국장 · 미 동부 날짜</span><strong>{usSessionDate(displayedSession)}</strong><small>정규장 종가 기준</small></div>
      </section>

      <section className="hero" id="top">
        <div className="eyebrow">RULE-BASED SWING SCREENER</div>
        <h1>미국 주식 스크리너</h1>
        <p>매수·준비·확인 대기 상태를 구분하고, 후보가 좁혀지는 과정을 확인합니다.</p>
      </section>

      <section className="sector-overview" aria-label="섹터별 ETF 등락률">
        <div className="sector-overview-heading"><div><div className="eyebrow">SECTOR PERFORMANCE</div><h2>섹터별 상승 · 하락</h2><p>미국장 기준일의 대표 섹터 ETF 등락률</p></div><span>기준일 종가</span></div>
        <div className="sector-grid">
          {sectorPerformance.map((item) => {
            const direction = item.change_pct === null ? "unknown" : item.change_pct > 0 ? "up" : item.change_pct < 0 ? "down" : "flat";
            const value = item.change_pct === null ? "자료 없음" : `${item.change_pct > 0 ? "+" : ""}${item.change_pct.toFixed(2)}%`;
            return <article className={`sector-card ${direction}`} key={item.symbol}>
              <span>{item.sector}</span><strong>{value}</strong><small>{item.symbol}</small>
            </article>;
          })}
        </div>
      </section>

      {failed && <div className="alert error"><strong>최근 자동 실행 실패</strong><span>{runStatus.message || "새 결과를 만들지 못해 마지막 정상 결과를 유지하고 있습니다."}</span><small>시도: {localDate(runStatus.attempted_at)} · 기준일 {runStatus.reference_date || "—"}</small></div>}
      {stale && <div className="alert warning"><strong>데이터가 오래됐습니다</strong><span>마지막 정상 결과 이후 4일 이상 지났습니다. 최신 거래일 데이터인지 확인하세요.</span></div>}
      {result.status === "degraded" && result.warnings?.map((warning, index) => <div className="alert warning" key={index}><strong>일부 데이터 확인 필요</strong><span>{warning}</span></div>)}
      {missing && <div className="alert info"><strong>아직 정상 실행 결과가 없습니다</strong><span>GitHub Actions에서 스크리너를 한 번 실행하면 이 화면에 결과가 표시됩니다.</span></div>}

      <section className="summary-grid" aria-label="매수 상태 요약">
        <button type="button" className="summary-card summary-card-button" aria-haspopup="dialog" onClick={() => setModal({ kind: "list", title: "매수 후보", description: "재무·유동성·기술 조건을 모두 통과한 종목입니다.", candidates: buyCandidates })}><span>매수</span><strong className="accent">{count(result.buy_count)}<em>종목</em></strong><small>모든 필수 조건 통과 · 목록 보기</small></button>
        <button type="button" className="summary-card summary-card-button" aria-haspopup="dialog" onClick={() => setModal({ kind: "list", title: "준비 후보", description: "핵심 조건은 통과했지만 일부 진입 타이밍 조건이 부족한 종목입니다.", candidates: readyCandidates })}><span>준비</span><strong>{count(result.ready_count ?? result.watch_count)}<em>종목</em></strong><small>일부 타이밍 조건 확인 필요 · 목록 보기</small></button>
        {waitingCandidates.length > 0 ? <button type="button" className="summary-card summary-card-button" aria-haspopup="dialog" onClick={() => setModal({ kind: "list", title: "확인 대기 종목", description: "기술 사전 필터를 통과했지만 재무자료가 확인되지 않아 최종 판단을 보류한 종목입니다.", candidates: waitingCandidates })}><span>확인 대기</span><strong className="warning-number">{count(waitingCount)}<em>종목</em></strong><small>필수 재무자료 확인 필요 · 목록 보기</small></button> : <article className="summary-card summary-card-muted"><span>확인 대기</span><strong className="warning-number">{count(waitingCount)}<em>종목</em></strong><small>{waitingCount > 0 ? "이전 결과에는 목록 데이터 없음 · 다음 실행 후 제공" : "재무 확인 대기 종목 없음"}</small></article>}
        <article className="summary-card"><span>전체 스캔</span><strong>{count(result.universe_scanned_count)}<em>종목</em></strong><small>미국 상장 보통주</small></article>
      </section>

      <section className="screen-flow" aria-label="후보 선별 흐름">
        <div className="screen-flow-heading"><div><div className="eyebrow">SCREENING FLOW</div><h2>후보 선별 흐름</h2><p>전체 종목에서 기술 후보를 찾고, 마지막에는 매수·준비·확인 대기·제외로 분류합니다.</p></div></div>
        <div className="screen-flow-route">
          <div className="screen-flow-step"><span>전체 스캔</span><strong>{count(result.universe_scanned_count)}</strong><small>미국 상장 보통주</small></div>
          <span className="screen-flow-arrow">→</span>
          {technicalCandidates.length > 0 ? <button type="button" className="screen-flow-step screen-flow-button" onClick={() => setModal({ kind: "list", title: "기술 후보", description: "가격·유동성·추세·상대강도·점수 사전 필터를 통과한 종목입니다. 재무 및 최종 진입 조건을 모두 통과했다는 뜻은 아닙니다.", candidates: technicalCandidates })}><span>기술 후보</span><strong>{count(result.technical_candidate_count ?? technicalCandidates.length)}</strong><small>목록 보기</small></button> : <div className="screen-flow-step"><span>기술 후보</span><strong>{count(result.technical_candidate_count)}</strong><small>현재 공개 데이터에는 상세 목록이 없습니다.</small></div>}
          <span className="screen-flow-arrow">→</span>
          <div className="screen-flow-step"><span>최종 판정 대상</span><strong>{hasStageLists ? count(technicalCandidates.length) : "—"}</strong><small>기술 후보에 재무·타이밍 조건 적용</small></div>
        </div>
        <div className="screen-flow-outcomes">
          <h3>기술 후보의 최종 상태</h3>
          <div className="screen-flow-outcome-grid">
            <button type="button" className="screen-flow-outcome stage-buy" onClick={() => setModal({ kind: "list", title: "매수 후보", description: "재무·유동성·기술 조건을 모두 통과했습니다. 실제 매수 전 뉴스·실적·갭 위험을 확인하세요.", candidates: buyCandidates })}><span>매수</span><strong>{count(result.buy_count)}</strong><small>모든 필수 조건 충족</small></button>
            <button type="button" className="screen-flow-outcome stage-ready" onClick={() => setModal({ kind: "list", title: "준비 후보", description: "핵심 조건은 통과했지만 일부 진입 타이밍 조건이 부족합니다.", candidates: readyCandidates })}><span>준비</span><strong>{count(result.ready_count ?? result.watch_count)}</strong><small>타이밍 조건 추가 확인</small></button>
            {waitingCandidates.length > 0 ? <button type="button" className="screen-flow-outcome stage-wait" onClick={() => setModal({ kind: "list", title: "확인 대기 종목", description: "기술 후보이지만 필수 재무자료를 확인하지 못해 최종 판단을 보류합니다.", candidates: waitingCandidates })}><span>확인 대기</span><strong>{count(waitingCount)}</strong><small>재무자료 확인 필요</small></button> : <article className="screen-flow-outcome stage-wait"><span>확인 대기</span><strong>{count(waitingCount)}</strong><small>{waitingCount > 0 ? "현재 데이터에는 개별 목록이 없습니다." : "재무 확인 대기 종목 없음"}</small></article>}
            {hasStageLists ? <button type="button" className="screen-flow-outcome stage-reject" onClick={() => setModal({ kind: "list", title: "최종 제외된 기술 후보", description: "기술 사전 필터는 통과했지만 재무 또는 필수 매수 조건을 충족하지 못한 종목입니다.", candidates: rejectedCandidates })}><span>제외</span><strong>{count(rejectedCandidates.length)}</strong><small>최종 필수 조건 미충족 · 목록 보기</small></button> : <article className="screen-flow-outcome stage-reject"><span>제외</span><strong>—</strong><small>새 단계 데이터 생성 후 확인 가능</small></article>}
          </div>
        </div>
        <p className="screen-flow-note"><b>매수</b>는 모든 필수 조건 충족, <b>준비</b>는 핵심 조건 충족 후 진입 타이밍 추가 확인, <b>확인 대기</b>는 기술 후보 중 재무자료 미확인, <b>제외</b>는 기술 후보였지만 최종 필수 조건 미충족을 뜻합니다. 실제 보유·주문 체결 상태는 자동 추적하지 않습니다.</p>
      </section>

      <section className="results-section">
        <div className="section-heading">
          <div><div className="eyebrow">LATEST SCREEN</div><h2>매수·준비 후보 리포트</h2><p>매수 또는 준비로 분류된 종목만 표시합니다. 확인 대기 종목은 위에서 따로 확인하세요.</p></div>
          {!missing && <a className="download" href="/data/latest-candidates.csv" download>CSV 다운로드 <span>↓</span></a>}
        </div>
        {renderMarkdown(markdown, finalCandidates, (candidate) => setModal({ kind: "detail", candidate }))}
        <CandidateModal modal={modal} onClose={() => setModal(null)} />
      </section>

      <footer><span>지표와 판정은 기존 Python 스크리너 산출값입니다.</span><span>매매 결정 전 시세와 갭 위험을 확인하세요.</span></footer>
      </>}
    </main>
  );
}

type CalculatorInputs = {
  total: string; stockCount: string; cashRatio: string; firstBuyRatio: string;
  stopLossRatio: string; firstTargetRatio: string; finalTargetRatio: string;
};

function InvestmentCalculator() {
  const [input, setInput] = useState<CalculatorInputs>({ total: "14000", stockCount: "5", cashRatio: "17", firstBuyRatio: "60", stopLossRatio: "-5", firstTargetRatio: "6", finalTargetRatio: "10" });
  const get = (key: keyof CalculatorInputs) => Number.parseFloat(input[key]) || 0;
  const total = Math.max(0, get("total"));
  const count = Math.max(1, Math.min(100, Math.floor(get("stockCount"))));
  const cashPct = Math.min(100, Math.max(0, get("cashRatio"))) / 100;
  const firstPct = Math.min(100, Math.max(0, get("firstBuyRatio"))) / 100;
  const stopPct = Math.min(0, Math.max(-100, get("stopLossRatio"))) / 100;
  const firstTargetPct = Math.max(0, get("firstTargetRatio")) / 100;
  const finalTargetPct = Math.max(0, get("finalTargetRatio")) / 100;
  const cash = total * cashPct;
  const stockPool = total - cash;
  const perStock = stockPool / count;
  const addPct = 1 - firstPct;
  const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
  const percent = (n: number) => (n * 100).toFixed(0) + "%";
  const set = (key: keyof CalculatorInputs, value: string) => setInput((old) => ({ ...old, [key]: value }));
  const fields: { key: keyof CalculatorInputs; label: string; suffix: string; min?: number; max?: number; step?: number }[] = [
    { key: "total", label: "총 투자금", suffix: "USD", min: 0, step: 100 },
    { key: "stockCount", label: "기본 종목 수", suffix: "종목", min: 1, max: 100, step: 1 },
    { key: "cashRatio", label: "현금 비중 목표", suffix: "%", min: 0, max: 100, step: 1 },
    { key: "firstBuyRatio", label: "1차 매수 비중", suffix: "%", min: 0, max: 100, step: 1 },
    { key: "stopLossRatio", label: "손절 기준", suffix: "%", min: -100, max: 0, step: 1 },
    { key: "firstTargetRatio", label: "1차 익절 기준", suffix: "%", min: 0, step: 1 },
    { key: "finalTargetRatio", label: "최종 익절 기준", suffix: "%", min: 0, step: 1 },
  ];
  return <section className="calculator-page" aria-label="스윙 투자 계산기">
    <div className="hero calculator-hero"><div className="eyebrow">POSITION SIZING</div><h1>미국주식 스윙 투자 계산기</h1><p>총 투자금과 운용 기준을 입력하면 종목별 목표 금액, 매수 금액, 손절·익절 예상액을 계산합니다.</p></div>
    <div className="calculator-layout">
      <section className="calculator-card input-card">
        <div className="calculator-section-title"><div><div className="eyebrow">YOUR PLAN</div><h2>운용 기준</h2></div><span>입력값</span></div>
        <div className="calculator-inputs">{fields.map(({ key, label, suffix, ...limits }) => <label className="calculator-field" key={key}><span>{label}</span><div className="calculator-input-wrap"><input type="number" inputMode="decimal" value={input[key]} onChange={(event) => set(key, event.target.value)} {...limits} aria-label={label} /><em>{suffix}</em></div></label>)}</div>
        <p className="calculator-note">종목당 목표 비중은 현금 목표를 제외한 투자금 기준으로 종목 수에 따라 나눕니다.</p>
      </section>
      <section className="calculator-card summary-card-large">
        <div className="calculator-section-title"><div><div className="eyebrow">AUTOMATIC SUMMARY</div><h2>자동 요약</h2></div><span>USD</span></div>
        <div className="calc-summary-grid">
          <article><span>현금 목표 금액</span><strong>{money(cash)}</strong><small>총 투자금의 {percent(cashPct)}</small></article>
          <article><span>주식 투자 목표액</span><strong>{money(stockPool)}</strong><small>현금 목표 제외</small></article>
          <article><span>종목당 목표액</span><strong>{money(perStock)}</strong><small>목표 비중 {percent(1 / count)} · {count}종목</small></article>
          <article><span>종목당 1차 매수액</span><strong>{money(perStock * firstPct)}</strong><small>목표액의 {percent(firstPct)}</small></article>
          <article><span>종목당 추가 매수 여력</span><strong>{money(perStock * addPct)}</strong><small>목표액의 {percent(addPct)}</small></article>
          <article className="negative"><span>종목당 손절 시 손실액</span><strong>{money(perStock * stopPct)}</strong><small>손절 기준 {input.stopLossRatio || "0"}%</small></article>
          <article className="positive"><span>종목당 1차 익절 예상액</span><strong>{money(perStock * firstTargetPct)}</strong><small>1차 익절 기준 {input.firstTargetRatio || "0"}%</small></article>
          <article className="positive"><span>종목당 최종 익절 예상액</span><strong>{money(perStock * finalTargetPct)}</strong><small>최종 익절 기준 {input.finalTargetRatio || "0"}%</small></article>
        </div>
      </section>
    </div>
    <section className="calculator-card allocation-card">
      <div className="calculator-section-title"><div><div className="eyebrow">CAPITAL ALLOCATION</div><h2>권장 자금 배분 예시</h2><p>종목 수는 기본 종목 수에 따라 자동 계산됩니다.</p></div></div>
      <div className="allocation-table-wrap"><table className="allocation-table">
        <thead><tr><th>구분</th><th>종목 수</th><th>종목당 목표 금액</th><th>총 금액</th><th>총 투자금 대비 비중</th></tr></thead>
        <tbody>{Array.from({ length: count }, (_, i) => <tr key={i}><td>종목 {String.fromCharCode(65 + (i % 26))}{i >= 26 ? Math.floor(i / 26) : ""}</td><td>1</td><td>{money(perStock)}</td><td>{money(perStock)}</td><td>{percent(total ? perStock / total : 0)}</td></tr>)}
          <tr className="cash-row"><td>현금</td><td>—</td><td>—</td><td>{money(cash)}</td><td>{percent(cashPct)}</td></tr><tr className="total-row"><td>합계</td><td>{count}</td><td>—</td><td>{money(stockPool + cash)}</td><td>{percent(total ? 1 : 0)}</td></tr>
        </tbody>
      </table></div>
    </section>
    <section className="calculator-card strategy-card">
      <div className="calculator-section-title"><div><div className="eyebrow">ENTRY & EXIT PLAN</div><h2>매수 / 매도 전략</h2><p>종목당 목표 금액 기준 예상 손익입니다.</p></div></div>
      <div className="allocation-table-wrap"><table className="allocation-table strategy-table">
        <thead><tr><th>구분</th><th>기준</th><th>종목당 금액 예시</th><th>예상 손익(USD)</th><th>비고</th></tr></thead>
        <tbody>
          <tr><td>신규 종목 1차 매수</td><td>{percent(firstPct)}</td><td>{money(perStock * firstPct)}</td><td>{money(perStock * firstPct)}</td><td>목표 금액 범위 안에서 조절</td></tr>
          <tr><td>추가 매수</td><td>{percent(addPct)}</td><td>{money(perStock * addPct)}</td><td>{money(perStock * addPct)}</td><td>추세 확인 후 조건 충족 시</td></tr>
          <tr className="loss-row"><td>손절</td><td>{input.stopLossRatio || "0"}%</td><td>{money(perStock)}</td><td>{money(perStock * stopPct)}</td><td>기계적으로 실행, 미련 없이</td></tr>
          <tr className="profit-row"><td>1차 익절</td><td>{input.firstTargetRatio || "0"}%</td><td>{money(perStock)}</td><td>{money(perStock * firstTargetPct)}</td><td>일부 익절 고려</td></tr>
          <tr className="profit-row"><td>최종 익절</td><td>{input.finalTargetRatio || "0"}%</td><td>{money(perStock)}</td><td>{money(perStock * finalTargetPct)}</td><td>목표 도달 시 나머지 정리</td></tr>
        </tbody>
      </table></div>
    </section>
    <footer><span>입력한 운용 기준에 따른 단순 계산 예시입니다.</span><span>실제 매매 전 주가, 수수료, 환율 및 갭 위험을 확인하세요.</span></footer>
  </section>;
}

function CandidateModal({ modal, onClose }: { modal: DashboardModal | null; onClose: () => void }) {
  if (!modal) return null;
  const title = modal.kind === "list" ? modal.title : (modal.candidate.Ticker || "종목") + " 판정 근거";
  const candidate = modal.kind === "detail" ? modal.candidate : null;
  const checks = candidate?.filter_results ?? {};
  const fundamentalUnavailable = candidate?.["Fundamental Quality"] === "UNAVAILABLE";
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="candidate-modal" role="dialog" aria-modal="true" aria-labelledby="candidate-modal-title">
      <header className="modal-header"><div><div className="eyebrow">{modal.kind === "list" ? "SCREEN RESULTS" : "SCREEN CONDITIONS"}</div><h2 id="candidate-modal-title">{title}</h2>{modal.kind === "list" && modal.description && <p className="modal-description">{modal.description}</p>}</div><button type="button" className="modal-close" onClick={onClose} aria-label="팝업 닫기">×</button></header>
      {modal.kind === "list" ? <div className="candidate-list-table-wrap">
        {modal.candidates.length ? <table className="candidate-list-table"><thead><tr><th>티커</th><th>회사명</th><th>섹터</th><th>판정</th><th>점수</th></tr></thead>
          <tbody>{modal.candidates.map((item) => <tr key={item.Ticker}>
            <td><a href={tradingViewUrl(item)} target="_blank" rel="noopener noreferrer">{item.Ticker || "—"} ↗</a></td>
            <td>{candidateText(item, "Company Name")}</td><td>{displaySector(item["Sector"])}</td>
            <td><b className={`decision ${candidateStageClass(item)}`}>{candidateStageLabel(item)}</b></td>
            <td>{candidateText(item, "Score")}</td>
          </tr>)}</tbody></table> : <p className="modal-empty">표시할 종목이 없습니다. 스크리너 실행 결과를 확인하세요.</p>}
      </div> : <div className="candidate-details">
        <div className="candidate-detail-heading"><div><strong>{candidate?.Ticker}</strong><span>{candidateText(candidate!, "Company Name")} · {candidate?.Exchange || "NASDAQ"} · {displaySector(candidate?.["Sector"])}</span></div><a className="download" href={tradingViewUrl(candidate!)} target="_blank" rel="noopener noreferrer">TradingView 차트 ↗</a></div>
        <div className="candidate-metrics">
          {[["판정", candidateStageLabel(candidate!)], ["점수", candidateText(candidate!, "Score")], ["기준봉 종가", candidateText(candidate!, "Price")], ["RSI14", candidateText(candidate!, "RSI14")], ["SPY 대비 강도", candidateText(candidate!, "Relative Strength") + "%"], ["손절폭", candidateText(candidate!, "ATR Stop %")]].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}
        </div>
        {candidate?.["Status Reason"] && <p className={`stage-reason stage-${candidateStage(candidate!).toLowerCase()}`}>{String(candidate["Status Reason"])}</p>}
        <h3>필터 판정</h3>
        {Object.keys(checks).length || fundamentalUnavailable ? <ul className="condition-list">
          {Object.entries(checks).map(([key, passed]) => {
            const marketWarning = key === "Market Regime BULL" && !passed;
            const fundamentalUnknown = fundamentalUnavailable && ["Market Cap >= $2B", "PE > 0", "PE < 40", "ROE > 15%", "Sales Growth 5Y > 5%"].includes(key);
            const state = marketWarning || fundamentalUnknown ? "warning" : passed ? "pass" : "fail";
            const status = marketWarning ? "경고" : fundamentalUnknown ? "미확인" : passed ? "통과" : "미통과";
            const label = marketWarning ? "시장 위험구간 (매수 차단 조건 아님)" : fundamentalUnknown ? `${FILTER_LABELS[key] || key} (재무자료 없음)` : FILTER_LABELS[key] || key;
            return <li className={state} key={key}><b>{status}</b><span>{label}</span></li>;
          })}
          {fundamentalUnavailable && <li className="warning"><b>미확인</b><span>재무 데이터 확인 불가</span></li>}
        </ul> : <p className="modal-empty">이 항목의 조건 상세가 결과 파일에 없습니다.</p>}
        {candidate && candidateStage(candidate) !== "WAIT" && Boolean(candidate["Fail Reason"]) && <p className="fail-reason"><strong>미충족 사유:</strong> {String(candidate["Fail Reason"])}</p>}
      </div>}
    </section>
  </div>;
}
