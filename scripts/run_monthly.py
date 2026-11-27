"""Publish monthly momentum and daily loss checks for the dashboard."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from scripts.run_cloud import ROOT, _atomic_write, _read_current_result
from data_provider import DataProvider, UniverseProvider
from indicators import spy_market_regime
from market_calendar import is_exchange_session, latest_completed_session, previous_korea_date
from monthly_momentum import MonthlyMomentum, MonthlyRiskMonitor, pending_month_end, publish_monthly
from sector_performance import daily_sector_performance, monthly_stock_sectors


def write_status(path, status, reference_date, attempted_at):
    _atomic_write(path, json.dumps({
        "status": status,
        "attempted_at": attempted_at,
        "reference_date": str(reference_date),
        "message": None,
    }, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scheduled", action="store_true")
    parser.add_argument("--skip-unchanged", action="store_true")
    args = parser.parse_args(argv)

    result_path = ROOT / "web" / "public" / "data" / "latest-results.json"
    status_path = result_path.with_name("latest-run-status.json")
    reference_date = previous_korea_date() if args.scheduled else latest_completed_session()
    if not is_exchange_session(reference_date):
        if args.scheduled:
            last = _read_current_result(status_path)
            if last.get("status") != "market_closed" or last.get("reference_date") != str(reference_date):
                write_status(status_path, "market_closed", reference_date, datetime.now(timezone.utc).isoformat())
            print(f"U.S. market closed on {reference_date}. Keeping the last trading session's results.")
            return 0
        raise RuntimeError(f"Invalid XNYS session: {reference_date}")

    current = _read_current_result(result_path)
    monthly = current.get("monthly_momentum")
    month_end = pending_month_end(reference_date, monthly, refresh_bootstrap=False)
    daily_risk = (monthly or {}).get("daily_risk") or {}
    if (
        args.skip_unchanged and month_end is None
        and daily_risk.get("reference_date") == str(reference_date)
        and current.get("sector_reference_date") == str(reference_date)
        and current.get("status") == "success"
    ):
        last = _read_current_result(status_path)
        if last.get("status") != "success" or last.get("reference_date") != str(reference_date):
            write_status(status_path, "success", reference_date, datetime.now(timezone.utc).isoformat())
        print(f"Monthly momentum checks already published for {reference_date}.")
        return 0

    prices = DataProvider()
    spy = prices.history("SPY", reference_date)
    if spy.frame is None:
        raise RuntimeError(f"SPY close unavailable for {reference_date}: {spy.error}")
    market = spy_market_regime(spy.frame, reference_date)
    if market.get("reference_date") != str(reference_date):
        raise RuntimeError(f"SPY close unconfirmed for {reference_date}")

    if month_end is not None:
        ranking = MonthlyMomentum(month_end)
        for member in UniverseProvider().get():
            quote = prices.history(member["ticker"], month_end)
            if quote.frame is None:
                continue
            try:
                ranking.observe(member, quote.frame)
            except (ValueError, KeyError) as exc:
                print(f"Skipping {member['ticker']} in the month-end ranking: {exc}")
        ranked = ranking.result()
        if not ranked or len(ranked["items"]) < 10:
            raise RuntimeError(f"Fewer than ten eligible prices for the {month_end} ranking")
        monthly = publish_monthly(monthly, ranked)

    monitor = MonthlyRiskMonitor(reference_date, monthly)
    if monthly and str(reference_date) > monthly["reference_date"]:
        for member in monthly["items"]:
            ticker = member["ticker"]
            quote = spy if ticker == "SPY" else prices.history(ticker, reference_date)
            if quote.frame is not None:
                monitor.observe(member, quote.frame)
    monitored = monitor.result(monthly)
    unchecked = [
        ticker for ticker, item in monitored["daily_risk"]["items"].items()
        if item["status"] == "unavailable"
    ]
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": 1,
        "status": "degraded" if unchecked else "success",
        "last_successful_run_at": now,
        "data_date": str(reference_date),
        "spy_regime": market["market_regime"],
        "spy_reference_date": market["reference_date"],
        "monthly_momentum": monitored,
        "sector_reference_date": str(reference_date),
        "sector_performance": daily_sector_performance(prices, reference_date),
        "stock_sectors": monthly_stock_sectors(monthly, current.get("stock_sectors") or {}),
    }
    _atomic_write(result_path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    write_status(status_path, payload["status"], reference_date, now)
    print(f"Monthly momentum for {reference_date}. Price checks unavailable: {', '.join(unchecked) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
