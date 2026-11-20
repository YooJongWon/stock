import { NextRequest, NextResponse } from "next/server";
import { isValidPortfolioSession, PORTFOLIO_COOKIE_NAME, portfolioAuthConfigured } from "@/lib/portfolio-auth";

export const runtime = "nodejs";

const API = "https://openapi.tossinvest.com";
const requestOptions = { cache: "no-store", redirect: "error" } as const;
type Token = { value: string; expiresAt: number };

let cachedToken: Token | undefined;
let pendingToken: Promise<Token> | undefined;

class TossError extends Error {
  constructor(readonly status: number) {
    super("Toss Securities API request failed");
  }
}

async function issueToken(clientId: string, clientSecret: string): Promise<Token> {
  const response = await fetch(`${API}/oauth2/token`, {
    ...requestOptions,
    method: "POST",
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: clientId,
      client_secret: clientSecret,
    }),
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new TossError(response.status);

  const data = await response.json();
  if (typeof data?.access_token !== "string" || !data.access_token ||
      !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
    throw new Error("Invalid token response");
  }

  return {
    value: data.access_token,
    expiresAt: Date.now() + Math.max(0, data.expires_in - 30) * 1000,
  };
}

async function getToken(clientId: string, clientSecret: string) {
  if (cachedToken && cachedToken.expiresAt > Date.now()) return cachedToken;

  pendingToken ??= issueToken(clientId, clientSecret)
    .then((token) => (cachedToken = token))
    .finally(() => { pendingToken = undefined; });
  return pendingToken;
}

function reply(body: object, status = 200) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "private, no-store" } });
}

export async function GET(request: NextRequest) {
  if (!portfolioAuthConfigured()) {
    return reply({ error: "포트폴리오 인증 환경변수가 설정되지 않았습니다." }, 503);
  }
  if (!isValidPortfolioSession(request.cookies.get(PORTFOLIO_COOKIE_NAME)?.value)) {
    return reply({ error: "포트폴리오 인증이 필요합니다." }, 401);
  }

  const clientId = process.env.TOSS_CLIENT_ID;
  const clientSecret = process.env.TOSS_CLIENT_SECRET;
  if (!clientId || !clientSecret) {
    return reply({ error: "토스증권 API 키가 서버에 설정되지 않았습니다." }, 503);
  }

  try {
    const token = await getToken(clientId, clientSecret);
    const response = await fetch(`${API}/api/v1/accounts`, {
      ...requestOptions,
      headers: { Authorization: `Bearer ${token.value}` },
      signal: AbortSignal.timeout(8000),
    });
    if (response.status === 401 && cachedToken === token) cachedToken = undefined;
    if (!response.ok) throw new TossError(response.status);

    const data = await response.json();
    if (!Array.isArray(data?.result)) throw new Error("Invalid accounts response");
    return reply({ accountCount: data.result.length });
  } catch (error) {
    if (error instanceof TossError) {
      if (error.status === 403) {
        return reply({ error: "토스증권이 접근을 거부했습니다. 서버의 발신 IP와 API 권한을 확인해 주세요." }, 502);
      }
      if (error.status === 401) {
        return reply({ error: "토스증권 인증에 실패했습니다. API 키 설정을 확인하거나 다시 시도해 주세요." }, 502);
      }
      if (error.status === 429) {
        return reply({ error: "토스증권 호출 한도에 도달했습니다. 잠시 후 다시 시도해 주세요." }, 429);
      }
    }
    return reply({ error: "토스증권 연결에 실패했습니다. 잠시 후 다시 시도해 주세요." }, 502);
  }
}
