"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";

import { buildCalculatorPlan, type CalculatorInputs } from "@/lib/calculator-plan";
import type { TossHolding, TossSnapshot } from "@/lib/toss";

const refreshMs = 30_000;
const koreaTime = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "medium" });

const buyStages = { 1: "1차매수", 2: "2차매수" } as const;
type BuyStage = keyof typeof buyStages;
type StageRow = { holding_key: string; stage: BuyStage };
const legacyStorageKey = "toss-buy-stages";
const stageFilters = [
  { value: "all", label: "전체" },
  { value: 1, label: buyStages[1] },
  { value: 2, label: buyStages[2] },
] as const;

function legacyStageRows(): StageRow[] {
  try {
    const stored = JSON.parse(localStorage.getItem(legacyStorageKey) ?? "{}");
    return Object.entries(stored).flatMap(([holding_key, stage]): StageRow[] =>
      holding_key.length > 0 && holding_key.length <= 120 && (stage === 0 || stage === 1 || stage === 2)
        ? [{ holding_key, stage: stage === 2 ? 2 : 1 }]
        : [],
    );
  } catch {
    return [];
  }
}

async function saveStages(stages: StageRow[], options?: { importLegacy: true; signal: AbortSignal }) {
  const response = await fetch("/api/toss/stages", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stages, importLegacy: options?.importLegacy }),
    signal: options?.signal,
  });
  if (!response.ok) throw new Error("Could not save Toss buy stages");
}

export default function TossConnection() {
  const [needsAuth, setNeedsAuth] = useState(false);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [snapshot, setSnapshot] = useState<TossSnapshot | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [savedSettings, setSavedSettings] = useState<Partial<CalculatorInputs> | null>(null);
  const [stageFilter, setStageFilter] = useState<"all" | BuyStage>("all");
  const [manualStages, setManualStages] = useState<Record<string, BuyStage> | null>(null);
  const [stageError, setStageError] = useState("");
  const [savingStage, setSavingStage] = useState(false);
  const [stageLoadAttempt, setStageLoadAttempt] = useState(0);
  const inFlight = useRef(false);
  const hasSnapshot = snapshot !== null;
  const plan = buildCalculatorPlan(savedSettings);

  useEffect(() => {
    if (!hasSnapshot) return;
    const controller = new AbortController();
    async function loadStages() {
      try {
        const legacy = legacyStageRows();
        for (let offset = 0; offset < legacy.length; offset += 500) {
          await saveStages(legacy.slice(offset, offset + 500), { importLegacy: true, signal: controller.signal });
        }
        const response = await fetch("/api/toss/stages", { cache: "no-store", signal: controller.signal });
        if (!response.ok) throw new Error("Could not load Toss buy stages");
        const data: { stages: StageRow[] } = await response.json();
        if (controller.signal.aborted) return;
        setManualStages(Object.fromEntries(data.stages.map(({ holding_key, stage }) => [holding_key, stage])));
        setStageError("");
        if (legacy.length > 0) {
          try { localStorage.removeItem(legacyStorageKey); } catch { /* Import is safe to repeat. */ }
        }
      } catch {
        if (!controller.signal.aborted) setStageError("저장된 매수 상태를 불러오지 못했습니다.");
      }
    }
    void loadStages();
    return () => controller.abort();
  }, [hasSnapshot, stageLoadAttempt]);

  async function advanceStage(key: string, stage: BuyStage) {
    if (!manualStages || savingStage) return;
    const next: BuyStage = stage === 1 ? 2 : 1;
    setSavingStage(true);
    setStageError("");
    try {
      await saveStages([{ holding_key: key, stage: next }]);
      setManualStages((current) => current && { ...current, [key]: next });
    } catch {
      setStageError("매수 상태를 저장하지 못했습니다. 상태 버튼을 다시 눌러 주세요.");
    } finally {
      setSavingStage(false);
    }
  }

  async function checkConnection(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (inFlight.current) return;

    inFlight.current = true;
    setBusy(true);
    try {
      if (needsAuth) {
        const auth = await fetch("/api/portfolio/auth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        });
        if (!auth.ok) {
          const data = await auth.json();
          setError(data.error ?? "인증에 실패했습니다.");
          return;
        }
        setError("");
        setPassword("");
        setNeedsAuth(false);
      }

      const response = await fetch("/api/toss", { cache: "no-store" });
      if (response.status === 401) {
        setError("");
        setNeedsAuth(true);
        setRefreshing(false);
        setSnapshot(null);
        setManualStages(null);
        return;
      }

      const data = await response.json();
      if (!response.ok) {
        setError(data.error ?? "연결 확인에 실패했습니다.");
        return;
      }
      setError("");
      setSnapshot(data);
      setRefreshing(true);
    } catch {
      setError("연결 확인에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    if (!hasSnapshot) return;
    const controller = new AbortController();
    async function loadSettings() {
      try {
        const response = await fetch("/api/portfolio", { cache: "no-store", signal: controller.signal });
        if (!response.ok) return;
        const data = await response.json();
        if (!controller.signal.aborted) setSavedSettings(data.calculatorInputs ?? null);
      } catch {
        // The same defaults apply when saved calculator settings are unavailable.
      }
    }
    void loadSettings();
    return () => controller.abort();
  }, [hasSnapshot]);

  const refresh = useEffectEvent(() => {
    if (!needsAuth && document.visibilityState === "visible") void checkConnection();
  });

  useEffect(() => {
    refresh();
    const onVisibilityChange = () => refresh();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => document.removeEventListener("visibilitychange", onVisibilityChange);
  }, []);

  useEffect(() => {
    if (!refreshing) return;
    const timer = window.setInterval(() => refresh(), refreshMs);
    return () => window.clearInterval(timer);
  }, [refreshing]);

  return (
    <section className="portfolio-page" role="tabpanel" id="toss-panel" aria-labelledby="toss-tab">
      <div className="portfolio-heading-row">
        <div className="hero portfolio-hero">
          <h1>토스</h1>
          <p>토스증권 계좌 · 화면을 보는 동안 30초마다 자동 갱신</p>
        </div>
        {!needsAuth && (
          <button className="portfolio-primary toss-refresh" type="button" disabled={busy} onClick={() => void checkConnection()}>
            {busy ? "조회 중…" : "새로고침"}
          </button>
        )}
      </div>

      {needsAuth ? (
        <form className="portfolio-login" onSubmit={checkConnection}>
          <h2>개인 포트폴리오 인증</h2>
          <label className="portfolio-field">
            <span>접근 비밀번호</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          </label>
          <button className="portfolio-primary" type="submit" disabled={busy}>
            {busy ? "조회 중…" : "인증하고 조회"}
          </button>
          {error && <p className="portfolio-error" role="alert">{error}</p>}
        </form>
      ) : (
        <>
          {error && <p className="portfolio-error" role="alert">{error}{snapshot && " 마지막으로 조회한 데이터를 표시합니다."}</p>}
          {snapshot ? (
            <>
              <p className="toss-status" role="status">계좌 {snapshot.accountCount}개 · 마지막 조회 {koreaTime.format(new Date(snapshot.checkedAt))} (한국 시간)</p>
              <section className="portfolio-plan-banner" aria-label="스윙 투자 배정">
                <div className="portfolio-plan-banner-heading">
                  <div><span>스윙 매수 배정{!savedSettings && " · 기본 설정"}</span><strong>종목당 목표 투자금 {usd.format(plan.perStockAmount)}</strong></div>
                </div>
                <div className="portfolio-plan-amounts toss-plan-amounts">
                  <div><small>1차 매수 배정</small><strong>{usd.format(plan.firstBuyAmount)}</strong></div>
                  <div><small>2차 매수 추가 배정</small><strong>{usd.format(plan.secondBuyAmount)}</strong></div>
                  <div><small>2차 매수 기준</small><strong>1차 체결가 대비 +{plan.secondEntryRisePct.toFixed(1)}%</strong></div>
                </div>
                <p>USD 종목은 매입금액이 목표액에 도달하면 기본 상태가 2차매수로 표시됩니다. 버튼으로 바꾼 상태는 자동 저장됩니다.</p>
              </section>
              {snapshot.accounts.some(({ holdings }) => holdings.length > 0) && (
                <div className="portfolio-group-filter-tabs toss-stage-filters" role="group" aria-label="매수 상태별 종목 보기">
                  {stageFilters.map(({ value, label }) => (
                    <button type="button" key={value} className={stageFilter === value ? "active" : ""} aria-pressed={stageFilter === value} onClick={() => setStageFilter(value)}>
                      {label}
                    </button>
                  ))}
                </div>
              )}
              {stageError && <p className="portfolio-error" role="alert">{stageError}</p>}
              {!manualStages && stageError && (
                <button type="button" className="portfolio-secondary toss-stage-retry" onClick={() => {
                  setStageError("");
                  setStageLoadAttempt((attempt) => attempt + 1);
                }}>상태 다시 불러오기</button>
              )}
              {savingStage && <p className="toss-status" role="status">매수 상태 저장 중…</p>}
              {snapshot.accounts.length === 0 && <div className="portfolio-panel">조회 가능한 토스증권 계좌가 없습니다.</div>}
              {snapshot.accounts.map(({ holdings, buyingPower }, index) => {
                const usdValue = sumHoldingValues(holdings, "USD");
                const krwValue = holdings.some(({ currency }) => currency === "KRW") ? sumHoldingValues(holdings, "KRW") : undefined;
                const usdBuyingPower = readNumber(buyingPower?.find(({ currency }) => currency === "USD")?.amount);
                const usdTotal = usdValue === null || usdBuyingPower === null ? null : usdValue + usdBuyingPower;

                const visibleHoldings = holdings.map((holding) => {
                  const cost = holdingCost(holding);
                  const trackBudget = holding.currency === "USD" && cost !== null && plan.perStockAmount > 0;
                  const costCents = cost === null ? 0 : Math.round(cost * 100);
                  const automaticStage: BuyStage = trackBudget && plan.secondBuyAmount > 0 &&
                    costCents >= Math.round(plan.perStockAmount * 100) ? 2 : 1;
                  const key = JSON.stringify([index, holding.currency, holding.symbol]);
                  const stage = manualStages?.[key] ?? automaticStage;
                  return { holding, key, cost, trackBudget, stage };
                }).filter(({ stage }) => stageFilter === "all" || stageFilter === stage);

                return (
                  <section key={index} className="portfolio-panel" aria-label={`토스증권 계좌 ${index + 1}`}>
                    <div className="portfolio-panel-heading">
                      <h2>계좌 {index + 1}</h2>
                    </div>
                    <div className="portfolio-summary toss-account-summary">
                      <article className="toss-account-total">
                        <span>달러 합계</span>
                        <strong>{usdTotal === null ? "—" : usd.format(usdTotal)}</strong>
                        <small>달러 주식 평가금액 + 달러 매수 가능</small>
                      </article>
                      <article>
                        <span>총 주식 평가금액</span>
                        <strong>{usdValue === null ? "—" : usd.format(usdValue)}</strong>
                        {krwValue !== undefined && <small>원화 평가액 {krwValue === null ? "조회 불가" : krw.format(krwValue)}</small>}
                      </article>
                      <article>
                        <span>달러 매수 가능</span>
                        <strong>{usdBuyingPower === null ? "—" : usd.format(usdBuyingPower)}</strong>
                        {usdBuyingPower === null && <small>조회 불가</small>}
                      </article>
                    </div>
                    <div className="portfolio-panel-heading">
                      <h2>보유 종목</h2>
                      <span className="portfolio-count">{holdings.length}개</span>
                    </div>
                    {visibleHoldings.length === 0 ? (
                      <p className="toss-status">{holdings.length === 0 ? "보유 종목이 없습니다." : "이 상태에 해당하는 종목이 없습니다."}</p>
                    ) : (
                      <div className="portfolio-table-wrap toss-holdings">
                        <table className="portfolio-table" aria-label={`계좌 ${index + 1} 보유 종목`}>
                          <thead>
                            <tr>
                              <th scope="col">종목</th>
                              <th scope="col">수익률</th>
                              <th scope="col">매수 배정 진행</th>
                              <th scope="col">수량</th>
                              <th scope="col">현재가</th>
                              <th scope="col">평가금액</th>
                            </tr>
                          </thead>
                          <tbody>
                            {visibleHoldings.map(({ holding, key, cost, trackBudget, stage }) => {
                              const { symbol, name, currency, quantity, lastPrice, value, profitLoss } = holding;
                              const rate = readNumber(holding.returnRate) ?? (cost ? divide(profitLoss, cost) : null);
                              return (
                                <tr key={key}>
                                  <td><strong>{symbol}</strong><small>{name}</small></td>
                                  <td className={`toss-return ${profitLossClass(rate)}`}>
                                    <span>{rate === null ? "—" : percent.format(rate)}</span>
                                    <small>{formatMoney(profitLoss, currency)}</small>
                                  </td>
                                  <td className="toss-budget">
                                    <button
                                      type="button"
                                      className={`toss-stage-button toss-stage-${stage}`}
                                      aria-label={`${symbol} ${buyStages[stage]}. ${buyStages[stage === 1 ? 2 : 1]}(으)로 변경`}
                                      disabled={!manualStages || savingStage}
                                      onClick={() => void advanceStage(key, stage)}
                                    >
                                      {buyStages[stage]} <span aria-hidden="true">↻</span>
                                    </button>
                                    {trackBudget && cost !== null ? (
                                      <>
                                        <small>{usd.format(cost)} / {usd.format(plan.perStockAmount)}</small>
                                        <div className="portfolio-budget-track" aria-hidden="true">
                                          <span style={{ width: `${Math.min(100, cost / plan.perStockAmount * 100)}%` }} />
                                        </div>
                                      </>
                                    ) : <small>{currency !== "USD" ? "USD 투자 계획 대상 아님" : "배정 확인 불가"}</small>}
                                  </td>
                                  <td>{formatNumber(quantity)}</td>
                                  <td>{formatMoney(lastPrice, currency)}</td>
                                  <td>{formatMoney(value, currency)}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                );
              })}
            </>
          ) : !error && <p className="toss-status" role="status">토스증권 계좌 조회 중…</p>}
        </>
      )}
    </section>
  );
}

function formatNumber(amount: string) {
  return amount.replace(/^-?\d+/, (integer) => integer.replace(/\B(?=(\d{3})+$)/g, ","));
}

function formatMoney(amount: string | null, currency: string) {
  return amount == null ? "—" : `${formatNumber(amount)} ${currency}`;
}

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const krw = new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW" });
const percent = new Intl.NumberFormat("ko-KR", {
  style: "percent", signDisplay: "exceptZero", minimumFractionDigits: 2, maximumFractionDigits: 2,
});

function readNumber(amount: string | null | undefined) {
  if (typeof amount !== "string" || amount.trim() === "") return null;
  const number = Number(amount);
  return Number.isFinite(number) ? number : null;
}

function sumHoldingValues(holdings: TossHolding[], currency: "USD" | "KRW") {
  let total = 0;
  for (const holding of holdings) {
    if (holding.currency !== currency) continue;
    const value = readNumber(holding.value);
    if (value === null) return null;
    total += value;
  }
  return total;
}

function holdingCost(holding: TossHolding) {
  const purchaseAmount = readNumber(holding.purchaseAmount);
  if (purchaseAmount !== null) return purchaseAmount >= 0 ? purchaseAmount : null;
  const value = readNumber(holding.value);
  const profit = readNumber(holding.profitLoss);
  if (value === null || profit === null) return null;
  const cost = value - profit;
  return Number.isFinite(cost) && cost >= 0 ? cost : null;
}

function divide(amount: string | null, cost: number) {
  const value = readNumber(amount);
  return value === null ? null : value / cost;
}

function profitLossClass(rate: number | null) {
  if (rate === null || Math.abs(rate) < 0.00005) return "";
  return rate < 0 ? "negative" : "positive";
}
