"""Canonical sector classification and daily sector ETF returns."""
import logging
from math import isfinite

import exchange_calendars as xc

from indicators import normalize_ohlcv
from providers.yfinance_provider import YFinanceProvider

LOG = logging.getLogger(__name__)

# Yahoo sector key, Select Sector SPDR symbol, dashboard label.
SECTORS = (
    ("basic-materials", "XLB", "소재"),
    ("communication-services", "XLC", "커뮤니케이션 서비스"),
    ("energy", "XLE", "에너지"),
    ("financial-services", "XLF", "금융"),
    ("industrials", "XLI", "산업재"),
    ("technology", "XLK", "정보기술"),
    ("consumer-defensive", "XLP", "필수소비재"),
    ("real-estate", "XLRE", "부동산"),
    ("utilities", "XLU", "유틸리티"),
    ("healthcare", "XLV", "헬스케어"),
    ("consumer-cyclical", "XLY", "임의소비재"),
)
SECTOR_ETFS = tuple((symbol, label) for _, symbol, label in SECTORS)
SECTOR_BY_KEY = {key: symbol for key, symbol, _ in SECTORS}


def daily_price_change(frame, reference_date, previous_date):
    closes = normalize_ohlcv(frame, reference_date).Close
    previous, current = closes.reindex([previous_date, reference_date])
    if not all(isfinite(value) and value > 0 for value in (previous, current)):
        raise ValueError(f"missing valid close on {previous_date} or {reference_date}")
    return round((current / previous - 1) * 100, 2)


def daily_sector_performance(prices, reference_date):
    previous_date = xc.get_calendar("XNYS").previous_session(reference_date).date()
    results = []
    for symbol, sector in SECTOR_ETFS:
        change = None
        try:
            result = prices.history(symbol, reference_date)
            if result.frame is None:
                raise ValueError(result.error or "ETF history unavailable")
            change = daily_price_change(result.frame, reference_date, previous_date)
        except (KeyError, ValueError) as exc:
            LOG.warning("Sector ETF %s unavailable: %s", symbol, exc)
        results.append({"symbol": symbol, "sector": sector, "change_pct": change})
    return results


def monthly_stock_sectors(monthly, known):
    """Resolve only names shown on the dashboard, caching confirmed classifications."""
    if not monthly:
        return {}
    symbols = {symbol for symbol, _ in SECTOR_ETFS}
    provider = YFinanceProvider(retries=0)
    items = monthly["items"] + (monthly.get("previous") or {}).get("items", [])
    result = {}
    for ticker in dict.fromkeys(item["ticker"] for item in items):
        if known.get(ticker) in symbols:
            result[ticker] = known[ticker]
            continue
        try:
            info = provider.instrument_info(ticker)
            key = info.get("sectorKey") or str(info.get("sector") or "").lower().replace(" ", "-")
            if key in SECTOR_BY_KEY:
                result[ticker] = SECTOR_BY_KEY[key]
        except RuntimeError as exc:
            LOG.warning("Stock sector %s unavailable: %s", ticker, exc)
    return result
