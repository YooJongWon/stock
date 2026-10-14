from __future__ import annotations

from datetime import date, timedelta
import hashlib
import json
import threading
import requests

from config import SETTINGS


class FinImpulseSandboxClient:
    """FinImpulse API client with a local daily request cap and usage ledger."""

    base_url = "https://api.finimpulse.com/v1"
    _usage_lock = threading.Lock()

    def __init__(self, token=None, session=None, usage_path=None):
        self.token = (token if token is not None else SETTINGS.finimpulse_sandbox_token).strip()
        self.session = session or requests.Session()
        self.api_request_count = 0
        self._token_id = hashlib.sha256(self.token.encode("utf-8")).hexdigest()[:16]
        self._usage_path = usage_path or (SETTINGS.cache_dir / "finimpulse_daily_usage.json")
        self._usage_date = date.today().isoformat()
        self._daily_usage = self._load_daily_usage()
        self.daily_cost_today = float(self._daily_usage.get("cost", 0.0))
        self.daily_blocked = False

    @property
    def configured(self):
        return bool(self.token)

    def _load_daily_usage(self):
        try:
            database = json.loads(self._usage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            database = {}
        record = database.get(self._token_id, {}) if isinstance(database, dict) else {}
        if record.get("date") != self._usage_date:
            return {"date": self._usage_date, "requests": 0, "cost": 0.0}
        return {
            "date": self._usage_date,
            "requests": max(0, int(record.get("requests", 0))),
            "cost": max(0.0, float(record.get("cost", 0.0))),
        }

    def _save_daily_usage(self):
        with self._usage_lock:
            try:
                database = json.loads(self._usage_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                database = {}
            if not isinstance(database, dict):
                database = {}
            database[self._token_id] = self._daily_usage
            self._usage_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._usage_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(database, indent=2), encoding="utf-8")
            temporary.replace(self._usage_path)

    @property
    def daily_requests_used(self):
        return int(self._daily_usage["requests"])

    @property
    def daily_requests_remaining(self):
        return max(0, SETTINGS.finimpulse_daily_max_requests - self.daily_requests_used)

    def _reserve_daily_request(self, endpoint):
        if self.daily_blocked:
            raise RuntimeError("FinImpulse daily API limit was reached; no request sent")
        if self.daily_requests_remaining <= 0:
            self.daily_blocked = True
            raise RuntimeError(
                f"Local FinImpulse daily request cap reached "
                f"({SETTINGS.finimpulse_daily_max_requests}); no request sent"
            )
        # Count before sending so a crash or retry cannot bypass the local cap.
        self._daily_usage["requests"] += 1
        self._save_daily_usage()
        self.api_request_count += 1

    def _record_response_cost(self, payload):
        value = payload.get("cost")
        if isinstance(value, (int, float)) and value > 0:
            self._daily_usage["cost"] += float(value)
            self.daily_cost_today = float(self._daily_usage["cost"])
            self._save_daily_usage()

    def _post(self, endpoint, body):
        if not self.configured:
            raise RuntimeError("FINIMPULSE_API_TOKEN is not set in the project's .env file")
        self._reserve_daily_request(endpoint)
        try:
            response = self.session.post(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            detail = str(exc).replace(self.token, "[redacted]")
            raise RuntimeError(f"FinImpulse request failed for {endpoint}: {detail}") from None
        if not response.ok:
            detail = response.text[:300].replace(self.token, "[redacted]").replace("\r", " ").replace("\n", " ")
            raise RuntimeError(f"FinImpulse HTTP {response.status_code} for {endpoint}: {detail}")
        try:
            payload = response.json()
        except ValueError:
            raise RuntimeError(f"FinImpulse returned invalid JSON for {endpoint}") from None
        if not isinstance(payload, dict):
            raise RuntimeError(f"FinImpulse returned unexpected data for {endpoint}")
        status = payload.get("status_code")
        if status in (42901, "42901"):
            self.daily_blocked = True
            raise RuntimeError("FinImpulse daily credit limit exceeded; stopping further requests")
        if status not in (None, 20000, "20000"):
            message = str(payload.get("status_message") or payload.get("message") or "API request failed")
            raise RuntimeError(f"FinImpulse {endpoint}: {message[:240]}")
        self._record_response_cost(payload)
        return payload

    @staticmethod
    def _object(payload):
        value = payload.get("result") or payload.get("data") or payload
        if isinstance(value, list):
            return value[0] if value and isinstance(value[0], dict) else {}
        return value if isinstance(value, dict) else {}

    def get_fundamentals(self, ticker, reference_date):
        ref = date.fromisoformat(str(reference_date)[:10])
        summary_payload = self._post("summary", {"symbol": ticker})
        income_payload = self._post(
            "financials/income_statement",
            {
                "symbol": ticker,
                "intervals": ["annual"],
                "start_date": str(ref - timedelta(days=6 * 366)),
                "end_date": str(ref),
            },
        )
        summary = self._object(summary_payload)
        income_result = self._object(income_payload)
        items = income_result.get("items", [])
        annual = []
        for row in items if isinstance(items, list) else []:
            if str(row.get("interval", "")).lower() != "annual":
                continue
            try:
                period_end = date.fromisoformat(str(row.get("date", ""))[:10])
            except ValueError:
                continue
            try:
                revenue = float(row.get("total_revenue"))
            except (TypeError, ValueError):
                continue
            if period_end <= ref and revenue > 0:
                annual.append((period_end, revenue))
        annual.sort(key=lambda row: row[0])
        growth = None
        growth_periods = None
        if len(annual) >= 2:
            latest_date, latest_revenue = annual[-1]
            target = min(annual[:-1], key=lambda row: abs((latest_date - row[0]).days - 365.25 * 5))
            base_date, base_revenue = target
            years = (latest_date - base_date).days / 365.25
            if 4 <= years <= 6 and base_revenue > 0:
                growth = (latest_revenue / base_revenue) ** (1 / years) - 1
                growth_periods = {"base_period_end": str(base_date), "latest_period_end": str(latest_date)}

        def number(*keys):
            for key in keys:
                value = summary.get(key)
                try:
                    if value is not None:
                        return float(value)
                except (TypeError, ValueError):
                    continue
            return None

        return {
            "ticker": ticker,
            "market_cap": number("market_cap", "valuation_measures_market_cap"),
            "pe": number("trailing_pe", "valuation_measures_pe_ratio", "price_to_earnings"),
            "roe": number("return_on_equity"),
            "sales_growth_5y": growth,
            "sales_growth_periods": growth_periods,
            "quote_type": summary.get("quote_type"),
            "display_name": summary.get("display_name") or summary.get("long_name"),
            "live": summary_payload.get("live", income_payload.get("live")),
            "summary_cost": summary_payload.get("cost"),
            "income_cost": income_payload.get("cost"),
            "total_cost": sum(
                float(value) for value in (summary_payload.get("cost"), income_payload.get("cost"))
                if isinstance(value, (int, float))
            ),
            "summary_status": summary_payload.get("status_message"),
            "income_status": income_payload.get("status_message"),
            "sandbox_dummy_data": not bool(summary_payload.get("live", income_payload.get("live"))),
        }

    def get_test_fundamentals(self, ticker, reference_date):
        """Compatibility wrapper for the standalone diagnostic."""
        return self.get_fundamentals(ticker, reference_date)
