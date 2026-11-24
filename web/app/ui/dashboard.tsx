"use client";

import { useEffect, useState } from "react";
import { normalizeExitSettings } from "../../lib/swing-plan";
import PortfolioManager from "./portfolio-manager";
import { DEFAULT_CALCULATOR_INPUTS, type CalculatorInputs } from "@/lib/calculator-plan";
import TossConnection from "./toss-connection";
import Momentum from "./momentum";

type MonthlyMomentumItem = { ticker: string; name: string | null; exchange: string | null; return_pct: number };

type MonthlyMomentum = {
  reference_date: string;
  period_start: string;
  period_end: string;
  eligible_count: number;
  source?: string;
  items: MonthlyMomentumItem[];
  rebalance_open_at?: string;
  previous?: { reference_date: string; items: MonthlyMomentumItem[] };
  daily_risk?: {
    reference_date: string;
    start_date: string;
    items: Record<string, { status: "normal" | "warning" | "severe" | "pending" | "unavailable"; drawdown_pct?: number; rebalance_return_pct?: number }>;
  };
};

export type MonthlyDashboardResult = {
  data_date: string | null;
  spy_regime?: string;
  monthly_momentum?: MonthlyMomentum | null;
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
  return "https://kr.tradingview.com/chart/QaUkvTii/?symbol=" + encodeURIComponent(exchange + ":" + (candidate.Ticker || ""));
}
export default function Dashboard({ result, failedSession }: { result: MonthlyDashboardResult; failedSession?: string | null }) {
  const [portfolioOpened, setPortfolioOpened] = useState(false);
  const [activeMenu, setActiveMenu] = useState<"monthly" | "portfolio" | "momentum" | "toss">("monthly");

  return (
    <main className="shell">
      <header className="topbar">
        <a className="brand" href="#top"><span className="brand-mark">S</span> US EQUITY SCREENER</a>
        <nav className="menu-tabs" aria-label="주 메뉴" role="tablist">
          <button type="button" role="tab" aria-selected={activeMenu === "monthly"} className={activeMenu === "monthly" ? "active" : ""} onClick={() => setActiveMenu("monthly")}>월간 모멘텀</button>
          <button type="button" role="tab" aria-selected={activeMenu === "momentum"} className={activeMenu === "momentum" ? "active" : ""} onClick={() => setActiveMenu("momentum")}>급등 모멘텀</button>
          <button type="button" role="tab" aria-selected={activeMenu === "portfolio"} className={activeMenu === "portfolio" ? "active" : ""} onClick={() => { setPortfolioOpened(true); setActiveMenu("portfolio"); }}>내 포트폴리오</button>
          <button type="button" role="tab" id="toss-tab" aria-controls="toss-panel" aria-selected={activeMenu === "toss"} className={activeMenu === "toss" ? "active" : ""} onClick={() => setActiveMenu("toss")}>토스</button>
        </nav>
        <span className="market-tag"><i /> NYSE · NASDAQ</span>
      </header>

      {portfolioOpened && <div hidden={activeMenu !== "portfolio"}><PortfolioManager active={activeMenu === "portfolio"} /></div>}
      {activeMenu === "monthly" && (
        <MonthlyStrategy momentum={result.monthly_momentum} marketRegime={result.spy_regime} marketDate={result.data_date} failedSession={failedSession} />
      )}
      {activeMenu === "toss" && <TossConnection />}
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

function MonthlyStrategy({ momentum, marketRegime, marketDate, failedSession }: {
  momentum?: MonthlyMomentum | null;
  marketRegime?: string;
  marketDate: string | null;
  failedSession?: string | null;
}) {
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
          setCapitalStatus("내 포트폴리오에서 로그인하면 저장된 투자금을 불러옵니다.");
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
  const dailyRisk = momentum?.daily_risk;
  const riskLabels = { normal: "기준 이내", warning: "낙폭 주의", severe: "큰 낙폭", pending: "첫 종가 대기", unavailable: "가격 미확인" };
  const marketLabel = marketRegime === "BULL" ? "상승 환경" : marketRegime === "RISK_OFF" ? "위험 구간" : "확인 대기";

  return (
    <section className="monthly-dashboard" aria-label="월간 모멘텀 스크리너">
      <header className="monthly-hero" id="top">
        <div>
          <p className="monthly-eyebrow">12−1개월 상대 모멘텀</p>
          <h1>월간 모멘텀 스크리너</h1>
          <p>최근 한 달을 제외한 수익률로 상위 10종목을 고르고, 월말 순위가 바뀌면 비중을 조정합니다.</p>
        </div>
        <div className="monthly-market">
          <span>SPY 시장 환경</span><strong>{marketLabel}</strong>
          {marketDate && <small>미국장 {marketDate} 종가</small>}
        </div>
      </header>

      {failedSession && <p className="monthly-panel-note" role="status">미국장 {failedSession} 기준 배치에 실패했습니다. 아래는 마지막으로 게시된 결과입니다.</p>}

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
            {!momentum.previous && <p className="monthly-panel-note">이전 월 목록을 저장한 뒤부터 신규·유지·이탈을 표시합니다.</p>}
            <p className="monthly-panel-note">
              {dailyRisk ? `가격 기준 · 미국장 ${dailyRisk.reference_date} 종가 · ${dailyRisk.start_date} 교체 시점부터 고점 대비 −8% 이하 낙폭 주의 / −12% 이하 큰 낙폭` : "일일 손실 점검은 다음 배치에서 표시됩니다."}
            </p>
            <div className="monthly-table-wrap">
              <table className="monthly-strategy-table">
                <thead><tr><th scope="col">순위</th><th scope="col">종목</th><th scope="col">12−1 수익률</th><th scope="col">월간 변경</th><th scope="col">교체일 시가 대비</th><th scope="col">고점 대비 낙폭</th></tr></thead>
                <tbody>
                  {momentum.items.map(({ ticker, name, exchange, return_pct }, index) => {
                    const prior = previousRank.get(ticker);
                    const risk = dailyRisk?.items[ticker];
                    const periodReturn = risk?.rebalance_return_pct;
                    return (
                      <tr key={ticker}>
                        <td>{index + 1}</td>
                        <td><a href={tradingViewUrl({ Ticker: ticker, Exchange: exchange ?? undefined })} target="_blank" rel="noreferrer">{ticker} ↗</a>{name && <small>{name}</small>}</td>
                        <td className={return_pct >= 0 ? "monthly-profit" : "monthly-loss"}>{momentumPercent.format(return_pct / 100)}</td>
                        <td>{momentum.previous ? <span className={prior ? "monthly-badge" : "monthly-badge monthly-badge-new"}>{prior ? `유지 · 이전 ${prior}위` : "신규 편입"}</span> : "—"}</td>
                        <td className={periodReturn == null ? undefined : periodReturn >= 0 ? "monthly-profit" : "monthly-loss"}>{periodReturn == null ? "—" : momentumPercent.format(periodReturn / 100)}</td>
                        <td className={risk ? `monthly-risk-${risk.status}` : undefined}><span className="monthly-risk-label">{risk ? riskLabels[risk.status] : "배치 대기"}</span>
                          {risk?.drawdown_pct != null && <small>{momentumPercent.format(risk.drawdown_pct / 100)}</small>}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {momentum.previous && (
              <div className="monthly-exits">
                <strong>목록 이탈 · 보유 중이면 정리 검토</strong>
                <span>{exits.length ? exits.map(({ ticker }) => ticker).join(" · ") : "이탈 종목 없음"}</span>
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
          <div><dt>낙폭과 월말 교체</dt><dd>교체일 시가 대비 수익률은 목록 전체에 같은 가격 기준을 적용합니다. 고점 대비 낙폭은 교체일 시가와 이후 최고 종가 중 높은 가격에서 얼마나 내려왔는지 보여줍니다. 낙폭 표시는 위험 점검용이며 정기 매매는 월말 순위에 따라 검토합니다. 회계·유동성 문제로 보유 근거가 깨지면 월중에도 청산을 검토합니다.</dd></div>
        </dl>
      </section>
    </section>
  );
}
