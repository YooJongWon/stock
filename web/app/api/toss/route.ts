import { NextRequest, NextResponse } from "next/server";
import { isValidPortfolioSession, PORTFOLIO_COOKIE_NAME, portfolioAuthConfigured } from "@/lib/portfolio-auth";

import { fetchTossSnapshot, TossError } from "@/lib/toss";

export const runtime = "nodejs";

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

  const relayUrl = process.env.TOSS_RELAY_URL;
  const relaySecret = process.env.TOSS_RELAY_SECRET;
  const clientId = process.env.TOSS_CLIENT_ID;
  const clientSecret = process.env.TOSS_CLIENT_SECRET;

  try {
    if (relayUrl || relaySecret) {
      if (!relayUrl || !relaySecret || new URL(relayUrl).protocol !== "https:") {
        return reply({ error: "토스증권 중계 서버 설정을 확인해 주세요." }, 503);
      }

      const response = await fetch(new URL("/snapshot", relayUrl), {
        cache: "no-store",
        redirect: "error",
        headers: { Authorization: `Bearer ${relaySecret}` },
        signal: AbortSignal.timeout(28000),
      });
      if (response.status === 401) {
        return reply({ error: "토스증권 중계 서버 인증에 실패했습니다." }, 502);
      }
      const data = await response.json();
      if (!response.ok) throw new TossError(data?.upstreamStatus ?? response.status);
      return reply(data);
    }

    if (!clientId || !clientSecret) {
      return reply({ error: "토스증권 API 키가 서버에 설정되지 않았습니다." }, 503);
    }
    return reply(await fetchTossSnapshot(clientId, clientSecret));
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
