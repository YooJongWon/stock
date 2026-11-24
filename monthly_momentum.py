"""Rank monthly price momentum using the screener's already downloaded daily bars."""
from calendar import monthrange
from datetime import date, timedelta
from math import isfinite

from config import SETTINGS
from indicators import normalize_ohlcv

LIST_SIZE = 10
BOOTSTRAP_SOURCE = "existing_momentum_price_cache"


def pending_month_end(reference_date, published):
    """Select the latest completed month-end not already represented in the report."""
    import exchange_calendars as xc

    ref = date.fromisoformat(str(reference_date)[:10])
    cal = xc.get_calendar("XNYS")
    first = ref.replace(day=1)
    last = ref.replace(day=monthrange(ref.year, ref.month)[1])
    target = cal.sessions_in_range(first, last)[-1].date()
    if target > ref:
        previous_month = first - timedelta(days=1)
        target = cal.sessions_in_range(previous_month.replace(day=1), previous_month)[-1].date()
    published = published or {}
    published_date = published.get("reference_date", "")
    target_date = target.isoformat()
    if target_date > published_date or (
        target_date == published_date and published.get("source") == BOOTSTRAP_SOURCE
    ):
        return target
    return None


def rebalance_open(reference_date):
    """Regular session open following the ranking close, serialized in UTC."""
    import exchange_calendars as xc

    cal = xc.get_calendar("XNYS")
    return cal.session_open(cal.next_session(reference_date)).isoformat()


def publish_monthly(previous, current):
    """Keep the prior published list for month-over-month comparisons."""
    if not current:
        return previous
    if not previous:
        return current
    if previous["reference_date"] == current["reference_date"]:
        prior = previous.get("previous")
    else:
        prior = {"reference_date": previous["reference_date"], "items": previous["items"]}
    return {**current, "previous": prior} if prior else current


class MonthlyMomentum:
    def __init__(self, reference_date):
        import exchange_calendars as xc

        self.reference_date = reference_date
        cal = xc.get_calendar("XNYS")
        sessions = cal.sessions_in_range(reference_date - timedelta(days=400), reference_date)
        self.start, self.end = sessions[-253].date(), sessions[-22].date()
        self.liquidity_days = list(sessions[-30:].date)
        self.ranked = []

    def observe(self, member, frame):
        # Use the same 252/21-session anchors as the research. Missing anchor
        # sessions cannot shift the lookback or turn a stale close into a signal.
        bars = normalize_ohlcv(frame, self.reference_date)
        required = bars.reindex([self.start, self.end, *self.liquidity_days])
        if required[["Close", "Volume"]].isna().any().any():
            return
        first, last = required.Close.iloc[:2]
        recent = required.iloc[2:]
        dollar_volume = (recent.Close * recent.Volume).mean()
        if recent.Close.iloc[-1] < SETTINGS.price_min or dollar_volume < SETTINGS.avg_dollar_volume_min:
            return
        change = float((last / first - 1) * 100)
        if isfinite(change):
            self.ranked.append({
                "ticker": member["ticker"],
                "name": member.get("name"),
                "exchange": member.get("exchange"),
                "return_pct": change,
            })

    def result(self):
        if not self.ranked:
            return None
        ranked = sorted(self.ranked, key=lambda item: (-item["return_pct"], item["ticker"]))
        return {
            "reference_date": self.reference_date.isoformat(),
            "rebalance_open_at": rebalance_open(self.reference_date),
            "period_start": self.start.isoformat(),
            "period_end": self.end.isoformat(),
            "eligible_count": len(ranked),
            "items": ranked[:LIST_SIZE],
        }
