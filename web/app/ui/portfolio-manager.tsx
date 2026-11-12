"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Position = {
  id: string;
  ticker: string;
  note: string;
  firstBuyAmount: number;
  secondBuyAmount: number;
  legacyInvestedAmount: number;
  buyStage: number;
  sellStage: number;
  exitStatus: "active" | "stopped" | "completed";
};
type PositionDraft = Pick<Position, "ticker" | "note">;
type BuyStageEditor = { positionId: string; stage: 1 | 2 };

type TickerSearchResult = { symbol: string; name: string; exchange: string };
type PortfolioData = { cashBalance: number; positions: Position[] };

const EMPTY_DRAFT: PositionDraft = { ticker: "", note: "" };
const totalInvested = (position: Position) =>
  position.firstBuyAmount + position.secondBuyAmount + position.legacyInvestedAmount;
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

function TickerSearchField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const [query, setQuery] = useState(value);
  const [results, setResults] = useState<TickerSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");

  useEffect(() => { setQuery(value); }, [value]);

  useEffect(() => {
    const term = query.trim();
    if (!open || term.length < 2) {
      setResults([]);
      setSearching(false);
      setSearchError("");
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setSearchError("");
      try {
        const response = await fetch(`/api/portfolio/ticker-search?q=${encodeURIComponent(term)}`, {
          cache: "no-store",
          signal: controller.signal,
        });
        const payload = await response.json() as { results?: TickerSearchResult[]; error?: string };
        if (!response.ok) throw new Error(payload.error || "종목 검색에 실패했습니다.");
        setResults(Array.isArray(payload.results) ? payload.results : []);
      } catch (caught) {
        if (controller.signal.aborted) return;
        setResults([]);
        setSearchError(caught instanceof Error ? caught.message : "검색 서비스에 연결하지 못했습니다.");
      } finally {
        if (!controller.signal.aborted) setSearching(false);
      }
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);

  const choose = (result: TickerSearchResult) => {
    setQuery(result.symbol);
    onChange(result.symbol);
    setOpen(false);
    setResults([]);
  };

  return <label className="portfolio-field ticker-search-field">
    <span>티커 검색 (회사명 또는 티커)</span>
    <input
      type="text"
      value={query}
      placeholder="예: Apple 또는 AAPL"
      autoComplete="off"
      role="combobox"
      aria-autocomplete="list"
      aria-expanded={open && query.trim().length >= 2}
      onFocus={() => setOpen(true)}
      onChange={(event) => {
        setQuery(event.target.value);
        onChange(event.target.value);
        setOpen(true);
      }}
      onBlur={() => window.setTimeout(() => setOpen(false), 150)}
    />
    {open && query.trim().length >= 2 && <div className="ticker-search-results" role="listbox">
      {searching ? <div className="ticker-search-message">종목 검색 중…</div>
        : searchError ? <div className="ticker-search-message">{searchError}</div>
        : results.length ? results.map((result) => <button
          type="button"
          role="option"
          aria-selected={false}
          key={result.symbol}
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => choose(result)}
        >
          <strong>{result.symbol}</strong>
          <span>{result.name}</span>
          <small>{result.exchange}</small>
        </button>)
        : <div className="ticker-search-message">검색 결과가 없습니다. 티커를 직접 입력할 수도 있습니다.</div>}
    </div>}
    <small className="ticker-search-hint">검색 결과에서 종목을 선택하면 티커만 저장됩니다.</small>
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
  const [buyStageEditor, setBuyStageEditor] = useState<BuyStageEditor | null>(null);
  const [buyAmountInput, setBuyAmountInput] = useState("");
  const [buyStageError, setBuyStageError] = useState("");
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
      setPositions(Array.isArray(data.positions) ? data.positions.map((item) => ({
        id: item.id,
        ticker: item.ticker,
        note: item.note || "",
        firstBuyAmount: Number(item.firstBuyAmount) || 0,
        secondBuyAmount: Number(item.secondBuyAmount) || 0,
        legacyInvestedAmount: Number(item.legacyInvestedAmount) || 0,
        buyStage: Number.isInteger(item.buyStage) && item.buyStage >= 0 && item.buyStage <= 2 ? item.buyStage : 0,
        sellStage: Number.isInteger(item.sellStage) && item.sellStage >= 0 && item.sellStage <= 3 ? item.sellStage : 0,
        exitStatus: item.exitStatus === "stopped" || item.exitStatus === "completed" ? item.exitStatus : "active",
      })) : []);
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
    const cost = positions.reduce((sum, item) => sum + totalInvested(item), 0);
    const cash = Math.max(0, Number(cashBalance) || 0);
    return {
      cost,
      cash,
      positionCount: positions.filter((item) => item.exitStatus === "active").length,
      firstBuyCount: positions.filter((item) => item.buyStage >= 1 && item.exitStatus === "active").length,
      secondBuyCount: positions.filter((item) => item.buyStage >= 2 && item.exitStatus === "active").length,
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
    setDraft((old) => ({ ...old, [key]: value }));
  };
  const updateEditDraft = (key: keyof PositionDraft, value: string) => {
    setEditDraft((old) => ({ ...old, [key]: value }));
  };

  const addPosition = (event: FormEvent) => {
    event.preventDefault();
    const ticker = draft.ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) {
      setError("티커를 검색 결과에서 선택하거나 올바른 티커를 입력해 주세요.");
      return;
    }
    if (positions.some((item) => item.ticker === ticker && item.exitStatus === "active")) {
      setError("이미 보유 목록에 있는 종목입니다.");
      return;
    }
    const next: Position = {
      id: crypto.randomUUID(),
      ticker,
      note: draft.note.trim(),
      firstBuyAmount: 0,
      secondBuyAmount: 0,
      legacyInvestedAmount: 0,
      buyStage: 0,
      sellStage: 0,
      exitStatus: "active",
    };
    setPositions((old) => [...old, next]);
    setDraft(EMPTY_DRAFT);
    setDirty(true);
    setError("");
    setMessage("새 종목이 추가됐습니다. 1차 매수 버튼에서 실제 매수 금액을 입력하세요.");
  };

  const startEdit = (position: Position) => {
    setEditingId(position.id);
    setEditDraft({ ticker: position.ticker, note: position.note });
  };

  const commitEdit = (event: FormEvent) => {
    event.preventDefault();
    if (!editingId) return;
    const ticker = editDraft.ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) {
      setError("티커 형식이 올바르지 않습니다.");
      return;
    }
    if (positions.some((item) => item.id !== editingId && item.ticker === ticker && item.exitStatus === "active")) {
      setError("이미 보유 목록에 있는 종목입니다.");
      return;
    }
    setPositions((old) => old.map((item) => item.id === editingId ? { ...item, ticker, note: editDraft.note.trim() } : item));
    setEditingId(null);
    setDirty(true);
    setError("");
    setMessage("수정 내용이 반영됐습니다. 저장 버튼을 눌러 저장하세요.");
  };

  const openBuyStageEditor = (position: Position, stage: 1 | 2) => {
    setBuyStageEditor({ positionId: position.id, stage });
    setBuyAmountInput("");
    setBuyStageError("");
  };

  const completeBuyStage = (event: FormEvent) => {
    event.preventDefault();
    if (!buyStageEditor) return;
    const amount = Number(buyAmountInput);
    if (!Number.isFinite(amount) || amount <= 0) {
      setBuyStageError("실제 매수 금액을 USD로 입력해 주세요.");
      return;
    }
    const { positionId, stage } = buyStageEditor;
    setPositions((old) => old.map((item) => {
      if (item.id !== positionId) return item;
      return stage === 1
        ? { ...item, firstBuyAmount: amount, buyStage: 1 }
        : { ...item, secondBuyAmount: amount, buyStage: 2 };
    }));
    setDirty(true);
    setBuyStageEditor(null);
    setBuyAmountInput("");
    setBuyStageError("");
    setMessage(`${stage}차 매수 금액이 반영됐습니다. 변경사항 저장을 눌러 저장하세요.`);
  };

  const completeSellStage = (position: Position) => {
    if (position.exitStatus !== "active" || position.buyStage < 2 || position.sellStage >= 3) return;
    const nextStage = position.sellStage + 1;
    if (!window.confirm(`${position.ticker} ${nextStage}차 매도 체결을 기록할까요?`)) return;
    setPositions((old) => old.map((item) => item.id === position.id ? {
      ...item,
      sellStage: nextStage,
      exitStatus: nextStage === 3 ? "completed" : "active",
    } : item));
    setDirty(true);
    setMessage(nextStage === 3
      ? `${position.ticker} 분할매도 완료로 표시했습니다. 저장 버튼을 눌러 주세요.`
      : `${position.ticker} ${nextStage}차 매도를 기록했습니다. 저장 버튼을 눌러 주세요.`);
  };

  const stopLossPosition = (position: Position) => {
    if (position.exitStatus !== "active" || position.buyStage < 1) return;
    if (!window.confirm(`${position.ticker} 손절 완료로 처리할까요? 실제 매도 체결 후 진행해 주세요.`)) return;
    setPositions((old) => old.map((item) => item.id === position.id ? { ...item, exitStatus: "stopped" } : item));
    setDirty(true);
    setMessage(`${position.ticker} 손절 종료로 표시했습니다. 저장 버튼을 눌러 주세요.`);
  };

  const deletePosition = (id: string) => {
    if (!window.confirm("이 보유 종목을 삭제할까요?")) return;
    setPositions((old) => old.filter((item) => item.id !== id));
    setDirty(true);
    if (editingId === id) setEditingId(null);
    if (buyStageEditor?.positionId === id) setBuyStageEditor(null);
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
      <div className="hero portfolio-hero"><div className="eyebrow">PRIVATE INVESTMENT TRACKER</div><h1>내 포트폴리오</h1><p>실제 투입한 매수 금액과 분할매수·매도 진행 단계를 기록합니다.</p></div>
      <button className="portfolio-logout" type="button" onClick={logout}>로그아웃</button>
    </div>

    <div className="portfolio-summary portfolio-summary-simple">
      <article><span>총 매수 원금</span><strong>{usd(totals.cost)}</strong><small>1차·2차 매수 금액 및 기존 원금 포함</small></article>
      <article><span>남은 예수금</span><strong>{usd(totals.cash)}</strong><small>직접 입력한 USD 잔액</small></article>
      <article><span>보유 종목</span><strong>{totals.positionCount}개</strong><small>1차 매수 {totals.firstBuyCount}개 · 2차 매수 {totals.secondBuyCount}개 진행</small></article>
    </div>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">CASH BALANCE</div><h2>남은 예수금</h2><p>계좌의 남은 현금을 USD 기준으로 입력합니다.</p></div></div>
      <div className="portfolio-cash-row">
        <NumericField label="예수금 (USD)" value={cashBalance} onChange={(value) => { setCashBalance(value); setDirty(true); }} step="0.01" />
        <div className="portfolio-save-area"><span>{dirty ? "저장되지 않은 변경사항이 있습니다." : message || "모든 변경사항이 저장되었습니다."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
      </div>
    </section>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">HOLDINGS</div><h2>보유 종목</h2><p>종목을 등록한 뒤 1차 매수 금액을 입력하고 단계별 거래를 진행하세요.</p></div><span className="portfolio-count">{positions.length} / 100</span></div>
      <form className="portfolio-position-form" onSubmit={addPosition}>
        <h3>보유 종목 추가</h3>
        <div className="portfolio-form-grid">
          <TickerSearchField value={draft.ticker} onChange={(value) => updateDraft("ticker", value)} />
          <label className="portfolio-field"><span>메모 (선택)</span><input type="text" value={draft.note} onChange={(event) => updateDraft("note", event.target.value)} /></label>
        </div>
        <button className="portfolio-secondary" type="submit">+ 종목 등록 (1차 매수 전)</button>
      </form>

      {positions.length ? <div className="portfolio-table-wrap"><table className="portfolio-table portfolio-workflow-table">
        <thead><tr><th>종목</th><th>누적 매수금액</th><th>매수 진행</th><th>매도 진행</th><th>관리</th></tr></thead>
        <tbody>{positions.map((item) => {
          const invested = totalInvested(item);
          const isActive = item.exitStatus === "active";
          return <tr key={item.id}>
            <td><strong>{item.ticker}</strong>{item.note && <small>{item.note}</small>}</td>
            <td className="portfolio-invested-cell">
              <strong>{usd(invested)}</strong>
              <small>1차 {usd(item.firstBuyAmount)} · 2차 {usd(item.secondBuyAmount)}</small>
              {item.legacyInvestedAmount > 0 && <small>기존 기록 {usd(item.legacyInvestedAmount)} (차수 미분류)</small>}
            </td>
            <td><div className="portfolio-stage-actions">
              <div className="portfolio-stage-line">
                {item.buyStage >= 1
                  ? <span className="portfolio-stage-done">✓ 1차 매수 완료</span>
                  : isActive
                    ? <button type="button" className="portfolio-stage-next buy" onClick={() => openBuyStageEditor(item, 1)}>1차 매수 금액 입력</button>
                    : <span className="portfolio-stage-locked">1차 매수 전</span>}
              </div>
              <div className="portfolio-stage-line">
                {item.buyStage >= 2
                  ? <span className="portfolio-stage-done">✓ 2차 매수 완료</span>
                  : item.buyStage === 1 && isActive
                    ? <button type="button" className="portfolio-stage-next buy" onClick={() => openBuyStageEditor(item, 2)}>2차 매수 준비 · 금액 입력</button>
                    : <span className="portfolio-stage-locked">1차 매수 후 2차 매수 준비</span>}
              </div>
            </div></td>
            <td><div className="portfolio-stage-actions">
              {item.exitStatus === "stopped"
                ? <span className="portfolio-exit-status stopped">손절 종료</span>
                : item.exitStatus === "completed"
                  ? <span className="portfolio-exit-status completed">분할매도 완료</span>
                  : item.buyStage < 2
                    ? <span className="portfolio-stage-locked">2차 매수 완료 후 익절 가능</span>
                    : <>
                      <div className="portfolio-stage-line">
                        {item.sellStage >= 1
                          ? <span className="portfolio-stage-done">✓ 1차 매도 완료</span>
                          : <button type="button" className="portfolio-stage-next sell" onClick={() => completeSellStage(item)}>1차 매도 +8% · 40% 완료</button>}
                      </div>
                      {item.sellStage >= 1 && <div className="portfolio-stage-line">
                        {item.sellStage >= 2
                          ? <span className="portfolio-stage-done">✓ 2차 매도 완료</span>
                          : <button type="button" className="portfolio-stage-next sell" onClick={() => completeSellStage(item)}>2차 매도 +9% · 30% 완료</button>}
                      </div>}
                      {item.sellStage >= 2 && <div className="portfolio-stage-line">
                        {item.sellStage >= 3
                          ? <span className="portfolio-stage-done">✓ 3차 매도 완료</span>
                          : <button type="button" className="portfolio-stage-next sell" onClick={() => completeSellStage(item)}>3차 매도 +10% · 30% 완료</button>}
                      </div>}
                    </>}
              {isActive && item.buyStage >= 1 && <button type="button" className="portfolio-stop-button" onClick={() => stopLossPosition(item)}>손절 -5% 완료 처리</button>}
            </div></td>
            <td><div className="portfolio-row-actions"><button type="button" onClick={() => startEdit(item)}>수정</button><button type="button" onClick={() => deletePosition(item.id)}>삭제</button></div></td>
          </tr>;
        })}</tbody>
      </table></div> : <div className="portfolio-empty">아직 등록한 보유 종목이 없습니다. 위 입력란에서 첫 종목을 추가하세요.</div>}
      {buyStageEditor && (() => {
        const item = positions.find((position) => position.id === buyStageEditor.positionId);
        if (!item) return null;
        return <form className="portfolio-buy-stage-editor" onSubmit={completeBuyStage}>
          <div>
            <strong>{item.ticker} · {buyStageEditor.stage}차 매수 금액</strong>
            <p>{buyStageEditor.stage === 1 ? "실제로 1차 매수한 금액을 입력해 주세요." : "실제로 추가 매수한 금액만 입력해 주세요. 기존 1차 금액과 합산됩니다."}</p>
          </div>
          <NumericField label="매수 금액 (USD)" value={buyAmountInput} onChange={setBuyAmountInput} step="0.01" />
          {buyStageError && <p className="portfolio-error">{buyStageError}</p>}
          <div className="portfolio-row-actions">
            <button className="portfolio-primary" type="submit">{buyStageEditor.stage}차 매수 완료</button>
            <button className="portfolio-secondary" type="button" onClick={() => { setBuyStageEditor(null); setBuyStageError(""); }}>취소</button>
          </div>
        </form>;
      })()}

      {editingId && <form className="portfolio-edit-form" onSubmit={commitEdit}>
        <h3>{editDraft.ticker || "종목"} 수정</h3>
        <div className="portfolio-form-grid">
          <TickerSearchField value={editDraft.ticker} onChange={(value) => updateEditDraft("ticker", value)} />
          <label className="portfolio-field"><span>메모 (선택)</span><input type="text" value={editDraft.note} onChange={(event) => updateEditDraft("note", event.target.value)} /></label>
        </div>
        <div className="portfolio-row-actions"><button className="portfolio-primary" type="submit">수정 반영</button><button className="portfolio-secondary" type="button" onClick={() => setEditingId(null)}>취소</button></div>
      </form>}
    </section>

    {error && <p className="portfolio-error portfolio-bottom-message">{error}</p>}
    <div className="portfolio-bottom-actions"><span>{message || "종목 추가·수정·삭제 후 ‘변경사항 저장’을 눌러 주세요."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
    <div className="portfolio-note">매수 금액은 실제 체결된 금액을 1차·2차로 나누어 기록합니다. 기존 종목은 과거 수량 × 평균 매수가로 계산한 금액을 ‘기존 기록(차수 미분류)’로 보존합니다. 일반 분할매도는 2차 매수 완료 후 순서대로 열리며, 손절은 1차 매수 이후 언제든 별도로 처리할 수 있습니다. 단계 변경과 금액 입력은 화면에서 반영한 뒤 ‘변경사항 저장’을 눌러 Supabase에 저장하세요.</div>
  </section>;
}
