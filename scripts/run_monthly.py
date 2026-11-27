"""Publish monthly momentum and daily loss checks for the dashboard."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import exchange_calendars as xc

from scripts.run_cloud import ROOT, _atomic_write, _read_current_result
from data_provider import DataProvider, UniverseProvider
from indicators import spy_market_regime
from market_calendar import batch_day_us_session, is_exchange_session, latest_completed_session, previous_korea_date
from monthly_company_risk import review_monthly_companies
from monthly_momentum import MonthlyMomentum, MonthlyRiskMonitor, assess_monthly_ranking, pending_month_end, publish_monthly
from sector_performance import daily_price_change, daily_sector_performance, monthly_stock_sectors


def write_status(path, status, reference_date, attempted_at, market_session):
    _atomic_write(path, json.dumps({
        "status": status,
        "attempted_at": attempted_at,
        "reference_date": str(reference_date),
        "market_session": market_session,
        "message": None,
    }, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--skip-unchanged", action="store_true")
    args = parser.parse_args(argv)

    result_path = ROOT / "web" / "public" / "data" / "latest-results.json"
    status_path = result_path.with_name("latest-run-status.json")
    attempted_at = datetime.now(timezone.utc)
    market_session = batch_day_us_session(attempted_at)
    reference_date = previous_korea_date(attempted_at) if args.scheduled else latest_completed_session(attempted_at)
    current = _read_current_result(result_path)
    monthly = current.get("monthly_momentum")
    last_review = (monthly or {}).get("company_risk") or {}
    company_check_due = not str(last_review.get("checked_at", "")).startswith(attempted_at.date().isoformat())
    if not is_exchange_session(reference_date):
        if args.scheduled:
            if monthly and company_check_due:
                monthly["company_risk"] = review_monthly_companies(
                    monthly, attempted_at, last_review.get("price_context") or {},
                )
                _atomic_write(result_path, json.dumps(current, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
            last = _read_current_result(status_path)
            if (last.get("status"), last.get("reference_date"), last.get("market_session")) != (
                "market_closed", str(reference_date), market_session
            ):
                write_status(status_path, "market_closed", reference_date, attempted_at.isoformat(), market_session)
            print(f"U.S. market closed on {reference_date}. Keeping the last trading session's results.")
            return 0
        raise RuntimeError(f"Invalid XNYS session: {reference_date}")

    month_end = pending_month_end(reference_date, monthly, refresh_bootstrap=False)
    daily_risk = (monthly or {}).get("daily_risk") or {}
    if (
        args.skip_unchanged and month_end is None
        and daily_risk.get("reference_date") == str(reference_date)
        and current.get("sector_reference_date") == str(reference_date)
        and current.get("status") == "success"
        and not company_check_due
    ):
        last = _read_current_result(status_path)
        if (last.get("status"), last.get("reference_date"), last.get("market_session")) != (
            "success", str(reference_date), market_session
        ):
            write_status(status_path, "success", reference_date, attempted_at.isoformat(), market_session)
        print(f"Monthly momentum checks already published for {reference_date}.")
        return 0

    prices = DataProvider()
    spy = prices.history("SPY", reference_date)
    if spy.frame is None:
        raise RuntimeError(f"SPY close unavailable for {reference_date}: {spy.error}")
    market = spy_market_regime(spy.frame, reference_date)
    if market.get("reference_date") != str(reference_date):
        raise RuntimeError(f"SPY close unconfirmed for {reference_date}")

    ranking_quality = current.get("monthly_ranking_quality")
    if month_end is not None:
        ranking = MonthlyMomentum(month_end)
        members = list(UniverseProvider().get())
        for member in members:
            quote = prices.history(member["ticker"], month_end)
            if quote.frame is None:
                continue
            try:
                ranking.observe(member, quote.frame)
            except (ValueError, KeyError) as exc:
                print(f"Skipping {member['ticker']} in the month-end ranking: {exc}")
        ranked, ranking_quality = assess_monthly_ranking(ranking, len(members))
        if ranked is None:
            print(f"Holding month-end ranking: {ranking_quality}")
        monthly = publish_monthly(monthly, ranked)

    monitor = MonthlyRiskMonitor(reference_date, monthly)
    if monthly and str(reference_date) > monthly["reference_date"]:
        for member in monthly["items"]:
            ticker = member["ticker"]
            quote = spy if ticker == "SPY" else prices.history(ticker, reference_date)
            if quote.frame is not None:
                monitor.observe(member, quote.frame)
    monitored = monitor.result(monthly)
    risk_items = (monitored or {}).get("daily_risk", {}).get("items", {})
    unchecked = [
        ticker for ticker, item in risk_items.items()
        if item["status"] == "unavailable"
    ]
    sectors = daily_sector_performance(prices, reference_date)
    stock_sectors = monthly_stock_sectors(monthly, current.get("stock_sectors") or {})
    if monitored:
        previous_date = xc.get_calendar("XNYS").previous_session(reference_date).date()
        try:
            spy_change = daily_price_change(spy.frame, reference_date, previous_date)
        except (ValueError, KeyError):
            spy_change = None
        changes_by_etf = {sector["symbol"]: sector["change_pct"] for sector in sectors}
        price_context = {}
        for ticker, frame in monitor.frames.items():
            try:
                change = daily_price_change(frame, reference_date, previous_date)
            except (ValueError, KeyError):
                continue
            price_context[ticker] = {
                "daily_return_pct": change,
                "spy_change": spy_change,
                "sector_change": changes_by_etf.get(stock_sectors.get(ticker)),
            }
        monitored["company_risk"] = review_monthly_companies(monitored, attempted_at, price_context)
    now = datetime.now(timezone.utc).isoformat()
    ranking_held = ranking_quality and ranking_quality["status"] == "held"
    payload = {
        "schema_version": 1,
        "status": "degraded" if unchecked or ranking_held else "success",
        "last_successful_run_at": now,
        "data_date": str(reference_date),
        "spy_regime": market["market_regime"],
        "spy_reference_date": market["reference_date"],
        "monthly_momentum": monitored,
        "monthly_ranking_quality": ranking_quality,
        "sector_reference_date": str(reference_date),
        "sector_performance": sectors,
        "stock_sectors": stock_sectors,
    }
    _atomic_write(result_path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    write_status(status_path, payload["status"], reference_date, attempted_at.isoformat(), market_session)
    print(f"Monthly momentum for {reference_date}. Price checks unavailable: {', '.join(unchecked) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
