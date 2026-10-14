"use client";

import { useEffect, useState } from "react";

type Candidate = Record<string, string | number | boolean | null | Record<string, boolean>> & {
  Ticker?: string;
  "Company Name"?: string;
  Final?: string;
  Score?: number;
  Price?: number;
  RSI14?: number;
  "Relative Strength"?: number;
  "ATR Stop %"?: number;
  "Entry Plan"?: number;
  "Initial Stop"?: number;
  "2R Target"?: number;
  filter_results?: Record<string, boolean>;
};

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
  candidates: Candidate[];
};

type RunStatus = { status: string; attempted_at: string | null; reference_date: string | null; message: string | null };

const filterLabels: Record<string, string> = {
  "Price >= $10": "주가 10달러 이상",
  "Market Cap >= $2B": "시가총액 20억 달러 이상",
  "PE > 0": "P/E 양수",
  "PE < 40": "P/E 40 미만",
  "ROE > 15%": "ROE 15% 초과",
  "Sales Growth 5Y > 5%": "5년 매출 성장률 5% 초과",
  "Average Volume >= 1M": "30일 평균 거래량 100만 주 이상",
  "Average Dollar Volume >= $30M": "30일 평균 거래대금 3,000만 달러 이상",
  "Market Regime BULL": "시장 상승장",
  "Trend Stack EMA20 > SMA50 > SMA200": "EMA20 > SMA50 > SMA200",
  "SMA50 Rising": "SMA50 상승",
  "Relative Strength > 0": "SPY 대비 상대강도 양수",
  "RSI >= 55": "RSI 55 이상",
  "RSI < 68": "RSI 68 미만",
  "Recent 50MA Pullback": "최근 SMA50 눌림",
  "Recent Volume Dry-up": "최근 거래량 감소",
  "Volume Expansion": "거래량 증가",
  "Strong Bull Candle": "강한 양봉",
  "50MA Distance 0..2 ATR": "SMA50 이격 0~2 ATR",
  "ATR Stop <= 5%": "ATR 손절폭 5% 이하",
  "Score >= 7": "점수 7점 이상",
};

function number(value: unknown, digits = 2) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("ko-KR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function localDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Seoul" }).format(date);
}

export default function Dashboard({ result, runStatus }: { result: Result; runStatus: RunStatus }) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => setNow(Date.now()), []);

  const stale = now !== null && !!result.last_successful_run_at && now - Date.parse(result.last_successful_run_at) > 96 * 60 * 60 * 1000;
  const missing = result.status === "not_run" || result.status === "missing";
  const failed = runStatus.status === "failed";
  const candidates = Array.isArray(result.candidates) ? result.candidates : [];

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#top"><span className="brand-mark">S</span> US EQUITY SCREENER</a>
        <span className="market-tag"><i /> NYSE · NASDAQ</span>
      </header>

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
        <article className="summary-card"><span>데이터 기준일</span><strong>{result.data_date || "—"}</strong><small>마지막 XNYS 정규장 종가</small></article>
        <article className="summary-card"><span>마지막 정상 실행</span><strong className="time-value">{localDate(result.last_successful_run_at)}</strong><small>한국 시간</small></article>
        <article className="summary-card"><span>매수 후보</span><strong className="accent">{number(result.buy_count, 0)}<em>종목</em></strong><small>기존 BUY 판정</small></article>
        <article className="summary-card"><span>관심 종목</span><strong>{number(result.watch_count, 0)}<em>종목</em></strong><small>기존 WATCH 판정</small></article>
      </section>

      <section className="results-section">
        <div className="section-heading">
          <div><div className="eyebrow">LATEST SCREEN</div><h2>매수 후보 목록</h2><p>전체 {number(result.universe_scanned_count, 0)}종목 검사 · BUY 우선 정렬</p></div>
          {!missing && result.status !== "failed" && <a className="download" href="/data/latest-candidates.csv" download>CSV 다운로드 <span>↓</span></a>}
        </div>

        {candidates.length === 0 ? (
          <div className="empty-state"><span className="empty-icon">⌕</span><strong>{missing ? "결과를 기다리는 중입니다" : "조건에 맞는 후보가 없습니다"}</strong><p>{missing ? "첫 번째 정상 실행 후 후보 목록이 여기에 표시됩니다." : "이번 실행은 정상 완료됐지만 BUY 또는 WATCH 종목이 없습니다."}</p></div>
        ) : (
          <div className="table-wrap"><table>
            <thead><tr><th>종목</th><th>판정</th><th>점수</th><th>종가</th><th>RSI14</th><th>SPY 대비</th><th>손절폭</th><th>진입 추정</th><th>2R 목표</th><th>필터</th></tr></thead>
            <tbody>{candidates.map((item, index) => {
              const checks = item.filter_results || {};
              return <tr key={`${item.Ticker || "row"}-${index}`}>
                <td><strong className="ticker">{item.Ticker || "—"}</strong><span className="company">{item["Company Name"] || "회사명 없음"}</span></td>
                <td><span className={`decision ${item.Final === "BUY" ? "buy" : "watch"}`}>{item.Final === "BUY" ? "매수" : "관심"}</span></td>
                <td><strong className="score">{number(item.Score, 0)}<small>/10</small></strong></td>
                <td>${number(item.Price)}</td><td>{number(item.RSI14)}</td><td>{number(item["Relative Strength"])}%</td><td>{number(item["ATR Stop %"])}%</td>
                <td>${number(item["Entry Plan"])}</td><td>${number(item["2R Target"])}</td>
                <td><details className="checks"><summary>통과 {Object.values(checks).filter(Boolean).length}/{Object.keys(checks).length}</summary><ul>{Object.entries(checks).map(([key, passed]) => <li key={key} className={passed ? "pass" : "fail"}><span>{passed ? "✓" : "×"}</span>{filterLabels[key] || key}</li>)}</ul></details></td>
              </tr>;
            })}</tbody>
          </table></div>
        )}
      </section>

      <footer><span>지표와 판정은 기존 Python 스크리너 산출값입니다.</span><span>매매 결정 전 시세와 갭 위험을 확인하세요.</span></footer>
    </main>
  );
}
