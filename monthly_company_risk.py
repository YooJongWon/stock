"""Evaluate public SEC disclosures and contextualize daily moves for the monthly basket."""
import logging
import re
from datetime import timedelta
from math import isfinite
from zoneinfo import ZoneInfo

import requests

from data_provider import UniverseProvider, _canonical_ticker
from providers.sec_fundamentals import SECFundamentalProvider

LOG = logging.getLogger(__name__)
EVENTS = {
    "1.03": ("review", "법원이 관여하는 파산·회생 절차를 공시했습니다."),
    "2.04": ("review", "빚을 앞당겨 갚아야 하거나 상환 부담이 커질 수 있는 사건을 공시했습니다."),
    "4.02": ("review", "기존 재무제표를 신뢰할 수 없다는 공시가 나왔습니다."),
    "3.01": ("watch", "거래소 상장 요건 미충족 또는 상장폐지 관련 공시가 나왔습니다."),
    "2.06": ("watch", "자산 가치가 크게 줄어 회계상 손실을 반영한다고 공시했습니다."),
    "2.02": ("notice", "실적 발표 공시가 나왔습니다."),
}
PERIODIC_FORMS = {"10-K", "10-Q", "20-F", "40-F"}
SEC_ERRORS = (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError)


def filing_rows(payload, as_of):
    recent = payload["filings"]["recent"]
    columns = ("accessionNumber", "filingDate", "form", "items", "reportDate")
    values = [recent[key] for key in columns]
    if any(not isinstance(value, list) for value in values) or len({len(value) for value in values}) != 1:
        raise ValueError("Malformed SEC filing list")
    rows = []
    for accession, filed, form, items, period in zip(*values):
        if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
            continue
        if filed <= as_of:
            rows.append((filed, accession, form.removesuffix("/A"), items, period))
    return sorted(rows, reverse=True)


def evidence(cik, row, message):
    filed, accession, form, _, _ = row
    index = accession.replace("-", "")
    return {
        "date": filed,
        "message": message,
        "form": form,
        "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{index}/{accession}-index.htm",
    }


def financial_signals(provider, cik, row):
    # Bind values to the same filing, exact balance-sheet period and currency.
    facts = provider._get_json(
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json", cik, 3600,
    )["facts"].get("us-gaap", {})
    _, accession, _, _, period = row

    def value(tag):
        records = facts.get(tag, {}).get("units", {}).get("USD", [])
        values = {
            item["val"] for item in records
            if item.get("accn") == accession and item.get("end") == period
            and not item.get("start") and type(item.get("val")) in (int, float)
            and isfinite(item["val"])
        }
        return values.pop() if len(values) == 1 else None

    equity = value("StockholdersEquity")
    assets = value("AssetsCurrent")
    liabilities = value("LiabilitiesCurrent")
    has_liquidity = assets is not None and liabilities is not None and liabilities > 0
    signals = []
    if equity is not None and equity < 0:
        signals.append(("watch", evidence(cik, row, "최신 보고서의 주주 몫 자산(자기자본)이 마이너스입니다.")))
    if has_liquidity and 0 <= assets < liabilities:
        signals.append(("watch", evidence(cik, row, f"1년 안에 현금화할 자산이 단기부채의 {assets / liabilities:.2f}배입니다.")))
    return signals, equity is not None and has_liquidity


def check_company(provider, cik, as_of, since):
    payload = provider._get_json(
        f"https://data.sec.gov/submissions/CIK{cik}.json", f"monthly-submissions:{cik}", 900,
    )
    rows = filing_rows(payload, as_of)
    events = []
    for row in rows:
        filed, _, form, items, _ = row
        if filed < since:
            break
        if form == "8-K":
            for code in dict.fromkeys(re.findall(r"\b\d\.\d{2}\b", items or "")):
                if code in EVENTS:
                    level, message = EVENTS[code]
                    events.append((level, evidence(cik, row, message)))
        elif form == "6-K":
            events.append(("notice", evidence(cik, row, "해외 발행사의 새 공시가 나왔습니다. 세부 내용은 원문 확인이 필요합니다.")))
    periodic = next((row for row in rows if row[2] in PERIODIC_FORMS and row[4]), None)
    fundamentals_checked = False
    if periodic:
        try:
            signals, fundamentals_checked = financial_signals(provider, cik, periodic)
            events.extend(signals)
        except SEC_ERRORS as exc:
            LOG.warning("Monthly SEC financial data unavailable for CIK %s: %s", cik, type(exc).__name__)
    return events, fundamentals_checked


def assess_item(events, filings_checked, fundamentals_checked, price, spy_change, sector_change):
    drawdown = price.get("drawdown_pct")
    change = price.get("daily_return_pct")
    details = []
    if drawdown is not None:
        details.append(f"리밸런싱 이후 고점 대비 {drawdown:+.2f}%.")
    if change is not None:
        context = [f"당일 {change:+.2f}%"]
        if spy_change is not None:
            context.append(f"SPY 대비 {change - spy_change:+.2f}%p")
        if sector_change is not None:
            context.append(f"섹터 ETF 대비 {change - sector_change:+.2f}%p")
        details.append(" · ".join(context) + ".")
    if change is not None and change < 0:
        details.append("공시와 주가 하락의 인과관계는 확인되지 않았습니다." if events else
                       "확인된 공시에서 하락 원인을 특정할 수 없습니다." if filings_checked else
                       "공시 조회가 불완전해 하락 원인을 확인할 수 없습니다.")
    if not filings_checked:
        details.append("SEC 공시 확인 불가.")
    elif not events:
        details.append("최근 30일 공시에서 점검 대상 위험 항목이 확인되지 않았습니다.")
    if filings_checked and not fundamentals_checked:
        details.append("최신 보고서의 재무 수치는 일부 또는 전부 확인 불가.")
    if drawdown is None:
        details.append("고점 대비 하락률은 " + ("집계 대기 중입니다." if price.get("status") == "pending" else "확인 불가입니다."))

    priorities = {"review": 0, "watch": 1, "notice": 2}
    events.sort(key=lambda event: priorities[event[0]])
    levels = {level for level, _ in events}
    status = "observe"
    if "review" in levels:
        status = "review"
    elif "watch" in levels or price.get("status") in {"warning", "severe"}:
        status = "watch"
    elif not filings_checked or not fundamentals_checked or drawdown is None:
        status = "unavailable"
    return {"status": status, "details": details, "evidence": [item for _, item in events[:5]]}


def review_monthly_companies(monthly, checked_at, price_context):
    risk = monthly.get("daily_risk") or {}
    prices = risk.get("items", {})
    as_of = checked_at.astimezone(ZoneInfo("America/New_York")).date()
    since = (as_of - timedelta(days=30)).isoformat()
    provider = SECFundamentalProvider()
    tickers = {}
    try:
        directory = provider._get_json(UniverseProvider.EXCHANGE_URL, "monthly-ticker-directory", 86400)
        tickers = {member["ticker"]: member["cik"] for member in UniverseProvider._from_exchange_file(directory)}
    except SEC_ERRORS as exc:
        LOG.warning("Monthly SEC ticker mapping unavailable: %s", type(exc).__name__)

    result = {}
    for member in monthly["items"]:
        ticker = member["ticker"]
        cik = tickers.get(_canonical_ticker(ticker))
        events, fundamentals_checked, filings_checked = [], False, False
        if cik:
            try:
                events, fundamentals_checked = check_company(provider, cik, as_of.isoformat(), since)
                filings_checked = True
            except SEC_ERRORS as exc:
                LOG.warning("Monthly SEC filings unavailable for %s: %s", ticker, type(exc).__name__)
        context = price_context.get(ticker, {})
        result[ticker] = assess_item(
            events, filings_checked, fundamentals_checked,
            {**prices.get(ticker, {}), "daily_return_pct": context.get("daily_return_pct")},
            context.get("spy_change"), context.get("sector_change"),
        )
    return {
        "checked_at": checked_at.isoformat(),
        "price_date": risk.get("reference_date"),
        "price_context": price_context,
        "items": result,
    }
