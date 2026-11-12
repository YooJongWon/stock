import { NextRequest, NextResponse } from "next/server";
import {
  createPortfolioSession,
  isValidPortfolioPassword,
  portfolioAuthConfigured,
  PORTFOLIO_COOKIE_NAME,
} from "@/lib/portfolio-auth";

export const runtime = "nodejs";

export async function POST(request: NextRequest) {
  if (!portfolioAuthConfigured()) {
    return NextResponse.json({ error: "포트폴리오 인증 환경변수가 설정되지 않았습니다." }, { status: 503 });
  }

  let body: { password?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "요청 형식이 올바르지 않습니다." }, { status: 400 });
  }

  if (!isValidPortfolioPassword(body.password)) {
    return NextResponse.json({ error: "비밀번호가 올바르지 않습니다." }, { status: 401 });
  }

  const session = createPortfolioSession();
  const response = NextResponse.json({ ok: true });
  response.cookies.set(PORTFOLIO_COOKIE_NAME, session.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: session.maxAge,
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set(PORTFOLIO_COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
