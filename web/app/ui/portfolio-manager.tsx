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
type PositionDraft = { ticker: string; note: string; firstBuyAmount: string };
type PositionEditDraft = { ticker: string; note: string; totalInvestedAmount: string };
type PortfolioGroup = "all" | "waiting" | "buy1" | "buy2" | "sell1" | "sell2" | "sell3" | "stopped";

const PORTFOLIO_GROUPS: { id: PortfolioGroup; label: string }[] = [
  { id: "all", label: "전체" },
  { id: "waiting", label: "매수 대기" },
  { id: "buy1", label: "1차 매수" },
  { id: "buy2", label: "2차 매수" },
  { id: "sell1", label: "1차 매도" },
  { id: "sell2", label: "2차 매도" },
  { id: "sell3", label: "3차 매도 완료" },
  { id: "stopped", label: "손절 종료" },
];
type BuyStageEditor = { positionId: string; stage: 1 | 2 };
type CalculatorInputs = {
  total: string; stockCount: string; cashRatio: string; firstBuyRatio: string;
  stopLossRatio: string; firstTargetRatio: string; finalTargetRatio: string;
  secondEntryRisePct: string;
};
type CalculatorPlan = {
  total: number; stockCount: number; perStockAmount: number; firstBuyAmount: number;
  secondBuyAmount: number; stopLossRatio: number; secondEntryRisePct: number;
  sellTargets: { label: string; returnPct: number; sellPct: number }[];
};
type TickerSearchResult = { symbol: string; name: string; exchange: string };
type PortfolioData = { cashBalance: number; positions: Position[]; calculatorInputs?: Partial<CalculatorInputs> | null };

const DEFAULT_CALCULATOR_INPUTS: CalculatorInputs = {
  total: "14000", stockCount: "5", cashRatio: "5", firstBuyRatio: "60",
  stopLossRatio: "-5", firstTargetRatio: "8", finalTargetRatio: "10",
  secondEntryRisePct: "4",
};
const EMPTY_DRAFT: PositionDraft = { ticker: "", note: "", firstBuyAmount: "" };
const totalInvested = (position: Position) =>
  position.firstBuyAmount + position.secondBuyAmount + position.legacyInvestedAmount;

function getPositionProgress(position: Position): { label: string; tone: "buy" | "sell" | "stopped" | "completed" | "pending" } {
  if (position.exitStatus === "stopped") return { label: "손절 종료", tone: "stopped" };
  if (position.exitStatus === "completed" || position.sellStage >= 3) return { label: "3차 매도 완료", tone: "completed" };
  if (position.sellStage === 2) return { label: "2차 매도 완료", tone: "sell" };
  if (position.sellStage === 1) return { label: "1차 매도 완료", tone: "sell" };
  if (position.buyStage >= 2) return { label: "2차 매수 완료", tone: "buy" };
  if (position.buyStage === 1) return { label: "1차 매수 완료", tone: "buy" };
  return { label: "1차 매수 대기", tone: "pending" };
}

function buildCalculatorPlan(input: Partial<CalculatorInputs> | null | undefined): CalculatorPlan {
  const read = (key: keyof CalculatorInputs, fallback: string) => {
    const raw = input?.[key];
    const value = typeof raw === "string" ? Number(raw) : Number.NaN;
    return Number.isFinite(value) ? value : Number(fallback);
  };
  const total = Math.max(0, read("total", DEFAULT_CALCULATOR_INPUTS.total));
  const stockCount = Math.max(1, Math.min(100, Math.floor(read("stockCount", DEFAULT_CALCULATOR_INPUTS.stockCount))));
  const cashRatio = Math.max(0, Math.min(100, read("cashRatio", DEFAULT_CALCULATOR_INPUTS.cashRatio))) / 100;
  const firstRatio = Math.max(0, Math.min(100, read("firstBuyRatio", DEFAULT_CALCULATOR_INPUTS.firstBuyRatio))) / 100;
  const perStockAmount = total * (1 - cashRatio) / stockCount;
  return {
    total, stockCount, perStockAmount,
    firstBuyAmount: perStockAmount * firstRatio,
    secondBuyAmount: perStockAmount * (1 - firstRatio),
    stopLossRatio: Math.min(0, Math.max(-100, read("stopLossRatio", DEFAULT_CALCULATOR_INPUTS.stopLossRatio))),
    secondEntryRisePct: Math.min(5, Math.max(3, read("secondEntryRisePct", DEFAULT_CALCULATOR_INPUTS.secondEntryRisePct))),
    sellTargets: [
      { label: "1차 매도", returnPct: Math.max(0, read("firstTargetRatio", DEFAULT_CALCULATOR_INPUTS.firstTargetRatio)), sellPct: 40 },
      { label: "2차 매도", returnPct: 9, sellPct: 30 },
      { label: "3차 매도", returnPct: Math.max(0, read("finalTargetRatio", DEFAULT_CALCULATOR_INPUTS.finalTargetRatio)), sellPct: 30 },
    ],
  };
}

const usd = (value: number) => new Intl.NumberFormat("en-US", {
  style: "currency", currency: "USD", maximumFractionDigits: 2,
}).format(Number.isFinite(value) ? value : 0);

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
  const [selectedGroup, setSelectedGroup] = useState<PortfolioGroup>("all");
  const [calculatorInputs, setCalculatorInputs] = useState<CalculatorInputs>(DEFAULT_CALCULATOR_INPUTS);
  const [draft, setDraft] = useState<PositionDraft>(EMPTY_DRAFT);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<PositionEditDraft>({ ticker: "", note: "", totalInvestedAmount: "0" });
  const [editError, setEditError] = useState("");
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
      setCalculatorInputs({ ...DEFAULT_CALCULATOR_INPUTS, ...(data.calculatorInputs || {}) });
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

  const plan = useMemo(() => buildCalculatorPlan(calculatorInputs), [calculatorInputs]);

  const groupCounts = useMemo(() => {
    const counts: Record<PortfolioGroup, number> = {
      all: positions.length, waiting: 0, buy1: 0, buy2: 0,
      sell1: 0, sell2: 0, sell3: 0, stopped: 0,
    };
    positions.forEach((item) => {
      if (item.exitStatus === "stopped") { counts.stopped += 1; return; }
      if (item.exitStatus === "completed" || item.sellStage >= 3) { counts.sell3 += 1; return; }
      if (item.sellStage === 2) { counts.sell2 += 1; return; }
      if (item.sellStage === 1) { counts.sell1 += 1; return; }
      if (item.buyStage >= 2) { counts.buy2 += 1; return; }
      if (item.buyStage === 1) { counts.buy1 += 1; return; }
      counts.waiting += 1;
    });
    return counts;
  }, [positions]);

  const filteredPositions = useMemo(() => {
    if (selectedGroup === "all") return positions;
    return positions.filter((item) => {
      if (selectedGroup === "stopped") return item.exitStatus === "stopped";
      if (selectedGroup === "sell3") return item.exitStatus === "completed" || item.sellStage >= 3;
      if (item.exitStatus !== "active") return false;
      if (selectedGroup === "sell2") return item.sellStage === 2;
      if (selectedGroup === "sell1") return item.sellStage === 1;
      if (selectedGroup === "buy2") return item.buyStage >= 2 && item.sellStage === 0;
      if (selectedGroup === "buy1") return item.buyStage === 1 && item.sellStage === 0;
      if (selectedGroup === "waiting") return item.buyStage === 0;
      return false;
    });
  }, [positions, selectedGroup]);

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
  const updateEditDraft = (key: keyof PositionEditDraft, value: string) => {
    setEditDraft((old) => ({ ...old, [key]: value }));
  };

  const addPosition = (event: FormEvent) => {
    event.preventDefault();
    const ticker = draft.ticker.trim().toUpperCase();
    const firstBuyAmount = Number(draft.firstBuyAmount);
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) {
      setError("티커를 검색 결과에서 선택하거나 올바른 티커를 입력해 주세요.");
      return;
    }
    if (!Number.isFinite(firstBuyAmount) || firstBuyAmount <= 0) {
      setError("실제 1차 매수 금액을 입력해 주세요.");
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
      firstBuyAmount,
      secondBuyAmount: 0,
      legacyInvestedAmount: 0,
      buyStage: 1,
      sellStage: 0,
      exitStatus: "active",
    };
    setPositions((old) => [...old, next]);
    setDraft(EMPTY_DRAFT);
    setDirty(true);
    setError("");
    setMessage("종목과 1차 매수금액을 등록했습니다. 계산기 기준 2차 매수금액이 자동으로 계산됩니다.");
  };

  const startEdit = (position: Position) => {
    setEditingId(position.id);
    setEditError("");
    setEditDraft({
      ticker: position.ticker,
      note: position.note,
      totalInvestedAmount: totalInvested(position).toFixed(2),
    });
  };

  const closeEdit = () => {
    setEditingId(null);
    setEditError("");
  };

  const commitEdit = (event: FormEvent) => {
    event.preventDefault();
    if (!editingId) return;
    const ticker = editDraft.ticker.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(ticker)) {
      setEditError("티커 형식이 올바르지 않습니다.");
      return;
    }
    if (positions.some((item) => item.id !== editingId && item.ticker === ticker && item.exitStatus === "active")) {
      setEditError("이미 보유 목록에 있는 종목입니다.");
      return;
    }
    const targetTotal = Number(editDraft.totalInvestedAmount);
    if (!Number.isFinite(targetTotal) || targetTotal < 0) {
      setEditError("총 매수금액은 0 이상의 USD 금액으로 입력해 주세요.");
      return;
    }
    const current = positions.find((item) => item.id === editingId);
    if (!current) return;
    if (current.buyStage >= 1 && targetTotal <= 0) {
      setEditError("이미 매수한 종목의 총 매수금액은 0보다 커야 합니다.");
      return;
    }
    const separatedTrancheAmount = current.firstBuyAmount + current.secondBuyAmount;
    if (current.legacyInvestedAmount > 0 && targetTotal < separatedTrancheAmount) {
      setEditError(`차수가 구분된 매수금액 ${usd(separatedTrancheAmount)}보다 작게 설정할 수 없습니다.`);
      return;
    }
    let adjusted: Position;
    if (current.legacyInvestedAmount > 0) {
      adjusted = {
        ...current,
        ticker,
        note: editDraft.note.trim(),
        legacyInvestedAmount: Math.max(0, targetTotal - separatedTrancheAmount),
      };
    } else if (current.buyStage >= 2) {
      if (targetTotal <= current.firstBuyAmount) {
        setEditError(`2차 매수까지 완료된 종목은 1차 매수금액 ${usd(current.firstBuyAmount)}보다 큰 총액이어야 합니다.`);
        return;
      }
      adjusted = {
        ...current,
        ticker,
        note: editDraft.note.trim(),
        secondBuyAmount: targetTotal - current.firstBuyAmount,
      };
    } else if (current.buyStage === 1) {
      adjusted = {
        ...current,
        ticker,
        note: editDraft.note.trim(),
        firstBuyAmount: targetTotal,
      };
    } else {
      adjusted = {
        ...current,
        ticker,
        note: editDraft.note.trim(),
        firstBuyAmount: targetTotal,
        buyStage: targetTotal > 0 ? 1 : 0,
      };
    }
    setPositions((old) => old.map((item) => item.id === editingId ? adjusted : item));
    setEditingId(null);
    setDirty(true);
    setEditError("");
    setMessage("총 매수금액을 수정했습니다. 차수별 금액에도 반영됐으니 변경사항 저장을 눌러 주세요.");
  };

  const openBuyStageEditor = (position: Position, stage: 1 | 2) => {
    const recommended = stage === 1 ? plan.firstBuyAmount : Math.max(0, plan.perStockAmount - totalInvested(position));
    setBuyStageEditor({ positionId: position.id, stage });
    setBuyAmountInput(recommended > 0 ? recommended.toFixed(2) : "");
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
    const current = positions.find((item) => item.id === positionId);
    if (!current || current.exitStatus !== "active" ||
        (stage === 1 && current.buyStage !== 0) ||
        (stage === 2 && current.buyStage !== 1)) {
      setBuyStageError("현재 단계에서는 이 매수를 진행할 수 없습니다.");
      return;
    }
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
    const target = plan.sellTargets[nextStage - 1];
    if (!window.confirm(`${position.ticker} ${target.label} (+${target.returnPct}% · ${target.sellPct}%) 체결을 기록할까요?`)) return;
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
    if (!window.confirm(`${position.ticker} 손절 기준 ${Math.abs(plan.stopLossRatio)}% 도달 후 실제 매도 체결을 기록할까요?`)) return;
    setPositions((old) => old.map((item) => item.id === position.id ? { ...item, exitStatus: "stopped" } : item));
    setDirty(true);
    setMessage(`${position.ticker} 손절 종료로 표시했습니다. 저장 버튼을 눌러 주세요.`);
  };

  const deletePosition = (id: string) => {
    if (!window.confirm("이 보유 종목을 삭제할까요?")) return;
    setPositions((old) => old.filter((item) => item.id !== id));
    setDirty(true);
    if (editingId === id) closeEdit();
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
      <div className="hero portfolio-hero"><div className="eyebrow">PRIVATE INVESTMENT TRACKER</div><h1>내 포트폴리오</h1><p>스윙 투자 계산기의 종목당 배정금액을 기준으로 분할매수·매도 진행 상황을 관리합니다.</p></div>
      <button className="portfolio-logout" type="button" onClick={logout}>로그아웃</button>
    </div>

    <div className="portfolio-summary portfolio-summary-simple">
      <article><span>총 매수 원금</span><strong>{usd(totals.cost)}</strong><small>실제 1·2차 매수금액 합계</small></article>
      <article><span>남은 예수금</span><strong>{usd(totals.cash)}</strong><small>직접 입력한 USD 잔액</small></article>
      <article><span>현재 운용 종목</span><strong>{totals.positionCount}개</strong><small>1차 {totals.firstBuyCount}개 · 2차 {totals.secondBuyCount}개 완료</small></article>
    </div>
    <section className="portfolio-plan-banner">
      <div className="portfolio-plan-banner-heading">
        <div><span>SWING CALCULATOR 연동</span><strong>종목당 목표 투자금 {usd(plan.perStockAmount)}</strong></div>
        <small>총 투자금 {usd(plan.total)} ÷ {plan.stockCount}종목 · 현금 비중 반영</small>
      </div>
      <div className="portfolio-plan-amounts">
        <div><small>1차 매수 권장</small><strong>{usd(plan.firstBuyAmount)}</strong></div>
        <div><small>2차 매수 기본 배정</small><strong>{usd(plan.secondBuyAmount)}</strong></div>
        <div><small>2차 매수 진입 기준</small><strong>+3~5% · 설정 +{plan.secondEntryRisePct.toFixed(1)}%</strong></div>
        <div><small>손절 / 익절 목표</small><strong>{plan.stopLossRatio}% · +{plan.sellTargets.map((item) => item.returnPct).join("% / +")}%</strong></div>
      </div>
      <p>1차·2차 기본 배정은 계산기 기준입니다. 종목별 2차 추가 추천금액은 종목당 목표 투자금에서 해당 종목의 실제 누적 매수금액을 뺀 차액으로 자동 조정됩니다.</p>
    </section>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">CASH BALANCE</div><h2>남은 예수금</h2><p>계좌의 남은 현금을 USD 기준으로 입력합니다.</p></div></div>
      <div className="portfolio-cash-row">
        <NumericField label="예수금 (USD)" value={cashBalance} onChange={(value) => { setCashBalance(value); setDirty(true); }} step="0.01" />
        <div className="portfolio-save-area"><span>{dirty ? "저장되지 않은 변경사항이 있습니다." : message || "모든 변경사항이 저장되었습니다."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
      </div>
    </section>

    <section className="portfolio-panel">
      <div className="portfolio-panel-heading"><div><div className="eyebrow">HOLDINGS</div><h2>보유 종목</h2><p>등록 시 실제 1차 매수금액을 입력하면 1차 매수 완료 상태로 시작합니다.</p></div><span className="portfolio-count">{positions.length} / 100</span></div>
      <form className="portfolio-position-form" onSubmit={addPosition}>
        <h3>보유 종목 추가</h3>
        <div className="portfolio-form-grid">
          <TickerSearchField value={draft.ticker} onChange={(value) => updateDraft("ticker", value)} />
          <NumericField label="실제 1차 매수 금액 (USD)" value={draft.firstBuyAmount} onChange={(value) => updateDraft("firstBuyAmount", value)} step="0.01" />
          <label className="portfolio-field portfolio-span-all"><span>메모 (선택)</span><input type="text" value={draft.note} onChange={(event) => updateDraft("note", event.target.value)} /></label>
        </div>
        <div className="portfolio-form-hint">계산기 기준 1차 권장금액 <strong>{usd(plan.firstBuyAmount)}</strong> · 종목당 총 배정금액 <strong>{usd(plan.perStockAmount)}</strong>. 실제 체결 금액으로 수정해서 등록하세요.</div>
        <button className="portfolio-primary" type="submit">1차 매수 완료로 등록</button>
      </form>

      <div className="portfolio-group-filter" aria-label="매매 진행 단계별 종목 필터">
        <div className="portfolio-group-filter-heading">
          <div><strong>진행 단계별 보기</strong><small>단계를 선택하면 해당 종목만 모아볼 수 있습니다.</small></div>
          <span>{filteredPositions.length} / {positions.length}개 표시</span>
        </div>
        <div className="portfolio-group-filter-tabs" role="group" aria-label="보유 종목 진행 단계">
          {PORTFOLIO_GROUPS.map((group) => (
            <button
              key={group.id}
              type="button"
              className={selectedGroup === group.id ? "active" : ""}
              aria-pressed={selectedGroup === group.id}
              onClick={() => setSelectedGroup(group.id)}
            >
              <span>{group.label}</span><b>{groupCounts[group.id]}</b>
            </button>
          ))}
        </div>
      </div>

      {filteredPositions.length ? <div className="portfolio-position-list">
        {filteredPositions.map((item) => {}
          const invested = totalInvested(item);
          const isActive = item.exitStatus === "active";
          const remainingBudget = Math.max(0, plan.perStockAmount - invested);
          const overBudget = Math.max(0, invested - plan.perStockAmount);
          const exitBasisAmount = item.buyStage >= 2 ? invested : plan.perStockAmount;
          const exitBasisLabel = item.buyStage >= 2 ? "실제 누적 매수금 기준" : "종목당 목표금액 기준";
          const progress = getPositionProgress(item);
          return <article className="portfolio-position-card" key={item.id}>
            <header className="portfolio-position-card-header">
              <div className="portfolio-position-identity">
                <span className={`portfolio-progress-badge ${progress.tone}`}>{progress.label}</span>
                <strong>{item.ticker}</strong>
                {item.note && <small>{item.note}</small>}
              </div>
              <div className="portfolio-position-invested"><span>누적 매수금액</span><strong>{usd(invested)}</strong><small>1차 {usd(item.firstBuyAmount)} · 2차 {usd(item.secondBuyAmount)}{item.legacyInvestedAmount > 0 ? ` · 기존 ${usd(item.legacyInvestedAmount)}` : ""}</small></div>
            </header>
            <div className="portfolio-position-columns">
              <section className="portfolio-position-section buy-section">
                <div className="portfolio-position-section-title"><span>BUY PLAN</span><strong>분할매수 진행</strong></div>
                <div className={`portfolio-buy-step ${item.buyStage >= 1 ? "done" : "current"}`}>
                  <div><strong>1차 매수</strong><small>권장 {usd(plan.firstBuyAmount)}</small></div>
                  {item.buyStage >= 1 ? <span className="portfolio-step-done">완료 · {usd(item.firstBuyAmount || item.legacyInvestedAmount)}</span>
                    : isActive ? <button type="button" className="portfolio-stage-next buy" onClick={() => openBuyStageEditor(item, 1)}>1차 매수 금액 입력</button>
                    : <span className="portfolio-stage-locked">진행 불가</span>}
                </div>
                <div className={`portfolio-buy-step ${item.buyStage >= 2 ? "done" : item.buyStage === 1 ? "current" : "locked"}`}>
                  <div><strong>2차 매수</strong><small>실제 1차 금액 반영 후 추가 권장 {usd(item.buyStage >= 1 ? remainingBudget : plan.secondBuyAmount)}</small></div>
                  {item.buyStage >= 2 ? <span className="portfolio-step-done">완료 · {usd(item.secondBuyAmount)}</span>
                    : item.buyStage === 1 && isActive && remainingBudget > 0
                      ? <button type="button" className="portfolio-stage-next buy" onClick={() => openBuyStageEditor(item, 2)}>2차 매수 · 추가 {usd(remainingBudget)}</button>
                      : item.buyStage === 1 && isActive
                        ? <span className="portfolio-stage-locked">목표 투자금 도달 · 추가 매수 보류</span>
                        : <span className="portfolio-stage-locked">1차 매수 완료 후 활성화</span>}
                  <div className="portfolio-buy-trigger-note">
                    **진입 기준:** 1차 매수가 대비 +3~5% 상승 구간 (현재 계산기 설정 예시 +{plan.secondEntryRisePct.toFixed(1)}%)
                    <small>상승 추세 유지 · 20일선 또는 돌파 저항선 지지 · 저점 상승 확인 후 진입</small>
                  </div>
                  {item.buyStage === 1 && overBudget > 0 && <div className="portfolio-over-budget-note">종목당 목표 투자금을 {usd(overBudget)} 초과했습니다. 추가 매수는 권장하지 않습니다.</div>}
                </div>
                <div className="portfolio-budget-progress">
                  <div><span>종목당 목표금액</span><strong>{usd(plan.perStockAmount)}</strong></div>
                  <div className="portfolio-budget-track"><span style={{ width: `${plan.perStockAmount > 0 ? Math.min(100, invested / plan.perStockAmount * 100) : 0}%` }} /></div>
                  <small>{plan.perStockAmount > 0 ? Math.min(100, invested / plan.perStockAmount * 100).toFixed(0) : "0"}% 집행 · 남은 배정금 {usd(remainingBudget)}</small>
                </div>
              </section>
              <section className="portfolio-position-section sell-section">
                <div className="portfolio-position-section-title"><span>SELL PLAN</span><strong>분할매도 목표</strong></div>
                {item.exitStatus !== "active" && <div className={`portfolio-exit-banner ${item.exitStatus}`}>{item.exitStatus === "stopped" ? "손절 처리된 종목" : "3차 분할매도까지 완료"}</div>}
                {plan.sellTargets.map((target, index) => {
                  const stage = index + 1;
                  const expectedSaleAmount = exitBasisAmount * (target.sellPct / 100) * (1 + target.returnPct / 100);
                  const expectedProfit = exitBasisAmount * (target.sellPct / 100) * (target.returnPct / 100);
                  const completed = item.sellStage >= stage;
                  const available = isActive && item.buyStage >= 2 && item.sellStage === stage - 1;
                  const lockedText = item.buyStage < 2 ? "2차 매수 완료 후 활성화" : `${stage - 1}차 매도 완료 후 활성화`;
                  return <div className={`portfolio-sell-target ${completed ? "completed" : available ? "available" : "pending"}`} key={target.label}>
                    <div className="portfolio-sell-target-main">
                      <strong>{target.label}</strong><span>+{target.returnPct}% 수익 · {target.sellPct}% 매도</span>
                      <small>예상 회수액 {usd(expectedSaleAmount)} · 예상 차익 +{usd(expectedProfit)}</small>
                      <small>{exitBasisLabel} · +{target.returnPct}% 도달 시 실행</small>
                    </div>
                    <div className="portfolio-sell-target-action">
                      {completed ? <span className="portfolio-step-done">완료</span>
                        : available ? <button type="button" className="portfolio-stage-next sell" onClick={() => completeSellStage(item)}>매도 완료 기록</button>
                        : <span className="portfolio-stage-locked">{lockedText}</span>}
                    </div>
                  </div>;
                })}
                <div className="portfolio-stop-target">
                  <div><strong>전량 손절</strong><span>{plan.stopLossRatio}% 기준</span><small>누적 매수 원금 대비 손실 기준</small></div>
                  {isActive && item.buyStage >= 1 ? <button type="button" className="portfolio-stop-button" onClick={() => stopLossPosition(item)}>손절 완료 기록</button>
                    : <span className="portfolio-stage-locked">1차 매수 후 활성화</span>}
                </div>
              </section>
            </div>
            <footer className="portfolio-position-card-footer">
              <span>{item.buyStage >= 2 ? "2차 매수 완료 · 익절 단계 진행 가능" : item.buyStage === 1 ? "2차 매수 대기 · 계산기 배정액 확인" : "1차 매수 전"}</span>
              <div className="portfolio-row-actions">
                <button type="button" onClick={() => startEdit(item)}>종목 수정</button>
                <button type="button" onClick={() => deletePosition(item.id)}>삭제</button>
              </div>
            </footer>
          </article>;
        })}
      </div> : <div className="portfolio-empty">
        {positions.length === 0
          ? "아직 등록한 종목이 없습니다. 종목을 검색하고 실제 1차 매수 금액을 입력해 등록하세요."
          : `‘${PORTFOLIO_GROUPS.find((group) => group.id === selectedGroup)?.label}’ 단계에 해당하는 종목이 없습니다.`}
        {positions.length > 0 && selectedGroup !== "all" && <button type="button" className="portfolio-empty-reset" onClick={() => setSelectedGroup("all")}>전체 종목 보기</button>}
      </div>}
      {buyStageEditor && (() => {
        const item = positions.find((position) => position.id === buyStageEditor.positionId);
        if (!item) return null;
        const recommended = buyStageEditor.stage === 1 ? plan.firstBuyAmount : Math.max(0, plan.perStockAmount - totalInvested(item));
        return <div className="portfolio-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setBuyStageEditor(null); }}>
          <form className="portfolio-buy-stage-editor" role="dialog" aria-modal="true" aria-labelledby="buy-stage-title" onSubmit={completeBuyStage}>
            <div className="portfolio-modal-heading">
              <div><span>BUY EXECUTION</span><h3 id="buy-stage-title">{item.ticker} · {buyStageEditor.stage}차 매수</h3><p>계산기 권장 금액과 실제 체결 금액을 비교한 뒤 기록하세요.</p></div>
              <button type="button" className="portfolio-modal-close" onClick={() => setBuyStageEditor(null)} aria-label="닫기">×</button>
            </div>
            <div className="portfolio-buy-recommendation">
              <div><small>종목당 목표 투자금</small><strong>{usd(plan.perStockAmount)}</strong></div>
              <div><small>{buyStageEditor.stage}차 권장 매수금</small><strong>{usd(recommended)}</strong></div>
              {buyStageEditor.stage === 2 && <div><small>현재까지 매수한 금액</small><strong>{usd(totalInvested(item))}</strong></div>}
            </div>
            {buyStageEditor.stage === 2 && <div className="portfolio-buy-trigger-modal">
              <strong>2차 진입 기준 · +3~5% 상승 구간</strong>
              <span>현재 계산기 설정 예시 +{plan.secondEntryRisePct.toFixed(1)}%</span>
              <small>상승 추세 유지, 20일선 또는 돌파 저항선 지지, 저점 상승을 확인하세요. 상승률 도달만으로 매수하지 않습니다.</small>
            </div>}
            <NumericField label="실제 매수 금액 (USD)" value={buyAmountInput} onChange={setBuyAmountInput} step="0.01" />
            <p className="portfolio-modal-hint">계산기 권장 추가금액을 기본값으로 채웠습니다. 실제 매수할 금액에 맞게 수정한 뒤 완료 처리하세요.</p>
            {Number(buyAmountInput) > recommended && recommended > 0 && <p className="portfolio-modal-warning">계산기 기준 권장 추가금액보다 큽니다. 종목당 배정금액을 초과하는지 확인하세요.</p>}
            {buyStageEditor.stage === 2 && recommended <= 0 && <p className="portfolio-modal-warning">종목당 목표 투자금에 이미 도달했습니다. 추가 매수를 권장하지 않습니다.</p>}
            {buyStageError && <p className="portfolio-error">{buyStageError}</p>}
            <div className="portfolio-row-actions">
              <button className="portfolio-primary" type="submit">{buyStageEditor.stage}차 매수 완료</button>
              <button className="portfolio-secondary" type="button" onClick={() => setBuyStageEditor(null)}>취소</button>
            </div>
          </form>
        </div>;
      })()}
      
      {editingId && (() => {
        const item = positions.find((position) => position.id === editingId);
        if (!item) return null;
        return <div
          className="portfolio-modal-backdrop portfolio-edit-backdrop"
          role="presentation"
          onMouseDown={(event) => { if (event.target === event.currentTarget) closeEdit(); }}
        >
          <form
            className="portfolio-edit-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="portfolio-edit-title"
            onSubmit={commitEdit}
          >
            <div className="portfolio-modal-heading">
              <div>
                <span>EDIT HOLDING</span>
                <h3 id="portfolio-edit-title">{item.ticker} 종목 수정</h3>
                <p>티커, 누적 매수금액, 메모를 수정할 수 있습니다.</p>
              </div>
              <button type="button" className="portfolio-modal-close" onClick={closeEdit} aria-label="수정 창 닫기">×</button>
            </div>
            <div className="portfolio-edit-modal-fields">
              <TickerSearchField value={editDraft.ticker} onChange={(value) => updateEditDraft("ticker", value)} />
              <NumericField
                label="총 매수금액 (USD)"
                value={editDraft.totalInvestedAmount}
                onChange={(value) => setEditDraft((old) => ({ ...old, totalInvestedAmount: value }))}
                step="0.01"
              />
              <label className="portfolio-field portfolio-span-all">
                <span>메모 (선택)</span>
                <input type="text" value={editDraft.note} onChange={(event) => updateEditDraft("note", event.target.value)} />
              </label>
            </div>
            <p className="portfolio-form-hint">총 매수금액을 바꾸면 차수별 매수금액도 자동 조정됩니다. 2차 매수 완료 종목은 1차 금액을 유지하고 2차 금액을 조정합니다.</p>
            {editError && <p className="portfolio-error portfolio-edit-error">{editError}</p>}
            <div className="portfolio-row-actions portfolio-edit-modal-actions">
              <button className="portfolio-primary" type="submit">수정 반영</button>
              <button className="portfolio-secondary" type="button" onClick={closeEdit}>취소</button>
            </div>
          </form>
        </div>;
      })()}
    </section>

    {error && <p className="portfolio-error portfolio-bottom-message">{error}</p>}
    <div className="portfolio-bottom-actions"><span>{message || "종목 추가·수정·삭제 후 ‘변경사항 저장’을 눌러 주세요."}</span><button className="portfolio-primary" type="button" onClick={save} disabled={!dirty || saving}>{saving ? "저장 중…" : "변경사항 저장"}</button></div>
    <div className="portfolio-note">매수 권장금액과 매도 목표 수익률은 스윙 투자 계산기의 저장된 총 투자금·종목 수·현금 비중·분할매수 비중·익절/손절 기준을 자동으로 사용합니다. 포트폴리오는 실제 투입한 매수 금액과 수익률 기준만 관리하며 수량·평균 매수가·실시간 시세는 저장하지 않습니다. 기존 원금은 보존하되 과거 매수 차수는 임의로 추정하지 않습니다. 예상 회수액과 차익은 실제 누적 매수금액을 기준으로 각 매도 비중을 배분한 추정치이며 수수료·세금·체결 오차를 제외합니다. 매수·매도 버튼은 실제 체결을 기록하는 용도이며 자동 주문은 실행하지 않습니다. 변경사항 저장을 눌러 Supabase에 반영하세요.</div>
  </section>;
}
