import { NextRequest, NextResponse } from "next/server";
import { isValidPortfolioSession, PORTFOLIO_COOKIE_NAME } from "@/lib/portfolio-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type YahooQuote = {
  symbol?: string;
  shortname?: string;
  longname?: string;
  exchDisp?: string;
  exchange?: string;
  quoteType?: string;
};

type YahooSearchResponse = { quotes?: YahooQuote[] };

export async function GET(request: NextRequest) {
  if (!isValidPortfolioSession(request.cookies.get(PORTFOLIO_COOKIE_NAME)?.value)) {
    return NextResponse.json({ error: "인증이 필요합니다." }, { status: 401 });
  }

  const query = request.nextUrl.searchParams.get("q")?.trim() || "";
  if (query.length < 2 || query.length > 60) {
    return NextResponse.json({ results: [] }, {
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    });
  }

  try {
    const url = new URL("https://query1.finance.yahoo.com/v1/finance/search");
    url.searchParams.set("q", query);
    url.searchParams.set("lang", "en-US");
    url.searchParams.set("region", "US");
    url.searchParams.set("quotesCount", "12");
    url.searchParams.set("newsCount", "0");
    url.searchParams.set("enableFuzzyQuery", "true");

    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; Jong9StockPortfolio/1.0)",
      },
      signal: AbortSignal.timeout(6000),
      next: { revalidate: 120 },
    });
    if (!response.ok) {
      return NextResponse.json({ error: "종목 검색 서비스 응답이 원활하지 않습니다." }, { status: 502 });
    }

    const data = await response.json() as YahooSearchResponse;
    const seen = new Set<string>();
    const results = (data.quotes || [])
      .filter((item) =>
        (item.quoteType === "EQUITY" || item.quoteType === "ETF") &&
        typeof item.symbol === "string" &&
        /^[A-Z0-9.^=-]{1,20}$/.test(item.symbol) &&
        !seen.has(item.symbol) &&
        Boolean(item.longname || item.shortname)
      )
      .map((item) => {
        const symbol = item.symbol!;
        seen.add(symbol);
        return {
          symbol,
          name: item.longname || item.shortname || symbol,
          exchange: item.exchDisp || item.exchange || "미국 시장",
        };
      })
      .slice(0, 8);

    return NextResponse.json({ results }, {
      headers: { "Cache-Control": "private, no-store, max-age=0" },
    });
  } catch {
    return NextResponse.json({ error: "종목 검색 중 연결 오류가 발생했습니다." }, { status: 502 });
  }
}
