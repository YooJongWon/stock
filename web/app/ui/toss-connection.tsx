"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";

import type { MonthlyDashboardResult } from "./dashboard";
import type { TossHolding, TossSnapshot } from "@/lib/toss";

const refreshMs = 30_000;
const koreaTime = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "medium" });

function tickerKey(symbol: string) {
  return symbol.trim().toUpperCase().replace(/\./g, "-");
}

export default function TossConnection({ momentum, positionWeight }: {
  momentum: MonthlyDashboardResult["monthly_momentum"];
  positionWeight: number;
}) {
  const [needsAuth, setNeedsAuth] = useState(false);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [snapshot, setSnapshot] = useState<TossSnapshot | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [capital, setCapital] = useState<number | null>(null);
  const [defaultCapital, setDefaultCapital] = useState(false);
  const inFlight = useRef(false);
  const hasSnapshot = snapshot !== null;
  const ranked = new Map(momentum?.items.map(({ ticker }, index) => [tickerKey(ticker), index + 1]));
  const previous = new Set(momentum?.previous?.items.map(({ ticker }) => tickerKey(ticker)));
  const held = new Set(snapshot?.accounts.flatMap(({ holdings }) =>
    holdings.filter(({ currency }) => currency === "USD").map(({ symbol }) => tickerKey(symbol))
  ));
  const missing = momentum?.items.filter(({ ticker }) => !held.has(tickerKey(ticker)));

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
        setCapital(null);
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
        if (controller.signal.aborted) return;
        const stored = data.calculatorInputs?.total;
        const total = stored == null ? 10000 : readNumber(stored);
        setCapital(total !== null && total >= 0 ? total : null);
        setDefaultCapital(stored == null);
      } catch {
        // Keep allocation unavailable when the saved capital cannot be read.
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
              <section className="portfolio-plan-banner" aria-label="월간 모멘텀 배정">
                <div className="portfolio-plan-banner-heading">
                  <div><span>월간 모멘텀 · {momentum ? momentum.reference_date + " 기준" : "순위 확인 대기"}</span>
                    <strong>종목당 목표 {capital === null ? "—" : usd.format(capital * positionWeight)}</strong></div>
                </div>
                <p>{defaultCapital ? "기본" : "월간 모멘텀"} 배정 자금 {capital === null ? "확인 대기" : usd.format(capital)} · 종목당 {positionWeight * 100}% · 목표 현금 37.5%</p>
                {missing && snapshot.accounts.length > 0 && <p><strong>미보유 상위 종목</strong> · {missing.length ? missing.map(({ ticker }) => ticker).join(" · ") : "모두 보유 중"}</p>}
              </section>
              {snapshot.accounts.length === 0 && <div className="portfolio-panel">조회 가능한 토스증권 계좌가 없습니다.</div>}
              {snapshot.accounts.map(({ holdings, buyingPower }, index) => {
                const usdValue = sumHoldingValues(holdings, "USD");
                const krwValue = holdings.some(({ currency }) => currency === "KRW") ? sumHoldingValues(holdings, "KRW") : undefined;
                const usdBuyingPower = readNumber(buyingPower?.find(({ currency }) => currency === "USD")?.amount);
                const usdTotal = usdValue === null || usdBuyingPower === null ? null : usdValue + usdBuyingPower;

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
                    {holdings.length === 0 ? (
                      <p className="toss-status">보유 종목이 없습니다.</p>
                    ) : (
                      <div className="portfolio-table-wrap toss-holdings">
                        <table className="portfolio-table" aria-label={`계좌 ${index + 1} 보유 종목`}>
                          <thead>
                            <tr>
                              <th scope="col">종목</th>
                              <th scope="col">수익률</th>
                              <th scope="col">월간 순위</th>
                              <th scope="col">수량</th>
                              <th scope="col">평균 매수가</th>
                              <th scope="col">현재가</th>
                              <th scope="col">평가금액</th>
                            </tr>
                          </thead>
                          <tbody>
                            {holdings.map((holding) => {
                              const cost = holdingCost(holding);
                              const { symbol, name, currency, quantity, lastPrice, value, profitLoss } = holding;
                              const rate = readNumber(holding.returnRate) ?? (cost ? divide(profitLoss, cost) : null);
                              const ticker = tickerKey(symbol);
                              const rank = currency === "USD" ? ranked.get(ticker) : undefined;
                              return (
                                <tr key={currency + ":" + symbol}>
                                  <td><strong>{symbol}</strong><small>{name}</small></td>
                                  <td className={`toss-return ${profitLossClass(rate)}`}>
                                    <span>{rate === null ? "—" : percent.format(rate)}</span>
                                    <small>{formatMoney(profitLoss, currency)}</small>
                                  </td>
                                  <td>{currency !== "USD" ? "대상 외" : !ranked.size ? "순위 확인 대기" : rank ? `상위 ${rank}위` : previous.has(ticker) ? "목록 이탈" : "목록 밖"}</td>
                                  <td>{formatNumber(quantity)}</td>
                                  <td>{formatAveragePurchasePrice(holding, cost)}</td>
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

function formatAveragePurchasePrice(holding: TossHolding, cost: number | null) {
  const reported = readNumber(holding.averagePurchasePrice);
  if (reported !== null && reported >= 0) return formatMoney(holding.averagePurchasePrice!, holding.currency);
  const quantity = readNumber(holding.quantity);
  if (cost === null || quantity === null || quantity <= 0) return "—";
  const price = cost / quantity;
  if (!Number.isFinite(price)) return "—";
  return price.toLocaleString("ko-KR", { maximumFractionDigits: 4 }) + " " + holding.currency + " (계산)";
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
