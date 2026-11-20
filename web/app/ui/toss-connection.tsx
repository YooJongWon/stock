"use client";

import { useState, type FormEvent } from "react";

export default function TossConnection() {
  const [needsAuth, setNeedsAuth] = useState(false);
  const [busy, setBusy] = useState(false);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [accountCount, setAccountCount] = useState<number | null>(null);

  async function checkConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;

    setBusy(true);
    setError("");
    setAccountCount(null);
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
        return;
      }

      const data = await response.json();
      if (!response.ok) {
        setError(data.error ?? "연결 확인에 실패했습니다.");
        return;
      }
      setAccountCount(data.accountCount);
    } catch {
      setError("연결 확인에 실패했습니다. 잠시 후 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="portfolio-page" role="tabpanel" id="toss-panel" aria-labelledby="toss-tab">
      <div className="hero portfolio-hero">
        <h1>토스</h1>
        <p>토스증권 Open API 연결을 확인합니다.</p>
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
        {accountCount !== null && <p role="status">연결되었습니다. 조회 가능한 계좌 {accountCount}개</p>}
      </form>
    </section>
  );
}
