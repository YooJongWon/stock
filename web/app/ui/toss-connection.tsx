"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";

import type { TossSnapshot } from "@/lib/toss";

const refreshMs = 30_000;
const koreaTime = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", dateStyle: "short", timeStyle: "medium" });

export default function TossConnection() {
  const [needsAuth, setNeedsAuth] = useState(false);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [snapshot, setSnapshot] = useState<TossSnapshot | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const inFlight = useRef(false);

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
              {snapshot.accounts.length === 0 && <div className="portfolio-panel">조회 가능한 토스증권 계좌가 없습니다.</div>}
              {snapshot.accounts.map(({ holdings, buyingPower }, index) => (
                <section key={index} className="portfolio-panel" aria-label={`토스증권 계좌 ${index + 1}`}>
                  <div className="portfolio-panel-heading">
                    <div>
                      <h2>계좌 {index + 1}</h2>
                      <p>현금 매수 가능 금액은 토스증권 Open API에서 미수 없이 매수할 수 있는 금액으로 제공됩니다.</p>
                    </div>
                  </div>
                  <div className="portfolio-summary">
                    {cashCurrencies.map(({ currency, label }) => {
                      const amount = buyingPower?.find((item) => item.currency === currency)?.amount;
                      return (
                        <article key={currency}>
                          <span>{label} 매수 가능</span>
                          <strong>{amount == null ? "—" : formatNumber(amount)}</strong>
                          <small>{!buyingPower ? "중계 서버 업데이트 필요" : amount == null ? "조회 실패" : currency}</small>
                        </article>
                      );
                    })}
                    <article><span>보유 종목</span><strong>{holdings.length}개</strong></article>
                  </div>
                  <div className="portfolio-panel-heading"><h2>보유 종목</h2></div>
                  {holdings.length === 0 ? (
                    <p className="toss-status">보유 종목이 없습니다.</p>
                  ) : (
                    <div className="portfolio-table-wrap toss-holdings">
                      <table className="portfolio-table" aria-label={`계좌 ${index + 1} 보유 종목`}>
                        <thead>
                          <tr>
                            <th scope="col">종목</th>
                            <th scope="col">수량</th>
                            <th scope="col">현재가</th>
                            <th scope="col">평가금액</th>
                            <th scope="col">평가손익</th>
                          </tr>
                        </thead>
                        <tbody>
                          {holdings.map(({ symbol, name, currency, quantity, lastPrice, value, profitLoss }) => (
                            <tr key={`${currency}:${symbol}`}>
                              <td><strong>{symbol}</strong><small>{name}</small></td>
                              <td>{formatNumber(quantity)}</td>
                              <td>{formatMoney(lastPrice, currency)}</td>
                              <td>{formatMoney(value, currency)}</td>
                              <td className={profitLossClass(profitLoss)}>{formatMoney(profitLoss, currency)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              ))}
            </>
          ) : !error && <p className="toss-status" role="status">토스증권 계좌 조회 중…</p>}
        </>
      )}
    </section>
  );
}

const cashCurrencies = [
  { currency: "KRW", label: "원화" },
  { currency: "USD", label: "달러" },
] as const;

function formatNumber(amount: string) {
  return amount.replace(/^-?\d+/, (integer) => integer.replace(/\B(?=(\d{3})+$)/g, ","));
}

function formatMoney(amount: string | null, currency: string) {
  return amount == null ? "—" : `${formatNumber(amount)} ${currency}`;
}

function profitLossClass(amount: string | null) {
  if (amount === null || Number(amount) === 0) return undefined;
  return amount.startsWith("-") ? "negative" : "positive";
}
