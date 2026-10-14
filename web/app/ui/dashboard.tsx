"use client";

import { useEffect, useState, type ReactNode } from "react";

type Result = {
  status: string;
  last_successful_run_at: string | null;
  data_date: string | null;
  error: string | null;
  warnings: string[];
  warning_count: number;
  buy_count: number;
  watch_count: number;
  universe_scanned_count: number;
  candidate_count: number;
};

type RunStatus = { status: string; attempted_at: string | null; reference_date: string | null; message: string | null };

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
        <span className="market-tag"><i /> NYSE · NASDAQ</span>
      </header>

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
        <article className="summary-card"><span>매수 후보</span><strong className="accent">{result.buy_count.toLocaleString("ko-KR")}<em>종목</em></strong><small>기존 BUY 판정</small></article>
        <article className="summary-card"><span>관심 종목</span><strong>{result.watch_count.toLocaleString("ko-KR")}<em>종목</em></strong><small>기존 WATCH 판정</small></article>
        <article className="summary-card"><span>전체 스캔</span><strong>{result.universe_scanned_count.toLocaleString("ko-KR")}<em>종목</em></strong><small>미국 상장 보통주</small></article>
        <article className="summary-card"><span>최종 후보</span><strong>{result.candidate_count.toLocaleString("ko-KR")}<em>종목</em></strong><small>BUY 및 WATCH</small></article>
      </section>

      <section className="results-section">
        <div className="section-heading">
          <div><div className="eyebrow">LATEST SCREEN</div><h2>최종 후보 리포트</h2><p>로컬 output/final_candidates.md와 같은 스크리너 보고서</p></div>
          {!missing && <a className="download" href="/data/latest-candidates.csv" download>CSV 다운로드 <span>↓</span></a>}
        </div>
        {renderMarkdown(markdown)}
      </section>

      <footer><span>지표와 판정은 기존 Python 스크리너 산출값입니다.</span><span>매매 결정 전 시세와 갭 위험을 확인하세요.</span></footer>
    </main>
  );
}
