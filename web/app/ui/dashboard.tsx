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
  fundamental_nonpositive_earnings?: number;
  fundamental_diagnostics_count?: number;
  fundamental_diagnostics?: FundamentalDiagnostic[];
  fundamental_missing_fields?: Record<string, number>;
  candidates?: Candidate[];
  technical_candidates?: Candidate[];
  waiting_candidates?: Candidate[];
  sector_performance?: { symbol: string; sector: string; change_pct: number | null }[];
};

type RunStatus = { status: string; attempted_at: string | null; reference_date: string | null; message: string | null };
type FundamentalDiagnostic = {
  ticker: string;
  company_name?: string | null;
  exchange?: string | null;
  reference_date: string;
  source?: string | null;
  quality?: string | null;
  status?: string | null;
  missing_fields: string[];
  field_diagnostics?: Record<string, {
    reason?: string;
    attempted_tags?: string[];
    extension_tags?: string[];
    filing_lookup_error?: string;
    yahoo_fallback_status?: string;
    yahoo_fallback_error?: string;
    filings_checked?: { form?: string; filed?: string; period?: string | null; accession?: string }[];
  }>;
  sec_status?: string;
  yahoo_status?: string;
  sec_tags?: Record<string, unknown>;
  extension_filings?: { form?: string; filed?: string; period?: string | null; accession?: string }[];
  filing_date?: string | null;
  ttm_period_end?: string | null;
  equity_period_end?: string | null;
  shares_period_end?: string | null;
  shares_filing_date?: string | null;
  revenue_period_end?: string | null;
  error?: string | null;
  warning?: string | null;
  statement_error?: string | null;
};

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
  const [activeMenu, setActiveMenu] = useState<"screener" | "calculator" | "fundamentals">("screener");
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
          <button type="button" role="tab" aria-selected={activeMenu === "fundamentals"} className={activeMenu === "fundamentals" ? "active" : ""} onClick={() => setActiveMenu("fundamentals")}>재무 데이터 진단</button>
        </nav>
        <span className="market-tag"><i /> NYSE · NASDAQ</span>
      </header>

      {activeMenu === "calculator" ? <InvestmentCalculator /> : activeMenu === "fundamentals" ? <FundamentalDiagnostics result={result} /> : <>
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
      {(result.fundamental_nonpositive_earnings ?? 0) > 0 && <div className="alert info"><strong>재무 조건에 따른 제외</strong><span>TTM 순이익이 0 이하인 {count(result.fundamental_nonpositive_earnings)}개 종목은 PER을 의미 있게 계산할 수 없어 매수 후보에서 제외했습니다. 이는 데이터 조회 실패가 아닙니다.</span></div>}
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

type DiagnosticFieldKey = "market_cap" | "pe" | "roe" | "sales_growth_5y";
const DIAGNOSTIC_FIELD_LABELS: Record<DiagnosticFieldKey, string> = {
  market_cap: "시가총액",
  pe: "PER",
  roe: "ROE",
  sales_growth_5y: "5년 매출 성장률",
};

function FundamentalDiagnostics({ result }: { result: Result }) {
  const diagnostics = result.fundamental_diagnostics ?? [];
  const [query, setQuery] = useState("");
  const [fieldFilter, setFieldFilter] = useState<"all" | DiagnosticFieldKey>("all");
  const [statusFilter, setStatusFilter] = useState<"all" | "WITHHELD" | "FAILED" | "SUCCESS" | "NOT_NEEDED">("all");

  const filtered = diagnostics.filter((item) => {
    const normalizedQuery = query.trim().toLowerCase();
    const matchesQuery = !normalizedQuery
      || item.ticker.toLowerCase().includes(normalizedQuery)
      || String(item.company_name ?? "").toLowerCase().includes(normalizedQuery);
    const matchesField = fieldFilter === "all" || item.missing_fields.includes(fieldFilter);
    const matchesStatus = statusFilter === "all"
      || (statusFilter === "WITHHELD" ? item.yahoo_status === "WITHHELD"
        : statusFilter === "FAILED" ? item.yahoo_status === "FAILED" || item.sec_status === "FAILED"
          : statusFilter === "SUCCESS" ? item.yahoo_status === "SUCCESS"
            : item.yahoo_status === "NOT_NEEDED");
    return matchesQuery && matchesField && matchesStatus;
  });

  const counts: Record<DiagnosticFieldKey, number> = {
    market_cap: 0, pe: 0, roe: 0, sales_growth_5y: 0,
  };
  diagnostics.forEach((item) => item.missing_fields.forEach((field) => {
    if (field in counts) counts[field as DiagnosticFieldKey] += 1;
  }));

  const downloadUrl = "/data/latest-fundamental-diagnostics.csv";
  const statusLabel = (item: FundamentalDiagnostic) => {
    if (item.yahoo_status === "WITHHELD") return "Yahoo 보충 보류";
    if (item.yahoo_status === "FAILED" || item.sec_status === "FAILED") return "데이터 제공자 오류";
    if (item.missing_fields.length) return "필드 미확인";
    return "확인 필요";
  };

  return <section className="diagnostics-page">
    <section className="hero diagnostics-hero">
      <div className="eyebrow">FUNDAMENTAL DATA QUALITY</div>
      <h1>재무 데이터 진단</h1>
      <p>기술 사전 필터를 통과한 종목 중 필수 재무 필드가 비어 있는 원인과 SEC 공시 근거를 확인합니다.</p>
    </section>

    <section className="diagnostics-summary">
      <article className="diagnostic-summary-card"><span>재무 진단 대상</span><strong>{count(result.fundamental_diagnostics_count ?? diagnostics.length)}<em>종목</em></strong><small>최종 매수 기준을 임의로 변경하지 않습니다.</small></article>
      {(Object.keys(DIAGNOSTIC_FIELD_LABELS) as DiagnosticFieldKey[]).map((field) =>
        <article className="diagnostic-summary-card" key={field}>
          <span>{DIAGNOSTIC_FIELD_LABELS[field]} 누락</span>
          <strong>{count(counts[field])}<em>건</em></strong>
          <small>종목별 중복 누락 포함</small>
        </article>
      )}
    </section>

    <section className="diagnostics-panel">
      <div className="diagnostics-heading">
        <div><div className="eyebrow">DIAGNOSTIC RECORDS</div><h2>종목별 상세 진단</h2>
          <p>기준일 이후 공시나 확인되지 않은 추정값은 재무 지표에 사용하지 않습니다.</p>
        </div>
        <a className="download" href={downloadUrl} download>진단 CSV 다운로드 <span>↓</span></a>
      </div>

      <div className="diagnostics-filters">
        <label><span>종목 검색</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="티커 또는 회사명" /></label>
        <label><span>누락 필드</span><select value={fieldFilter} onChange={(event) => setFieldFilter(event.target.value as typeof fieldFilter)}>
          <option value="all">전체 필드</option>
          {(Object.keys(DIAGNOSTIC_FIELD_LABELS) as DiagnosticFieldKey[]).map((field) => <option value={field} key={field}>{DIAGNOSTIC_FIELD_LABELS[field]}</option>)}
        </select></label>
        <label><span>조회 상태</span><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}>
          <option value="all">전체 상태</option><option value="WITHHELD">Yahoo 보충 보류</option><option value="FAILED">제공자 오류</option><option value="SUCCESS">Yahoo 보충 성공</option><option value="NOT_NEEDED">Yahoo 불필요</option>
        </select></label>
      </div>

      {diagnostics.length === 0 ? <div className="diagnostics-empty">
        <strong>아직 재무 진단 데이터가 없습니다.</strong>
        <p>새 스크리너 실행부터 종목별 필드 누락 사유와 SEC 원본 공시 진단이 저장됩니다.</p>
      </div> : filtered.length === 0 ? <div className="diagnostics-empty"><strong>검색 조건에 맞는 종목이 없습니다.</strong></div> : <>
        <div className="diagnostics-table-wrap">
          <table className="diagnostics-table">
            <thead><tr><th>티커</th><th>누락 필드</th><th>출처</th><th>SEC / Yahoo</th><th>진단 근거</th></tr></thead>
            <tbody>{filtered.map((item) => <tr key={item.ticker}>
              <td><strong>{item.ticker}</strong><small>{item.company_name || "회사명 미확인"}</small></td>
              <td><div className="diagnostic-field-pills">{item.missing_fields.map((field) =>
                <span key={field}>{DIAGNOSTIC_FIELD_LABELS[field as DiagnosticFieldKey] ?? field}</span>
              )}</div></td>
              <td>{item.source || "UNAVAILABLE"}<small>{item.quality || "품질 미분류"}</small></td>
              <td>{item.sec_status || "—"} / {item.yahoo_status || "—"}<small>{statusLabel(item)}</small></td>
              <td><details className="diagnostic-detail">
                <summary>공시·오류 상세 보기</summary>
                <div className="diagnostic-detail-body">
                  {item.missing_fields.map((field) => {
                    const detail = item.field_diagnostics?.[field];
                    return <section key={field}>
                      <strong>{DIAGNOSTIC_FIELD_LABELS[field as DiagnosticFieldKey] ?? field}</strong>
                      <p>{detail?.reason || "필드 누락 원인을 추가로 수집하지 못했습니다."}</p>
                      {detail?.attempted_tags?.length ? <p><b>표준 XBRL 태그:</b> {detail.attempted_tags.join(", ")}</p> : null}
                      {detail?.extension_tags?.length ? <p><b>확인된 확장 태그:</b> {detail.extension_tags.join(", ")}</p> : null}
                      {detail?.filings_checked?.length ? <p><b>조회한 공시:</b> {detail.filings_checked.map((filing) => `${filing.form || "공시"} · 제출 ${filing.filed || "—"} · 기간 ${filing.period || "—"}`).join(" / ")}</p> : null}
                      {detail?.yahoo_fallback_error ? <p><b>Yahoo 보충 오류:</b> {detail.yahoo_fallback_error}</p> : null}
                      {detail?.filing_lookup_error ? <p><b>SEC 원문 조회 오류:</b> {detail.filing_lookup_error}</p> : null}
                    </section>;
                  })}
                  <p><b>SEC 공시 날짜:</b> {item.filing_date || "—"} · <b>TTM 기간 종료:</b> {item.ttm_period_end || "—"}</p>
                  <p><b>주식 수 공시:</b> {item.shares_filing_date || "—"} · <b>매출 기간:</b> {item.revenue_period_end || "—"}</p>
                  {item.error ? <p><b>수집 오류:</b> {item.error}</p> : null}
                </div>
              </details></td>
            </tr>)}</tbody>
          </table>
        </div>
        <p className="diagnostics-result-count">{count(filtered.length)} / {count(diagnostics.length)} 종목 표시</p>
      </>}
      <div className="diagnostics-note">진단 대상은 기술 사전 필터를 통과해 재무 조회까지 진행한 종목입니다. 전체 상장 종목의 모든 재무 누락을 의미하지 않으며, 매수·준비·제외 판정 기준은 기존 설정 그대로 적용됩니다.</div>
    </section>
  </section>;
}

type CalculatorInputs = {
  total: string; stockCount: string; cashRatio: string; firstBuyRatio: string;
  stopLossRatio: string; firstTargetRatio: string; finalTargetRatio: string;
  firstEntryPrice: string;
};

const CALCULATOR_STORAGE_KEY = "jong9-stock-swing-calculator-v1";
const DEFAULT_CALCULATOR_INPUTS: CalculatorInputs = {
  total: "14000", stockCount: "5", cashRatio: "17", firstBuyRatio: "60",
  stopLossRatio: "-5", firstTargetRatio: "8", finalTargetRatio: "10",
  firstEntryPrice: "100",
};

function InvestmentCalculator() {
  const [input, setInput] = useState<CalculatorInputs>(DEFAULT_CALCULATOR_INPUTS);
  const [storageReady, setStorageReady] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(CALCULATOR_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Partial<CalculatorInputs>;
        const restored = { ...DEFAULT_CALCULATOR_INPUTS };
        (Object.keys(restored) as (keyof CalculatorInputs)[]).forEach((key) => {
          const value = parsed[key];
          if (typeof value === "string" && value.trim() !== "" && Number.isFinite(Number(value))) {
            restored[key] = value;
          }
        });
        setInput(restored);
        setSaved(true);
      }
    } catch {
      // Storage may be unavailable; the calculator remains usable.
    } finally {
      setStorageReady(true);
    }
  }, []);

  useEffect(() => {
    if (!storageReady) return;
    try {
      window.localStorage.setItem(CALCULATOR_STORAGE_KEY, JSON.stringify(input));
      setSaved(true);
    } catch {
      setSaved(false);
    }
  }, [input, storageReady]);

  const resetInputs = () => {
    setInput(DEFAULT_CALCULATOR_INPUTS);
    try {
      window.localStorage.removeItem(CALCULATOR_STORAGE_KEY);
      setSaved(false);
    } catch {
      setSaved(false);
    }
  };
  const get = (key: keyof CalculatorInputs) => Number.parseFloat(input[key]) || 0;
  const total = Math.max(0, get("total"));
  const count = Math.max(1, Math.min(100, Math.floor(get("stockCount"))));
  const cashPct = Math.min(100, Math.max(0, get("cashRatio"))) / 100;
  const firstPct = Math.min(100, Math.max(0, get("firstBuyRatio"))) / 100;
  const secondPct = 1 - firstPct;
  const stopPct = Math.min(0, Math.max(-100, get("stopLossRatio"))) / 100;
  const firstTargetPct = Math.max(0, get("firstTargetRatio")) / 100;
  const secondTargetPct = 0.09;
  const finalTargetPct = Math.max(0, get("finalTargetRatio")) / 100;
  const firstEntryPrice = Math.max(0, get("firstEntryPrice"));
  const secondEntryPrice = firstEntryPrice * 1.05;
  const cash = total * cashPct;
  const stockPool = total - cash;
  const perStock = stockPool / count;
  const firstBuyAmount = perStock * firstPct;
  const secondBuyAmount = perStock * secondPct;
  const firstShares = firstEntryPrice > 0 ? firstBuyAmount / firstEntryPrice : 0;
  const secondShares = secondEntryPrice > 0 ? secondBuyAmount / secondEntryPrice : 0;
  const totalShares = firstShares + secondShares;
  const averagePrice = totalShares > 0 ? perStock / totalShares : 0;
  const stopPrice = averagePrice * (1 + stopPct);
  const target8Price = averagePrice * (1 + firstTargetPct);
  const target9Price = averagePrice * (1 + secondTargetPct);
  const target10Price = averagePrice * (1 + finalTargetPct);
  const money = (n: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(n);
  const price = (n: number) => n > 0 ? "$" + n.toFixed(2) : "—";
  const percent = (n: number) => (n * 100).toFixed(0) + "%";
  const set = (key: keyof CalculatorInputs, value: string) => setInput((old) => ({ ...old, [key]: value }));
  const fields: { key: keyof CalculatorInputs; label: string; suffix: string; min?: number; max?: number; step?: number }[] = [
    { key: "total", label: "총 투자금", suffix: "USD", min: 0, step: 100 },
    { key: "stockCount", label: "기본 종목 수", suffix: "종목", min: 1, max: 100, step: 1 },
    { key: "cashRatio", label: "현금 비중 목표", suffix: "%", min: 0, max: 100, step: 1 },
    { key: "firstBuyRatio", label: "1차 매수 비중", suffix: "%", min: 0, max: 100, step: 1 },
    { key: "stopLossRatio", label: "손절 기준", suffix: "%", min: -100, max: 0, step: 1 },
    { key: "finalTargetRatio", label: "3차 익절 기준", suffix: "%", min: 0, step: 1 },
    { key: "firstEntryPrice", label: "1차 매수가", suffix: "USD", min: 0, step: 0.01 },
  ];
  const sellPlan = [
    { label: "1차 익절", rate: firstTargetPct, ratio: 0.4, target: target8Price },
    { label: "2차 익절", rate: secondTargetPct, ratio: 0.3, target: target9Price },
    { label: "3차 익절", rate: finalTargetPct, ratio: 0.3, target: target10Price },
  ];
  const expectedProfit = sellPlan.reduce((sum, item) => sum + totalShares * item.ratio * (averagePrice * (1 + item.rate) - averagePrice), 0);
  const lossAtStop = totalShares * (stopPrice - averagePrice);

  return <section className="calculator-page" aria-label="스윙 투자 계산기">
    <div className="hero calculator-hero"><div className="eyebrow">POSITION SIZING</div><h1>미국주식 스윙 투자 계산기</h1><p>2회 분할매수와 3회 분할매도, 평균 매수가 기준 손절·목표가를 계산합니다.</p></div>
    <div className="calculator-layout">
      <section className="calculator-card input-card">
        <div className="calculator-section-title"><div><div className="eyebrow">YOUR PLAN</div><h2>운용 기준</h2></div><div className="calculator-storage-actions"><span className="calculator-save-status" role="status">{!storageReady ? "저장값 확인 중…" : saved ? "✓ 자동 저장됨" : "기본값 사용 중"}</span><button type="button" className="calculator-reset-button" onClick={resetInputs}>기본값 초기화</button></div></div>
        <div className="calculator-inputs">{fields.map(({ key, label, suffix, ...limits }) => <label className="calculator-field" key={key}><span>{label}</span><div className="calculator-input-wrap"><input type="number" inputMode="decimal" value={input[key]} onChange={(event) => set(key, event.target.value)} {...limits} aria-label={label} /><em>{suffix}</em></div></label>)}</div>
        <div className="calculator-note">
          <strong>고정 매매 원칙</strong><br />
          1차 매수 {percent(firstPct)} · 2차 매수 {percent(secondPct)} (1차 매수가 대비 +5% 상승 후 상승 추세 확인 시)<br />
          손절 {input.stopLossRatio || "-5"}% · 익절 +8% 40% / +9% 30% / +10% 30%<br />
          2차 매수 체결 시 실제 평균 매수가를 기준으로 손절·익절 가격을 다시 계산합니다.
        </div>
      </section>
      <section className="calculator-card summary-card-large">
        <div className="calculator-section-title"><div><div className="eyebrow">AUTOMATIC SUMMARY</div><h2>종목당 자동 계산</h2></div><span>USD</span></div>
        <div className="calc-summary-grid">
          <article><span>종목당 목표 투자액</span><strong>{money(perStock)}</strong><small>현금 목표 제외 · {count}종목 기준</small></article>
          <article><span>1차 매수 금액 ({percent(firstPct)})</span><strong>{money(firstBuyAmount)}</strong><small>1차 매수가 {price(firstEntryPrice)}</small></article>
          <article><span>2차 매수 금액 ({percent(secondPct)})</span><strong>{money(secondBuyAmount)}</strong><small>2차 기준가 {price(secondEntryPrice)} (+5%)</small></article>
          <article><span>2회 매수 후 평균 매수가</span><strong>{price(averagePrice)}</strong><small>두 차수 매수금액과 주식 수 반영</small></article>
          <article className="negative"><span>손절 가격 ({input.stopLossRatio || "-5"}%)</span><strong>{price(stopPrice)}</strong><small>평균 매수가 기준 예상 손실 {money(lossAtStop)}</small></article>
          <article className="positive"><span>전체 분할매도 예상 수익</span><strong>{money(expectedProfit)}</strong><small>세 차례 매도 비중과 목표가 반영</small></article>
        </div>
      </section>
    </div>
    <section className="calculator-card allocation-card">
      <div className="calculator-section-title"><div><div className="eyebrow">ENTRY PLAN</div><h2>2회 분할매수 계획</h2><p>2차 매수는 가격 도달만으로 실행하지 않고 추세를 확인합니다.</p></div></div>
      <div className="allocation-table-wrap"><table className="allocation-table strategy-table">
        <thead><tr><th>차수</th><th>배정 비중</th><th>매수 금액</th><th>기준 가격</th><th>실행 조건</th></tr></thead>
        <tbody>
          <tr><td>1차 매수</td><td>{percent(firstPct)}</td><td>{money(firstBuyAmount)}</td><td>{price(firstEntryPrice)}</td><td>스크리너 매수 후보 중 차트 확인 후 진입</td></tr>
          <tr><td>2차 매수</td><td>{percent(secondPct)}</td><td>{money(secondBuyAmount)}</td><td>{price(secondEntryPrice)}</td><td>1차 매수가 대비 +5% 도달 및 상승 추세 유지 확인</td></tr>
          <tr className="total-row"><td>합계</td><td>100%</td><td>{money(perStock)}</td><td>—</td><td>종목당 목표 투자액 이내</td></tr>
        </tbody>
      </table></div>
    </section>
    <section className="calculator-card strategy-card">
      <div className="calculator-section-title"><div><div className="eyebrow">EXIT PLAN</div><h2>3회 분할매도 계획</h2><p>매도 목표 수익률은 2회 매수 후 평균 매수가 기준입니다.</p></div></div>
      <div className="allocation-table-wrap"><table className="allocation-table strategy-table">
        <thead><tr><th>차수</th><th>목표 수익률</th><th>매도 비중</th><th>목표 매도가</th><th>예상 실현 손익</th></tr></thead>
        <tbody>
          {sellPlan.map((item) => <tr className="profit-row" key={item.label}><td>{item.label}</td><td>+{percent(item.rate)}</td><td>{percent(item.ratio)}</td><td>{price(item.target)}</td><td>{money(totalShares * item.ratio * (item.target - averagePrice))}</td></tr>)}
          <tr className="total-row"><td>합계</td><td>—</td><td>100%</td><td>—</td><td>{money(expectedProfit)}</td></tr>
          <tr className="loss-row"><td>전량 손절</td><td>{input.stopLossRatio || "-5"}%</td><td>100%</td><td>{price(stopPrice)}</td><td>{money(lossAtStop)}</td></tr>
        </tbody>
      </table></div>
      <p className="calculator-note">예상 손익은 수수료·환전 비용·세금 및 가격 갭을 제외한 단순 계산입니다. 실제 2차 매수 여부는 차트 추세와 거래량을 확인해 결정하세요.</p>
    </section>
    <footer><span>설정값은 이 브라우저에 자동 저장됩니다.</span><span>실제 매매 전 가격, 수수료, 환율 및 갭 위험을 확인하세요.</span></footer>
  </section>;
}
료, 환율 및 갭 위험을 확인하세요.</span></footer>
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
