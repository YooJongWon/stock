"""Exercise FinImpulse API on up to ten technical candidates within a daily cap.

Sandbox responses are dummy data. Live API requests incur usage-based costs.
Diagnostic results never feed the screener's BUY/WATCH decisions.
"""
from __future__ import annotations

import json
import pandas as pd

from config import SETTINGS
from providers.finimpulse_sandbox import FinImpulseSandboxClient


def main():
    summary_path = SETTINGS.output_dir / "run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    input_path = SETTINGS.output_dir / "technical_candidates.csv"
    if not input_path.exists():
        raise SystemExit(f"Missing {input_path}; run StockScreener.exe first.")
    candidates = pd.read_csv(input_path).head(10)
    client = FinImpulseSandboxClient()
    # One ticker needs two endpoint requests. Keep each daily run within the
    # remaining local daily cap, including requests from earlier runs today.
    ticker_count = min(len(candidates), client.daily_requests_remaining // 2)
    candidates = candidates.head(ticker_count)
    ref = summary.get("reference_date")
    if not ref and not candidates.empty:
        ref = str(candidates.iloc[0].get("Reference Date", ""))[:10]
    if not ref:
        raise SystemExit("Could not determine the reference date from the prior screener output.")

    results = []
    if not client.configured:
        results = [{"ticker": str(row.get("Ticker", "")).strip(), "error": "FINIMPULSE_API_TOKEN is blank"}
                   for _, row in candidates.iterrows()]
    else:
        for _, row in candidates.iterrows():
            ticker = str(row.get("Ticker", "")).strip()
            try:
                values = client.get_test_fundamentals(ticker, ref)
                results.append({"ticker": ticker, "values": values})
                mode = "live" if values.get("live") else "dummy sandbox"
                print(f"{ticker}: OK | {mode} | cost=${float(values.get('total_cost') or 0):.4f} | P/E={values.get('pe')} | ROE={values.get('roe')}")
            except Exception as exc:
                results.append({"ticker": ticker, "error": str(exc).replace(client.token, "[redacted]")})
                print(f"{ticker}: ERROR | {results[-1]['error']}")

    live_results = [item["values"] for item in results if "values" in item and item["values"].get("live")]
    dummy_results = [item["values"] for item in results if "values" in item and item["values"].get("sandbox_dummy_data")]
    total_cost = sum(float(value.get("total_cost") or 0) for value in live_results)
    mode = "LIVE API DATA" if live_results else ("SANDBOX DUMMY DATA" if dummy_results else "UNCONFIRMED")
    lines = [f"# FinImpulse API — {len(results)}-stock diagnostic", "",
             f"> **Mode: {mode}. Diagnostic results do not feed BUY/WATCH decisions.**", "",
             f"- Reference date used in requests: {ref}",
             f"- API token configured: {'yes' if client.configured else 'no'}",
             f"- Live responses: {len(live_results)}",
             f"- Sandbox dummy responses: {len(dummy_results)}",
             f"- Tickers attempted: {len(results)}",
             f"- HTTP requests sent by this run: {client.api_request_count}",
             f"- Daily API calls used: {client.daily_requests_used}/{SETTINGS.finimpulse_daily_max_requests}",
             f"- Daily API calls remaining: {client.daily_requests_remaining}",
             f"- Successful ticker responses: {sum('values' in item for item in results)}",
             f"- Reported live API cost this run: ${total_cost:.4f}",
             f"- Reported live API cost today: ${client.daily_cost_today:.4f}", "",
             "| Ticker | Status | Market Cap | P/E | ROE | 5Y Sales CAGR | Quote Type | Cost | Details |",
             "| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |"]
    for item in results:
        if "values" in item:
            values = item["values"]
            def fmt(value, kind):
                if value is None:
                    return "—"
                if kind == "cap":
                    return f"${value / 1e9:,.2f}B"
                if kind == "pct":
                    return f"{value:.1%}"
                return f"{value:.2f}"
            details = "; ".join(f"{key}: {value}" for key, value in (
                ("5Y periods", values.get("sales_growth_periods")),
                ("status", values.get("summary_status")),
            ) if value is not None)
            status = "OK · LIVE" if values.get("live") else "OK · DUMMY"
            cells = [item["ticker"], status, fmt(values.get("market_cap"), "cap"),
                     fmt(values.get("pe"), "num"), fmt(values.get("roe"), "pct"),
                     fmt(values.get("sales_growth_5y"), "pct"), values.get("quote_type") or "—",
                     f"${float(values.get('total_cost') or 0):.4f}", details or "—"]
        else:
            cells = [item["ticker"], "ERROR", "—", "—", "—", "—", "—", "—", item["error"]]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ") for value in cells) + " |")

    report_path = SETTINGS.output_dir / "finimpulse_api_diagnostic.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nDiagnostic report: {report_path}")
    if live_results:
        print(f"Reported live API cost this run: ${total_cost:.4f}")
    print(f"Daily API usage: {client.daily_requests_used}/{SETTINGS.finimpulse_daily_max_requests} requests")


if __name__ == "__main__":
    main()
