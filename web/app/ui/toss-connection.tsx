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
    setError("");
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
        setPassword("");
        setNeedsAuth(false);
      }

      const response = await fetch("/api/toss", { cache: "no-store" });
      if (response.status === 401) {
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
    if (document.visibilityState === "visible") void checkConnection();
  });

  useEffect(() => {
    if (!refreshing) return;
    const timer = window.setInterval(() => refresh(), refreshMs);
    const onVisibilityChange = () => refresh();
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [refreshing]);

  return (
    <section className="portfolio-page" role="tabpanel" id="toss-panel" aria-labelledby="toss-tab">
      <div className="hero portfolio-hero">
        <h1>토스</h1>
        <p>토스증권 현금 매수 가능 금액과 보유 종목을 조회합니다. 연결 후 이 탭을 보는 동안 30초마다 갱신됩니다.</p>
      </div>
      <form className="portfolio-login" onSubmit={checkConnection}>
        {needsAuth && (
          <label className="portfolio-field">
            <span>포트폴리오 접근 비밀번호</span>
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
          </label>
        )}
        <button className="portfolio-primary" type="submit" disabled={busy}>
          {busy ? "확인 중…" : needsAuth ? "인증하고 연결 확인" : "연결 확인"}
        </button>
        {error && <p className="portfolio-error" role="alert">{error}</p>}
        {snapshot && <p role="status">조회 가능한 계좌 {snapshot.accountCount}개 · 마지막 조회 {koreaTime.format(new Date(snapshot.checkedAt))} (한국 시간)</p>}
      </form>
      {snapshot?.accounts.map(({ holdings, buyingPower }, index) => (
        <section key={index} className="portfolio-login">
          <h2>계좌 {index + 1}</h2>
          <h3>현금 매수 가능 금액</h3>
          <p>토스증권 Open API에서 제공하는 미수 없는 매수 가능 금액입니다. 예수금 잔액은 API에서 제공하지 않습니다.</p>
          {buyingPower ? (
            <dl>
              {buyingPower.map(({ currency, amount }) => (
                <div key={currency}>
                  <dt>{currency === "KRW" ? "원화" : "달러"}</dt>
                  <dd>{amount === null ? "조회 실패" : `${amount.replace(/^-?\d+/, (integer) => integer.replace(/\B(?=(\d{3})+$)/g, ","))} ${currency}`}</dd>
                </div>
              ))}
            </dl>
          ) : <p>중계 서버를 업데이트하면 조회할 수 있습니다.</p>}
          <h3>보유 종목</h3>
          {holdings.length === 0 ? <p>보유 종목이 없습니다.</p> : (
            <ul>
              {holdings.map((holding) => (
                <li key={holding.symbol}>
                  <strong>{holding.name} ({holding.symbol})</strong>
                  <p>수량 {holding.quantity} · 현재가 {holding.lastPrice ?? "—"} · 평가금액 {holding.value ?? "—"} · 평가손익 {holding.profitLoss ?? "—"} ({holding.currency})</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </section>
  );
}
