"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Position = {
  id: string;
  ticker: string;
  shares: number;
  avgPrice: number;
  note: string;
  buyStage: number | null;
  sellStage: number | null;
};
type PositionDraft = Omit<Position, "id">;
type TickerSearchResult = { symbol: string; name: string; exchange: string };
type PortfolioData = { cashBalance: number; positions: Position[] };

const EMPTY_DRAFT: PositionDraft = {
  ticker: "", shares: 0, avgPrice: 0, note: "",
  buyStage: 1, sellStage: 0,
};
const BUY_STAGE_OPTIONS = [
  { value: "", label: "미설정" },
  { value: "1", label: "1차 매수 완료" },
  { value: "2", label: "2차 매수 완료" },
];
const SELL_STAGE_OPTIONS = [
  { value: "", label: "미설정" },
  { value: "0", label: "매도 전" },
  { value: "1", label: "1차 매도 완료" },
  { value: "2", label: "2차 매도 완료" },
  { value: "3", label: "3차 매도 완료" },
];
const buyStageLabel = (stage: number | null) =>
  stage === null ? "미설정" : stage === 1 ? "1차 매수 완료" : "2차 매수 완료";
const sellStageLabel = (stage: number | null) =>
  stage === null ? "미설정" : stage === 0 ? "매도 전" : `${stage}차 매도 완료`;
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

function StageField({ label, value, onChange, options }: {
  label: string;
  value: number | null;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return <label className="portfolio-field">
    <span>{label}</span>
    <select value={value === null ? "" : String(value)} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
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
        shares: item.shares,
        avgPrice: item.avgPrice,
        note: item.note || "",
        buyStage: typeof item.buyStage === "number" && Number.isInteger(item.buyStage) && item.buyStage >= 1 && item.buyStage <= 2 ? item.buyStage : null,
        sellStage: typeof item.sellStage === "number" && Number.isInteger(item.sellStage) && item.sellStage >= 0 && item.sellStage <= 3 ? item.sellStage : null,
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
    const cost = positions.reduce((sum, item) => sum + item.shares * item.avgPrice, 0);
    const cash = Math.max(0, Number(cashBalance) || 0);
    return {
      cost,
      cash,
      positionCount: positions.length,
      firstBuyCount: positions.filter((item) => item.buyStage === 1).length,
      secondBuyCount: positions.filter((item) => item.buyStage === 2).length,
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
    const nextValue = key === "ticker" || key === "note"
      ? value
      : key === "buyStage" || key === "sellStage" ? (value === "" ? null : Number(value)) : Number(value);
    setDraft((old) => ({ ...old, [key]: nextValue }));
  };
  const updateEditDraft = (key: keyof PositionDraft, value: string) => {
    const nextValue = key === "ticker" || key === "note"
      ? value
      : key === "buyStage" || key === "sellStage" ? (value === "" ? null : Number(value)) : Number(value);
    setEditDraft((old) => ({ ...old, [key]: nextValue }));
  };

  const addPosition = (event: FormEvent) => {
    event.preventDefault();
    const ticker = draft.ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker) || draft.shares <= 0 || draft.avgPrice <= 0) {
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
      ticker: position.ticker, shares: position.shares,
      avgPrice: position.avgPrice, note: position.note,
      buyStage: position.buyStage, sellStage: position.sellStage,
    });
  };

  const commitEdit = (event: FormEvent) => {
    event.preventDefault();
    if (!editingId || editDraft.shares <= 0 || editDraft.avgPrice <= 0) {
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
      <div className="hero portfolio-hero"><div className="eyebrow">PRIVATE INVESTMENT TRACKER</div><h1>내 포트폴리오</h1><p>보유 수량과 평균 매수가, 분할매수·매도 진행 단계를 관리합니다.</p></div>
      <button className="portfolio-logout" type="button" onClick={logout}>로그아웃</button>
    </div>

    <div className="portfolio-summary portfolio-summary-simple">
      <article><span>총 매수 원금</span><strong>{usd(totals.cost)}</strong><small>보유 수량 × 평균 매수가 합계</small></article>
      <article><span>남은 예수금</span><strong>{usd(totals.cash)}</strong><small>직접 입력한 USD 잔액</small></article>
      <article><span>보유 종목</span><strong>{totals.positionCount}개</strong><small>1차 매수 {totals.firstBuyCount}개 · 2차 매수 {totals.secondBuyCount}개</small></article>
    </div>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">CASH BALANCE</div><h2>남은 예수금</h2><p>계좌의 남은 현금을 USD 기준으로 입력합니다.</p></div></div>
      <div className="portfolio-cash-row">
        <NumericField label="예수금 (USD)" value={cashBalance} onChange={(value) => { setCashBalance(value); setDirty(true); }} step="0.01" />
        <div className="portfolio-save-area"><span>{dirty ? "저장되지 않은 변경사항이 있습니다." : message || "모든 변경사항이 저장되었습니다."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
      </div>
    </section>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">HOLDINGS</div><h2>보유 종목</h2><p>티커를 검색해 선택하고 수량·평균 매수가와 거래 진행 단계를 기록합니다.</p></div><span className="portfolio-count">{positions.length} / 100</span></div>
      <form className="portfolio-position-form" onSubmit={addPosition}>
        <h3>보유 종목 추가</h3>
        <div className="portfolio-form-grid">
          <TickerSearchField value={draft.ticker} onChange={(value) => updateDraft("ticker", value)} />
          {field("보유 수량", "shares", draft.shares, updateDraft, "0.0001")}
          {field("평균 매수가 (USD)", "avgPrice", draft.avgPrice, updateDraft)}
          {field("메모 (선택)", "note", draft.note, updateDraft)}
          <StageField label="매수 단계" value={draft.buyStage} onChange={(value) => updateDraft("buyStage", value)} options={BUY_STAGE_OPTIONS} />
          <StageField label="매도 단계" value={draft.sellStage} onChange={(value) => updateDraft("sellStage", value)} options={SELL_STAGE_OPTIONS} />
        </div>
        <button className="portfolio-secondary" type="submit">+ 보유 종목 추가</button>
      </form>

      {positions.length ? <div className="portfolio-table-wrap"><table className="portfolio-table">
        <thead><tr><th>티커</th><th>매수 / 매도 단계</th><th>보유 수량</th><th>평균 매수가</th><th>매수 원금</th><th>관리</th></tr></thead>
        <tbody>{positions.map((item) => {
          const cost = item.shares * item.avgPrice;
          return <tr key={item.id}>
            <td><strong>{item.ticker}</strong>{item.note && <small>{item.note}</small>}</td>
            <td><div className="portfolio-stage-display">
              <span className="portfolio-stage-badge buy">매수 · {buyStageLabel(item.buyStage)}</span>
              <span className="portfolio-stage-badge sell">매도 · {sellStageLabel(item.sellStage)}</span>
            </div></td>
            <td>{numberText(item.shares)}</td><td>{usd(item.avgPrice)}</td>
            <td>{usd(cost)}</td>
            <td><div className="portfolio-row-actions"><button type="button" onClick={() => startEdit(item)}>수정</button><button type="button" onClick={() => deletePosition(item.id)}>삭제</button></div></td>
          </tr>;
        })}</tbody>
      </table></div> : <div className="portfolio-empty">아직 등록한 보유 종목이 없습니다. 위 입력란에서 첫 종목을 추가하세요.</div>}

      {editingId && <form className="portfolio-edit-form" onSubmit={commitEdit}>
        <h3>{editDraft.ticker || "종목"} 수정</h3>
        <div className="portfolio-form-grid">
          <TickerSearchField value={editDraft.ticker} onChange={(value) => updateEditDraft("ticker", value)} />
          {field("보유 수량", "shares", editDraft.shares, updateEditDraft, "0.0001")}
          {field("평균 매수가 (USD)", "avgPrice", editDraft.avgPrice, updateEditDraft)}
          {field("메모 (선택)", "note", editDraft.note, updateEditDraft)}
          <StageField label="매수 단계" value={editDraft.buyStage} onChange={(value) => updateEditDraft("buyStage", value)} options={BUY_STAGE_OPTIONS} />
          <StageField label="매도 단계" value={editDraft.sellStage} onChange={(value) => updateEditDraft("sellStage", value)} options={SELL_STAGE_OPTIONS} />
        </div>
        <div className="portfolio-row-actions"><button className="portfolio-primary" type="submit">수정 반영</button><button className="portfolio-secondary" type="button" onClick={() => setEditingId(null)}>취소</button></div>
      </form>}
    </section>

    {error && <p className="portfolio-error portfolio-bottom-message">{error}</p>}
    <div className="portfolio-bottom-actions"><span>{message || "종목 추가·수정·삭제 후 ‘변경사항 저장’을 눌러 주세요."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
    <div className="portfolio-note">티커 검색은 Yahoo Finance 검색 결과를 이용합니다. 검색 결과에서 종목을 선택하거나 티커를 직접 입력할 수 있습니다. 회사명과 실시간 현재가는 저장하지 않으며, 매수 원금은 보유 수량 × 평균 매수가로 계산합니다. 기존 종목의 단계는 거래 이력을 추정하지 않고 ‘미설정’으로 표시하며, 수정 후 ‘변경사항 저장’을 눌러 주세요.</div>
  </section>;
}
