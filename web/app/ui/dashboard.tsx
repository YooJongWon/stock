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
  universe_scanned_count?: number;
  candidate_count?: number;
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
    : new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Seoul" }).format(date);
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

function renderMarkdown(source: string) {
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
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(markdownCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="markdown-table-wrap" key={index}>
          <table className="markdown-table">
            <thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{cell}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => (
              <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{row[cellIndex] ?? ""}</td>)}</tr>
            ))}</tbody>
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
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);

  const stale = now !== null && !!result.last_successful_run_at && now - Date.parse(result.last_successful_run_at) > 96 * 60 * 60 * 1000;
  const missing = result.status === "not_run" || result.status === "missing";
  const failed = runStatus.status === "failed";
  const displayedRunAt = runStatus.attempted_at ?? result.last_successful_run_at;
  const displayedSession = runStatus.reference_date ?? result.data_date;

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
        <p>기존 Python 엔진이 계산한 매수·관심 후보와 지표를 확인합니다.</p>
      </section>

      {failed && <div className="alert error"><strong>최근 자동 실행 실패</strong><span>{runStatus.message || "새 결과를 만들지 못해 마지막 정상 결과를 유지하고 있습니다."}</span><small>시도: {localDate(runStatus.attempted_at)} · 기준일 {runStatus.reference_date || "—"}</small></div>}
      {stale && <div className="alert warning"><strong>데이터가 오래됐습니다</strong><span>마지막 정상 결과 이후 4일 이상 지났습니다. 최신 거래일 데이터인지 확인하세요.</span></div>}
      {result.status === "degraded" && result.warnings?.map((warning, index) => <div className="alert warning" key={index}><strong>일부 데이터 확인 필요</strong><span>{warning}</span></div>)}
      {missing && <div className="alert info"><strong>아직 정상 실행 결과가 없습니다</strong><span>GitHub Actions에서 스크리너를 한 번 실행하면 이 화면에 결과가 표시됩니다.</span></div>}

      <section className="summary-grid" aria-label="실행 요약">
        <article className="summary-card"><span>매수 후보</span><strong className="accent">{count(result.buy_count)}<em>종목</em></strong><small>기존 BUY 판정</small></article>
        <article className="summary-card"><span>관심 종목</span><strong>{count(result.watch_count)}<em>종목</em></strong><small>기존 WATCH 판정</small></article>
        <article className="summary-card"><span>전체 스캔</span><strong>{count(result.universe_scanned_count)}<em>종목</em></strong><small>미국 상장 보통주</small></article>
        <article className="summary-card"><span>최종 후보</span><strong>{count(result.candidate_count)}<em>종목</em></strong><small>BUY 및 WATCH</small></article>
      </section>

      <section className="results-section">
        <div className="section-heading">
          <div><div className="eyebrow">LATEST SCREEN</div><h2>최종 후보 리포트</h2><p>로컬 output/final_candidates.md와 같은 스크리너 보고서</p></div>
          {!missing && <a className="download" href="/data/latest-candidates.csv" download>CSV 다운로드 <span>↓</span></a>}
        </div>
        {renderMarkdown(markdown)}
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
