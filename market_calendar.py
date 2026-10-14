from __future__ import annotations
from datetime import datetime, date, time
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

def latest_completed_session(now: datetime | None = None) -> date:
    """Last NYSE session whose regular close (16:00 ET) has passed."""
    now = now or datetime.now(NY)
    if now.tzinfo is None:
        now = now.replace(tzinfo=NY)
    now = now.astimezone(NY)
    try:
        import exchange_calendars as xc
        cal = xc.get_calendar("XNYS")
        sessions = cal.sessions_in_range((now.date().replace(day=1).replace(month=1)), now.date())
        for session in reversed(sessions):
            close = cal.session_close(session).to_pydatetime().astimezone(NY)
            if close <= now:
                return session.date()
        prev = cal.previous_session(sessions[0]) if len(sessions) else cal.date_to_session(now.date(), direction="previous")
        return prev.date()
    except (ImportError, ValueError, IndexError):
        # Calendar package is a required dependency; conservative weekday fallback keeps CLI usable.
        d = now.date()
        if d.weekday() < 5 and now.time() < time(16, 0):
            d = date.fromordinal(d.toordinal()-1)
        while d.weekday() >= 5:
            d = date.fromordinal(d.toordinal()-1)
        return d

def filter_confirmed_bars(frame, reference_date):
    """Remove future bars. Caller must select an actual row no later than the reference date."""
    from indicators import normalize_ohlcv
    return normalize_ohlcv(frame, reference_date)

def is_exchange_session(session_date) -> bool:
    """Return whether a date is a scheduled regular XNYS session."""
    import exchange_calendars as xc
    cal = xc.get_calendar("XNYS")
    return bool(cal.is_session(session_date))
