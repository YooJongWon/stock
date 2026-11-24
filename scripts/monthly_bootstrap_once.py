from datetime import date
import json
from pathlib import Path

import pandas as pd

from data_provider import UniverseProvider
from monthly_momentum import MonthlyMomentum

cache = Path("work/momentum/daily-prices")
members = UniverseProvider().get()
scan = MonthlyMomentum(date(2026, 10, 30))
parsed = 0
for member in members:
    ticker = member["ticker"]
    if "/" in ticker or "\\" in ticker:
        continue
    path = cache / (ticker + ".csv")
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        if "Adj Close" not in frame or frame["Adj Close"].isna().all():
            continue
        ratio = frame["Adj Close"] / frame["Close"]
        for column in ("Open", "High", "Low", "Close"):
            frame[column] = frame[column] * ratio
        scan.observe(member, frame)
        parsed += 1
    except (OSError, KeyError, ValueError):
        continue
result = scan.result()
if not result or len(result["items"]) != 10:
    raise SystemExit(f"Insufficient cached data: {parsed}/{len(members)} price histories")
result["source"] = "existing_momentum_price_cache"
result["universe_count"] = len(members)
result["price_histories_read"] = parsed
Path("monthly-momentum-initial.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False))
