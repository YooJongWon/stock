"use client";

import { useEffect, useState } from "react";
import { normalizeExitSettings } from "../../lib/swing-plan";
import { DEFAULT_CALCULATOR_INPUTS, type CalculatorInputs } from "@/lib/calculator-plan";
import { tradingViewChartUrl } from "@/lib/tradingview";
import TossConnection from "./toss-connection";
import Momentum from "./momentum";

type MonthlyMomentumItem = { ticker: string; name: string | null; exchange: string | null; return_pct: number };
type SectorPerformance = { symbol: string; sector: string; change_pct: number | null };

type MonthlyMomentum = {
  reference_date: string;
  period_start: string;
  period_end: string;
  eligible_count: number;
  source?: string;
  items: MonthlyMomentumItem[];
  rebalance_open_at?: string;
  previous?: { reference_date: string; items: MonthlyMomentumItem[] };
};

export type MonthlyDashboardResult = {
  data_date: string | null;
  spy_regime?: string;
  monthly_momentum?: MonthlyMomentum | null;
  sector_reference_date?: string;
  sector_performance?: SectorPerformance[];
  stock_sectors?: Record<string, string>;
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

function tradingViewUrl(candidate: { Ticker: string; Exchange?: string }) {
  const rawExchange = String(candidate.Exchange || "").toUpperCase();
  const exchange = rawExchange.includes("NYSE") || rawExchange === "NYQ" ? "NYSE"
    : rawExchange.includes("NASDAQ") || ["NMS", "NGM", "NCM"].includes(rawExchange) ? "NASDAQ"
    : "NASDAQ";
  return tradingViewChartUrl(exchange + ":" + (candidate.Ticker || ""));
}
export type MarketSession = { date: string; kind: "regular" | "early_close" | "closed"; close_et?: string };
const sessionLabels = { regular: "거래일", early_close: "조기 폐장", closed: "휴장" };

export default function Dashboard({ result, marketSession, batchReferenceDate, failedSession }: {
  result: MonthlyDashboardResult;
  marketSession: MarketSession | null;
  batchReferenceDate: string | null;
  failedSession?: string | null;
}) {
  const [activeMenu, setActiveMenu] = useState<"monthly" | "momentum" | "toss">("monthly");

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#top"><span className="brand-mark">S</span> US EQUITY SCREENER</a>
        <nav className="menu-tabs" aria-label="주 메뉴" role="tablist">
          <button type="button" role="tab" aria-selected={activeMenu === "monthly"} className={activeMenu === "monthly" ? "active" : ""} onClick={() => setActiveMenu("monthly")}>월간 모멘텀</button>
          <button type="button" role="tab" aria-selected={activeMenu === "momentum"} className={activeMenu === "momentum" ? "active" : ""} onClick={() => setActiveMenu("momentum")}>급등 모멘텀</button>
          <button type="button" role="tab" id="toss-tab" aria-controls="toss-panel" aria-selected={activeMenu === "toss"} className={activeMenu === "toss" ? "active" : ""} onClick={() => setActiveMenu("toss")}>토스</button>
        </nav>
        <span className="market-tag"><i /> NYSE · NASDAQ</span>
      </header>

      {activeMenu === "monthly" && (
        <MonthlyStrategy result={result} marketSession={marketSession} batchReferenceDate={batchReferenceDate} failedSession={failedSession} />
      )}
      {activeMenu === "toss" && <TossConnection momentum={result.monthly_momentum} positionWeight={monthlyPositionWeight} />}
      {activeMenu === "momentum" && <Momentum />}
    </main>
  );
}

const momentumPercent = new Intl.NumberFormat("ko-KR", {
  style: "percent", signDisplay: "exceptZero", maximumFractionDigits: 1,
});

const monthlyDollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const monthlyPositionWeight = 0.0625;
const monthlyPositionCount = 10;

const sectorPercent = new Intl.NumberFormat("ko-KR", {
  style: "percent", signDisplay: "exceptZero", minimumFractionDigits: 2, maximumFractionDigits: 2,
});

function MonthlyStrategy({ result, marketSession, batchReferenceDate, failedSession }: {
  result: MonthlyDashboardResult;
  marketSession: MarketSession | null;
  batchReferenceDate: string | null;
  failedSession?: string | null;
}) {
  const { monthly_momentum: momentum, spy_regime: marketRegime, data_date: marketDate,
    sector_reference_date: sectorDate, sector_performance: sectors = [], stock_sectors: stockSectors } = result;
  const [capitalInput, setCapitalInput] = useState("10000");
  const [settings, setSettings] = useState<CalculatorInputs | null>(null);
  const [savedCapital, setSavedCapital] = useState<string | null>(null);
  const [capitalStatus, setCapitalStatus] = useState("저장된 투자금 확인 중…");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    async function restore() {
      try {
        const response = await fetch("/api/portfolio", { cache: "no-store", signal: controller.signal });
        if (controller.signal.aborted) return;
        if (response.status === 401) {
          setCapitalStatus("토스 탭에서 인증한 뒤 돌아오면 저장된 투자금을 불러옵니다.");
          return;
        }
        if (!response.ok) throw new Error();
        const data = await response.json() as { calculatorInputs?: Partial<CalculatorInputs> | null };
        if (controller.signal.aborted) return;
        let legacy: Partial<CalculatorInputs> = {};
        if (!data.calculatorInputs?.total) {
          try {
            legacy = JSON.parse(window.localStorage.getItem("jong9-stock-swing-calculator-v1") ?? "{}") ?? {};
          } catch {
            // Browser storage is optional when restoring server settings.
          }
        }
        const restored = { ...DEFAULT_CALCULATOR_INPUTS };
        const stored = normalizeExitSettings({ ...legacy, ...data.calculatorInputs });
        for (const key of Object.keys(restored) as (keyof CalculatorInputs)[]) {
          const value = stored[key];
          if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) restored[key] = value;
        }
        const serverTotal = data.calculatorInputs?.total;
        const total = typeof stored.total === "string" && stored.total.trim() && Number.isFinite(Number(stored.total)) && Number(stored.total) >= 0 ? stored.total : "10000";
        setSettings(restored);
        setCapitalInput(total);
        setSavedCapital(serverTotal === total ? total : null);
        setCapitalStatus(serverTotal === total ? "저장된 투자금 불러옴" : total === stored.total ? "이 브라우저의 기존 투자금 불러옴 · 저장 가능" : "배정 계산용 투자금을 저장할 수 있습니다.");
      } catch {
        if (!controller.signal.aborted) setCapitalStatus("저장된 투자금을 불러오지 못했습니다. 탭을 다시 열어 주세요.");
      }
    }
    void restore();
    return () => controller.abort();
  }, []);

  async function saveCapital() {
    if (!settings || !validCapital || saving) return;
    setSaving(true);
    setCapitalStatus("투자금 저장 중…");
    try {
      const response = await fetch("/api/portfolio", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ calculatorInputs: { ...settings, total: capitalInput } }),
      });
      if (!response.ok) throw new Error();
      setSavedCapital(capitalInput);
      setCapitalStatus("투자금 저장됨");
    } catch {
      setCapitalStatus("투자금 저장 실패 · 다시 시도해 주세요.");
    } finally {
      setSaving(false);
    }
  }

  const capital = Number(capitalInput);
  const validCapital = capitalInput.trim() !== "" && Number.isFinite(capital) && capital >= 0;
  const allocation = validCapital ? monthlyDollars.format(capital * monthlyPositionWeight) : "—";
  const cashReserve = validCapital ? monthlyDollars.format(capital * (1 - monthlyPositionCount * monthlyPositionWeight)) : "—";
  const previousRank = new Map(momentum?.previous?.items.map(({ ticker }, index) => [ticker, index + 1]));
  const tickers = new Set(momentum?.items.map(({ ticker }) => ticker));
  const exits = momentum?.previous?.items.filter(({ ticker }) => !tickers.has(ticker)) ?? [];
  const marketLabel = marketRegime === "BULL" ? "상승 환경" : marketRegime === "RISK_OFF" ? "위험 구간" : "확인 대기";
  const sectorsBySymbol = new Map(sectors.map((sector) => [sector.symbol, sector]));
  const orderedSectors = [...sectors].sort((a, b) => (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity));

  return (
    <section className="monthly-dashboard" aria-label="월간 모멘텀 스크리너">
      <header className="monthly-hero" id="top">
        <div>
          <p className="monthly-eyebrow">12−1개월 상대 모멘텀</p>
          <h1>월간 모멘텀 스크리너</h1>
          <p>최근 한 달을 제외한 수익률로 상위 10종목을 고르고, 월말 순위가 바뀌면 비중을 조정합니다.</p>
        </div>
        <div className="monthly-market-cards">
          <div className="monthly-market">
            <span>SPY 시장 환경</span><strong>{marketLabel}</strong>
            {marketDate && <small>미국장 {marketDate} 종가</small>}
          </div>
          <div className="monthly-market">
            <span>배치 실행일 미국장 일정</span>
            <strong className={marketSession ? marketSession.kind === "regular" ? "session-open" : "session-closed" : undefined}>
              {marketSession ? sessionLabels[marketSession.kind] : "확인 대기"}
            </strong>
            {marketSession && <small>{marketSession.date}{marketSession.kind === "early_close" && marketSession.close_et && ` · ${marketSession.close_et} ET`}</small>}
            {batchReferenceDate && <small>배치 조회 기준 {batchReferenceDate}</small>}
          </div>
        </div>
      </header>

      {failedSession && <p className="monthly-panel-note" role="status">미국장 {failedSession} 기준 배치에 실패했습니다. 아래는 마지막으로 게시된 결과입니다.</p>}

      <section className="sector-overview monthly-sector-overview" aria-labelledby="monthly-sector-title">
        <div className="sector-overview-heading">
          <div><h2 id="monthly-sector-title">섹터별 일일 등락률</h2><p>미국 11개 섹터 ETF · 직전 거래일 종가 대비</p></div>
          {sectorDate && <span>미국장 {sectorDate}</span>}
        </div>
        {orderedSectors.length ? (
          <div className="sector-grid">
            {orderedSectors.map(({ symbol, sector, change_pct }) => (
              <div key={symbol} className={`sector-card ${change_pct == null ? "unknown" : change_pct > 0 ? "up" : change_pct < 0 ? "down" : "flat"}`}>
                <span>{sector}</span>
                <strong>{change_pct == null ? "종가 미확인" : sectorPercent.format(change_pct / 100)}</strong>
                <small>{symbol}</small>
              </div>
            ))}
          </div>
        ) : <p className="monthly-panel-note">섹터 등락률 데이터 게시 대기</p>}
      </section>

      <div className="monthly-overview">
        <article><span>순위 기준일 · 미국장</span><strong>{momentum?.reference_date ?? "—"}</strong><small>월말 정규장 종가</small></article>
        <article><span>기준 리밸런싱 시점</span><strong>{localDate(momentum?.rebalance_open_at ?? null)}</strong><small>월말 직후 미국장 시가 · 한국 시간 · 경과한 일정은 참고</small></article>
        <article>
          <label htmlFor="monthly-capital">배정 계산용 자금 (USD)</label>
          <div className="monthly-capital-control">
            <input id="monthly-capital" type="number" min="0" step="0.01" value={capitalInput} disabled={saving || capitalStatus === "저장된 투자금 확인 중…"} onChange={(event) => setCapitalInput(event.target.value)} />
            {settings && <button type="button" disabled={!validCapital || saving || capitalInput === savedCapital} onClick={saveCapital}>저장</button>}
          </div>
          <small role="status">{capitalStatus}</small>
          <small>종목당 6.25% · {monthlyPositionCount}종목 편입 시 목표 현금 {cashReserve}</small>
        </article>
      </div>

      <section className="monthly-panel" aria-labelledby="monthly-current-title">
        <div className="monthly-panel-heading">
          <div>
            <h2 id="monthly-current-title">월간 모멘텀 관찰 목록</h2>
            {momentum && <p>{momentum.period_start}~{momentum.period_end} 수익률 · {count(momentum.eligible_count)}종목 중 상위 {momentum.items.length}개{momentum.source === "existing_momentum_price_cache" && " · 기존 가격 캐시 기준"}</p>}
          </div>
          <strong>종목당 목표 {allocation}</strong>
        </div>
        {momentum ? (
          <>
            <p className="monthly-panel-note">
              {momentum.previous
                ? `지난 목록(${momentum.previous.reference_date})과 비교합니다. 새로 상위 10위에 들면 신규 편입, 지난달에도 상위 10위였으면 유지로 표시합니다.`
                : "지난달과 이번 달의 상위 10종목을 비교합니다. 첫 비교 결과는 다음 월말 순위가 게시되면 표시됩니다."}
            </p>
            <div className="monthly-table-wrap">
              <table className="monthly-strategy-table">
                <thead><tr><th scope="col">순위</th><th scope="col">종목</th><th scope="col">12−1 수익률</th><th scope="col">섹터</th><th scope="col">지난달 대비</th></tr></thead>
                <tbody>
                  {momentum.items.map(({ ticker, name, exchange, return_pct }, index) => {
                    const prior = previousRank.get(ticker);
                    const sector = sectorsBySymbol.get(stockSectors?.[ticker] ?? "");
                    return (
                      <tr key={ticker}>
                        <td>{index + 1}</td>
                        <td><a href={tradingViewUrl({ Ticker: ticker, Exchange: exchange ?? undefined })} target="_blank" rel="noreferrer">{ticker} ↗</a>{name && <small>{name}</small>}</td>
                        <td className={return_pct >= 0 ? "monthly-profit" : "monthly-loss"}>{momentumPercent.format(return_pct / 100)}</td>
                        <td>{sector?.sector ?? "미확인"}</td>
                        <td>{momentum.previous ? <span className={prior ? "monthly-badge" : "monthly-badge monthly-badge-new"}>{prior ? `유지 · 이전 ${prior}위` : "신규 편입"}</span> : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {momentum.previous && (
              <div className="monthly-exits">
                <strong>목록 이탈 · 보유 중이면 정리 검토</strong>
                <span>{exits.length ? exits.map(({ ticker }) => {
                  const sector = sectorsBySymbol.get(stockSectors?.[ticker] ?? "");
                  return sector ? `${ticker} (${sector.sector})` : ticker;
                }).join(" · ") : "이탈 종목 없음"}</span>
                <small>비교 기준 {momentum.previous.reference_date} 목록</small>
              </div>
            )}
          </>
        ) : <p className="monthly-panel-note">첫 월말 순위가 게시되면 이곳에 표시됩니다.</p>}
      </section>

      <section className="monthly-panel monthly-playbook" aria-labelledby="monthly-playbook-title">
        <div className="monthly-panel-heading"><h2 id="monthly-playbook-title">매수·매도와 손실 관리</h2></div>
        <dl>
          <div><dt>매수 검토</dt><dd>월말 순위 확정 후 다음 미국 거래일 개장에 신규 편입을 검토합니다. 실적 발표나 가이던스·공시를 더 확인해야 하면 배정액을 현금으로 둡니다.</dd></div>
          <div><dt>매도·익절</dt><dd>다음 월말 상위 10위 밖으로 밀린 보유 종목은 다음 거래일에 정리를 검토합니다. 상위권을 유지하면 보유하고 목표 비중을 점검합니다. 고정 수익률에 따른 분할익절 기준은 두지 않습니다.</dd></div>
          <div><dt>월중 위험 관리</dt><dd>회계·유동성 문제로 보유 근거가 깨지면 월중에도 청산을 검토합니다.</dd></div>
        </dl>
      </section>
    </section>
  );
}
