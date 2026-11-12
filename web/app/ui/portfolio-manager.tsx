"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Position = {
  id: string;
  ticker: string;
  companyName: string;
  shares: number;
  avgPrice: number;
  currentPrice: number;
  note: string;
};
type PositionDraft = Omit<Position, "id">;
type PortfolioData = { cashBalance: number; positions: Position[] };

const EMPTY_DRAFT: PositionDraft = {
  ticker: "", companyName: "", shares: 0, avgPrice: 0, currentPrice: 0, note: "",
};
const usd = (value: number) => new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 2,
}).format(Number.isFinite(value) ? value : 0);
const numberText = (value: number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);

function NumericField({ label, value, onChange, step = "0.01", min = "0" }: {
  label: string; value: string | number; onChange: (value: string) => void; step?: string; min?: string;
}) {
  return <label className="portfolio-field">
    <span>{label}</span>
    <input type="number" min={min} step={step} value={value} onChange={(event) => onChange(event.target.value)} />
  </label>;
}

export default function PortfolioManager() {
  const [authenticated, setAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);
  const [password, setPassword] = useState("");
  const [cashBalance, setCashBalance] = useState("0");
  const [positions, setPositions] = useState<Position[]>([]);
  const [draft, setDraft] = useState<PositionDraft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<PositionDraft>(EMPTY_DRAFT);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/portfolio", { cache: "no-store" });
      if (response.status === 401) {
        setAuthenticated(false);
        return;
      }
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "포트폴리오를 불러오지 못했습니다.");
      const data = payload as PortfolioData;
      setCashBalance(String(data.cashBalance ?? 0));
      setPositions(Array.isArray(data.positions) ? data.positions : []);
      setAuthenticated(true);
      setDirty(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const totals = useMemo(() => {
    const cost = positions.reduce((sum, item) => sum + item.shares * item.avgPrice, 0);
    const priced = positions.filter((item) => item.currentPrice > 0);
    const marketValue = priced.reduce((sum, item) => sum + item.shares * item.currentPrice, 0);
    const profit = priced.reduce((sum, item) => sum + item.shares * (item.currentPrice - item.avgPrice), 0);
    const pricedCost = priced.reduce((sum, item) => sum + item.shares * item.avgPrice, 0);
    const cash = Math.max(0, Number(cashBalance) || 0);
    const totalAssets = cash + marketValue;
    return {
      cost, marketValue, profit, returnPct: pricedCost > 0 ? profit / pricedCost * 100 : 0,
      cash, totalAssets, cashPct: totalAssets > 0 ? cash / totalAssets * 100 : 0,
    };
  }, [cashBalance, positions]);

  const authenticate = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    try {
      const response = await fetch("/api/portfolio/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "인증에 실패했습니다.");
      setPassword("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "인증에 실패했습니다.");
    }
  };

  const updateDraft = (key: keyof PositionDraft, value: string) => {
    setDraft((old) => ({ ...old, [key]: key === "ticker" || key === "companyName" || key === "note" ? value : Number(value) }));
  };
  const updateEditDraft = (key: keyof PositionDraft, value: string) => {
    setEditDraft((old) => ({ ...old, [key]: key === "ticker" || key === "companyName" || key === "note" ? value : Number(value) }));
  };

  const addPosition = (event: FormEvent) => {
    event.preventDefault();
    const ticker = draft.ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker) || draft.shares <= 0 || draft.avgPrice <= 0 || draft.currentPrice < 0) {
      setError("티커, 보유 수량, 평균 매수가를 올바르게 입력해 주세요.");
      return;
    }
    const next: Position = { ...draft, id: crypto.randomUUID(), ticker };
    setPositions((old) => [...old, next]);
    setDraft(EMPTY_DRAFT);
    setDirty(true);
    setError("");
    setMessage("새 종목이 목록에 추가됐습니다. 저장 버튼을 눌러 반영하세요.");
  };

  const startEdit = (position: Position) => {
    setEditingId(position.id);
    setEditDraft({
      ticker: position.ticker, companyName: position.companyName, shares: position.shares,
      avgPrice: position.avgPrice, currentPrice: position.currentPrice, note: position.note,
    });
  };

  const commitEdit = (event: FormEvent) => {
    event.preventDefault();
    if (!editingId || editDraft.shares <= 0 || editDraft.avgPrice <= 0 || editDraft.currentPrice < 0) {
      setError("수량과 평균 매수가는 0보다 커야 합니다.");
      return;
    }
    const ticker = editDraft.ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) {
      setError("티커 형식이 올바르지 않습니다.");
      return;
    }
    setPositions((old) => old.map((item) => item.id === editingId ? { ...editDraft, id: editingId, ticker } : item));
    setEditingId(null);
    setDirty(true);
    setError("");
    setMessage("수정 내용이 반영됐습니다. 저장 버튼을 눌러 저장하세요.");
  };

  const deletePosition = (id: string) => {
    if (!window.confirm("이 보유 종목을 삭제할까요?")) return;
    setPositions((old) => old.filter((item) => item.id !== id));
    setDirty(true);
    if (editingId === id) setEditingId(null);
    setMessage("삭제 내용이 반영됐습니다. 저장 버튼을 눌러 저장하세요.");
  };

  const save = async () => {
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const cash = Number(cashBalance);
      if (!Number.isFinite(cash) || cash < 0) throw new Error("예수금은 0 이상의 숫자로 입력해 주세요.");
      const response = await fetch("/api/portfolio", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cashBalance: cash, positions }),
      });
      const payload = await response.json();
      if (response.status === 401) {
        setAuthenticated(false);
        throw new Error("세션이 만료됐습니다. 다시 인증해 주세요.");
      }
      if (!response.ok) throw new Error(payload.error || "저장에 실패했습니다.");
      setDirty(false);
      setMessage("예수금과 보유 종목을 Supabase에 저장했습니다.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "저장에 실패했습니다.");
    } finally {
      setSaving(false);
    }
  };

  const logout = async () => {
    await fetch("/api/portfolio/auth", { method: "DELETE" });
    setAuthenticated(false);
    setMessage("");
  };

  const field = (label: string, key: keyof PositionDraft, value: PositionDraft[keyof PositionDraft], onChange: (key: keyof PositionDraft, value: string) => void, step?: string) =>
    <label className="portfolio-field" key={key}><span>{label}</span>
      <input
        type={typeof value === "number" ? "number" : "text"}
        min={typeof value === "number" ? "0" : undefined}
        step={typeof value === "number" ? step || "0.01" : undefined}
        value={String(value)}
        onChange={(event) => onChange(key, event.target.value)}
      />
    </label>;

  if (loading) return <section className="portfolio-page"><p className="portfolio-feedback">포트폴리오 정보를 확인하고 있습니다…</p></section>;

  if (!authenticated) return <section className="portfolio-page">
    <div className="hero portfolio-hero"><div className="eyebrow">PRIVATE INVESTMENT TRACKER</div><h1>내 포트폴리오</h1><p>예수금과 보유 종목을 여러 기기에서 함께 관리합니다.</p></div>
    <form className="portfolio-login" onSubmit={authenticate}>
      <h2>개인 포트폴리오 인증</h2>
      <p>본인만 사용하는 비밀번호를 입력해 주세요. 인증은 이 브라우저에서 7일간 유지됩니다.</p>
      <label className="portfolio-field"><span>접근 비밀번호</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required /></label>
      <button className="portfolio-primary" type="submit">인증하고 열기</button>
      {error && <p className="portfolio-error">{error}</p>}
    </form>
  </section>;

  return <section className="portfolio-page">
    <div className="portfolio-heading-row">
      <div className="hero portfolio-hero"><div className="eyebrow">PRIVATE INVESTMENT TRACKER</div><h1>내 포트폴리오</h1><p>보유 수량과 평균 매수가, 현재가를 직접 입력해 손익과 자산 구성을 관리합니다.</p></div>
      <button className="portfolio-logout" type="button" onClick={logout}>로그아웃</button>
    </div>

    <div className="portfolio-summary">
      <article><span>총 자산 (평가액 + 예수금)</span><strong>{usd(totals.totalAssets)}</strong><small>현재가 미입력 종목은 평가액에서 제외</small></article>
      <article><span>보유 주식 평가액</span><strong>{usd(totals.marketValue)}</strong><small>현재가 직접 입력 기준</small></article>
      <article><span>총 매수 원금</span><strong>{usd(totals.cost)}</strong><small>{positions.length}개 종목</small></article>
      <article className={totals.profit >= 0 ? "positive" : "negative"}><span>평가 손익</span><strong>{totals.profit >= 0 ? "+" : ""}{usd(totals.profit)}</strong><small>{totals.returnPct >= 0 ? "+" : ""}{totals.returnPct.toFixed(2)}%</small></article>
      <article><span>예수금 비중</span><strong>{totals.cashPct.toFixed(1)}%</strong><small>{usd(totals.cash)}</small></article>
    </div>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">CASH BALANCE</div><h2>남은 예수금</h2><p>계좌의 남은 현금을 USD 기준으로 입력합니다.</p></div></div>
      <div className="portfolio-cash-row">
        <NumericField label="예수금 (USD)" value={cashBalance} onChange={(value) => { setCashBalance(value); setDirty(true); }} step="0.01" />
        <div className="portfolio-save-area"><span>{dirty ? "저장되지 않은 변경사항이 있습니다." : message || "모든 변경사항이 저장되었습니다."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
      </div>
    </section>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">HOLDINGS</div><h2>보유 종목</h2><p>주식 수량, 평균 매수가, 현재가를 직접 입력합니다. 시세 자동 연동은 아직 사용하지 않습니다.</p></div><span className="portfolio-count">{positions.length} / 100</span></div>
      <form className="portfolio-position-form" onSubmit={addPosition}>
        <h3>보유 종목 추가</h3>
        <div className="portfolio-form-grid">
          {field("티커", "ticker", draft.ticker, updateDraft)}
          {field("회사명", "companyName", draft.companyName, updateDraft)}
          {field("보유 수량", "shares", draft.shares, updateDraft, "0.0001")}
          {field("평균 매수가 (USD)", "avgPrice", draft.avgPrice, updateDraft)}
          {field("현재가 (USD)", "currentPrice", draft.currentPrice, updateDraft)}
          {field("메모 (선택)", "note", draft.note, updateDraft)}
        </div>
        <button className="portfolio-secondary" type="submit">+ 보유 종목 추가</button>
      </form>

      {positions.length ? <div className="portfolio-table-wrap"><table className="portfolio-table">
        <thead><tr><th>종목</th><th>수량</th><th>평균 매수가</th><th>현재가</th><th>매수 원금</th><th>평가액</th><th>평가 손익</th><th>관리</th></tr></thead>
        <tbody>{positions.map((item) => {
          const cost = item.shares * item.avgPrice;
          const value = item.currentPrice > 0 ? item.shares * item.currentPrice : null;
          const pnl = value === null ? null : value - cost;
          const pct = pnl === null || cost <= 0 ? null : pnl / cost * 100;
          return <tr key={item.id}>
            <td><strong>{item.ticker}</strong><small>{item.companyName || "회사명 미입력"}</small>{item.note && <small>{item.note}</small>}</td>
            <td>{numberText(item.shares)}</td><td>{usd(item.avgPrice)}</td><td>{item.currentPrice > 0 ? usd(item.currentPrice) : "미입력"}</td>
            <td>{usd(cost)}</td><td>{value === null ? "—" : usd(value)}</td>
            <td className={pnl === null ? "" : pnl >= 0 ? "positive" : "negative"}>{pnl === null ? "—" : <>{pnl >= 0 ? "+" : ""}{usd(pnl)}<small>{pct! >= 0 ? "+" : ""}{pct!.toFixed(2)}%</small></>}</td>
            <td><div className="portfolio-row-actions"><button type="button" onClick={() => startEdit(item)}>수정</button><button type="button" onClick={() => deletePosition(item.id)}>삭제</button></div></td>
          </tr>;
        })}</tbody>
      </table></div> : <div className="portfolio-empty">아직 등록한 보유 종목이 없습니다. 위 입력란에서 첫 종목을 추가하세요.</div>}

      {editingId && <form className="portfolio-edit-form" onSubmit={commitEdit}>
        <h3>{editDraft.ticker || "종목"} 수정</h3>
        <div className="portfolio-form-grid">
          {field("티커", "ticker", editDraft.ticker, updateEditDraft)}
          {field("회사명", "companyName", editDraft.companyName, updateEditDraft)}
          {field("보유 수량", "shares", editDraft.shares, updateEditDraft, "0.0001")}
          {field("평균 매수가 (USD)", "avgPrice", editDraft.avgPrice, updateEditDraft)}
          {field("현재가 (USD)", "currentPrice", editDraft.currentPrice, updateEditDraft)}
          {field("메모 (선택)", "note", editDraft.note, updateEditDraft)}
        </div>
        <div className="portfolio-row-actions"><button className="portfolio-primary" type="submit">수정 반영</button><button className="portfolio-secondary" type="button" onClick={() => setEditingId(null)}>취소</button></div>
      </form>}
    </section>

    {error && <p className="portfolio-error portfolio-bottom-message">{error}</p>}
    <div className="portfolio-bottom-actions"><span>{message || "종목 추가·수정·삭제 후 ‘변경사항 저장’을 눌러 주세요."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
    <div className="portfolio-note">이 화면의 종목 정보와 현재가는 직접 입력한 값입니다. 자동 시세·증권사 계좌 연동은 하지 않습니다. 저장된 정보는 인증된 사용자만 조회할 수 있습니다.</div>
  </section>;
}
