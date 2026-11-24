export function tradingViewChartUrl(symbol: string) {
  return `https://kr.tradingview.com/chart/QaUkvTii/?symbol=${encodeURIComponent(symbol)}`;
}

export function holdingChartUrl(symbol: string, currency: string) {
  const ticker = symbol.trim().toUpperCase();
  const koreanCode = currency === "KRW" ? /^A?(\d{6})$/.exec(ticker) : null;
  if (koreanCode) return tradingViewChartUrl(`KRX:${koreanCode[1]}`);
  return tradingViewChartUrl(currency === "USD" ? ticker.replace(/-/g, ".") : ticker);
}
