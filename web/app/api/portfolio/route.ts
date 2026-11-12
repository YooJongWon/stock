import { NextRequest, NextResponse } from "next/server";
import { isValidPortfolioSession, PORTFOLIO_COOKIE_NAME } from "@/lib/portfolio-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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

const CALCULATOR_KEYS = [
  "total", "stockCount", "cashRatio", "firstBuyRatio", "stopLossRatio",
  "firstTargetRatio", "finalTargetRatio", "firstEntryPrice", "secondEntryRisePct",
] as const;

function supabaseConfig() {
  const url = (process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "").replace(/\/$/, "");
  const key = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY || "";
  if (!url || !key) throw new Error("SUPABASE_URL 및 SUPABASE_SERVICE_ROLE_KEY 환경변수가 필요합니다.");
  return { url, key };
}

async function supabaseRequest(path: string, init: RequestInit = {}) {
  const { url, key } = supabaseConfig();
  const headers: Record<string, string> = {
    apikey: key,
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  // Current sb_secret_ keys are API keys, not JWTs: send them via apikey only.
  // Legacy service_role keys are JWTs and can also be sent as Authorization Bearer.
  if (!key.startsWith("sb_secret_")) headers.Authorization = `Bearer ${key}`;

  const response = await fetch(`${url}/rest/v1/${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    const message = await response.text();
    throw new Error(`Supabase 요청 실패 (${response.status}): ${message.slice(0, 500)}`);
  }
  return response;
}

async function readPortfolio() {
  const response = await supabaseRequest(
    "private_portfolio_data?select=id,cash_balance,calculator_settings,positions&id=eq.owner",
  );
  const rows = await response.json() as Array<{
    cash_balance: number | string;
    calculator_settings: Record<string, string> | null;
    positions: Position[] | null;
  }>;
  const row = rows[0];
  return {
    cashBalance: row ? Number(row.cash_balance) || 0 : 0,
    calculatorInputs: row?.calculator_settings || null,
    positions: normalizeStoredPositions(row?.positions),
  };
}

function normalizeStoredPositions(value: unknown): Position[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const row = item as Record<string, unknown>;
    const ticker = String(row.ticker || "").trim().toUpperCase();
    const id = String(row.id || "").trim();
    if (!id || !/^[A-Z0-9.-]{1,12}$/.test(ticker)) return [];

    const hasNewAmounts =
      typeof row.firstBuyAmount === "number" &&
      typeof row.secondBuyAmount === "number" &&
      typeof row.legacyInvestedAmount === "number";
    const oldInvested = Math.max(0, Number(row.shares) * Number(row.avgPrice) || 0);
    const firstBuyAmount = hasNewAmounts ? Math.max(0, Number(row.firstBuyAmount)) : 0;
    const secondBuyAmount = hasNewAmounts ? Math.max(0, Number(row.secondBuyAmount)) : 0;
    const legacyInvestedAmount = hasNewAmounts
      ? Math.max(0, Number(row.legacyInvestedAmount))
      : oldInvested;
    const hasPreviousBuyStage = typeof row.buyStage === "number" && Number.isInteger(row.buyStage) && row.buyStage >= 0 && row.buyStage <= 2;
    const hasPreviousSellStage = typeof row.sellStage === "number" && Number.isInteger(row.sellStage) && row.sellStage >= 0 && row.sellStage <= 3;
    // Old portfolio records had actual shares and average price but no stages.
    // Treat an existing holding as at least a completed first buy; do not guess whether a second buy happened.
    const buyStage = hasPreviousBuyStage ? row.buyStage as number : oldInvested > 0 ? 1 : 0;
    const sellStage = hasPreviousSellStage ? row.sellStage as number : 0;
    const exitStatus = row.exitStatus === "stopped" || row.exitStatus === "completed"
      ? row.exitStatus
      : sellStage === 3 ? "completed" : "active";

    return [{
      id,
      ticker,
      note: String(row.note || "").slice(0, 500),
      firstBuyAmount,
      secondBuyAmount,
      legacyInvestedAmount,
      buyStage,
      sellStage,
      exitStatus,
    }];
  });
}

function validPositions(value: unknown): Position[] | null {
  if (!Array.isArray(value) || value.length > 100) return null;
  const normalized: Position[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") return null;
    const row = item as Record<string, unknown>;
    const ticker = String(row.ticker || "").trim().toUpperCase();
    const id = String(row.id || "").trim();
    const firstBuyAmount = Number(row.firstBuyAmount);
    const secondBuyAmount = Number(row.secondBuyAmount);
    const legacyInvestedAmount = Number(row.legacyInvestedAmount ?? 0);
    const buyStage = Number(row.buyStage);
    const sellStage = Number(row.sellStage);
    const exitStatus = row.exitStatus;
    if (!id || id.length > 80 || !/^[A-Z0-9.-]{1,12}$/.test(ticker) ||
        !Number.isFinite(firstBuyAmount) || firstBuyAmount < 0 ||
        !Number.isFinite(secondBuyAmount) || secondBuyAmount < 0 ||
        !Number.isFinite(legacyInvestedAmount) || legacyInvestedAmount < 0 ||
        !Number.isInteger(buyStage) || buyStage < 0 || buyStage > 2 ||
        !Number.isInteger(sellStage) || sellStage < 0 || sellStage > 3 ||
        !["active", "stopped", "completed"].includes(String(exitStatus)) ||
        (buyStage < 1 && (firstBuyAmount > 0 || secondBuyAmount > 0)) ||
        (buyStage < 2 && (secondBuyAmount > 0 || sellStage > 0)) ||
        (exitStatus !== "active" && exitStatus !== "stopped" && exitStatus !== "completed")) return null;

    normalized.push({
      id,
      ticker,
      note: String(row.note || "").slice(0, 500),
      firstBuyAmount,
      secondBuyAmount,
      legacyInvestedAmount,
      buyStage,
      sellStage,
      exitStatus,
    });
  }
  return normalized;
}

function validCalculatorInputs(value: unknown) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = value as Record<string, unknown>;
  const normalized: Record<string, string> = {};
  for (const key of CALCULATOR_KEYS) {
    const entry = source[key];
    if (typeof entry !== "string" || entry.trim() === "" || !Number.isFinite(Number(entry))) return null;
    normalized[key] = entry;
  }
  return normalized;
}

export async function GET(request: NextRequest) {
  if (!isValidPortfolioSession(request.cookies.get(PORTFOLIO_COOKIE_NAME)?.value)) {
    return NextResponse.json({ error: "인증이 필요합니다." }, { status: 401 });
  }
  try {
    return NextResponse.json(await readPortfolio(), {
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "포트폴리오 조회에 실패했습니다." },
      { status: 503 },
    );
  }
}

export async function PATCH(request: NextRequest) {
  if (!isValidPortfolioSession(request.cookies.get(PORTFOLIO_COOKIE_NAME)?.value)) {
    return NextResponse.json({ error: "인증이 필요합니다." }, { status: 401 });
  }

  let body: Record<string, unknown>;
  try {
    body = await request.json() as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }

  const patch: Record<string, unknown> = { updated_at: new Date().toISOString() };
  if (Object.prototype.hasOwnProperty.call(body, "cashBalance")) {
    const cashBalance = Number(body.cashBalance);
    if (!Number.isFinite(cashBalance) || cashBalance < 0) {
      return NextResponse.json({ error: "예수금은 0 이상의 숫자여야 합니다." }, { status: 400 });
    }
    patch.cash_balance = cashBalance;
  }
  if (Object.prototype.hasOwnProperty.call(body, "calculatorInputs")) {
    const calculatorInputs = validCalculatorInputs(body.calculatorInputs);
    if (!calculatorInputs) {
      return NextResponse.json({ error: "계산기 설정값이 올바르지 않습니다." }, { status: 400 });
    }
    patch.calculator_settings = calculatorInputs;
  }
  if (Object.prototype.hasOwnProperty.call(body, "positions")) {
    const positions = validPositions(body.positions);
    if (!positions) {
      return NextResponse.json({ error: "보유 종목 정보가 올바르지 않습니다." }, { status: 400 });
    }
    patch.positions = positions;
  }
  if (Object.keys(patch).length === 1) {
    return NextResponse.json({ error: "저장할 항목이 없습니다." }, { status: 400 });
  }

  try {
    await supabaseRequest("private_portfolio_data?id=eq.owner", {
      method: "PATCH",
      headers: { Prefer: "return=minimal" },
      body: JSON.stringify(patch),
    });
    return NextResponse.json({ ok: true, updatedAt: patch.updated_at }, {
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "포트폴리오 저장에 실패했습니다." },
      { status: 503 },
    );
  }
}
