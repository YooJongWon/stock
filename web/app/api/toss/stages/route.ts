import { NextRequest, NextResponse } from "next/server";
import { isValidPortfolioSession, PORTFOLIO_COOKIE_NAME } from "@/lib/portfolio-auth";
import { supabaseRequest } from "@/lib/portfolio-supabase";

const table = "private_toss_buy_stages";

function reply(body: object, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "private, no-store" } });
}

function authorized(request: NextRequest) {
  return isValidPortfolioSession(request.cookies.get(PORTFOLIO_COOKIE_NAME)?.value);
}

export async function GET(request: NextRequest) {
  if (!authorized(request)) return reply({ error: "인증이 필요합니다." }, 401);
  try {
    const response = await supabaseRequest(`${table}?select=holding_key,stage`);
    return reply({ stages: await response.json() });
  } catch {
    return reply({ error: "저장된 매수 상태를 불러오지 못했습니다." }, 503);
  }
}

export async function PUT(request: NextRequest) {
  if (!authorized(request)) return reply({ error: "인증이 필요합니다." }, 401);
  const body = await request.json().catch(() => null);
  const importing = body?.importLegacy === true;
  const entries: unknown = body?.stages;
  if (!Array.isArray(entries) || entries.length < 1 || entries.length > (importing ? 500 : 1) ||
      !entries.every((row) => typeof row?.holding_key === "string" &&
        row.holding_key.length > 0 && row.holding_key.length <= 120 && (row.stage === 1 || row.stage === 2)) ||
      new Set(entries.map((row) => row.holding_key)).size !== entries.length) {
    return reply({ error: "매수 상태 형식이 올바르지 않습니다." }, 400);
  }
  try {
    await supabaseRequest(`${table}?on_conflict=holding_key`, {
      method: "POST",
      headers: { Prefer: `resolution=${importing ? "ignore" : "merge"}-duplicates,return=minimal` },
      body: JSON.stringify(entries.map(({ holding_key, stage }) => ({ holding_key, stage }))),
    });
    return reply({ ok: true });
  } catch {
    return reply({ error: "매수 상태를 저장하지 못했습니다. 다시 시도해 주세요." }, 503);
  }
}
