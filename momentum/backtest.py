"""Next-open execution, conservative daily-bar fills and cash-constrained portfolio."""
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Costs:
    slippage: float = .001
    fee: float = .0005


def trade(bars, signal_date, horizon=20, costs=Costs()):
    """None means censored, never a negative training label. Horizon includes entry day."""
    pos = bars.index.get_loc(signal_date) + 1
    if pos + horizon > len(bars):
        return None
    window = bars.iloc[pos:pos + horizon]
    entry = float(window.Open.iloc[0]) * (1 + costs.slippage)
    stop, target = entry * .95, entry * 1.10
    for day, bar in window.iterrows():
        # Open gaps have a known order; only unknown intraday ordering is stop-first.
        if bar.Open <= stop:
            price, reason = float(bar.Open), "stop"
        elif bar.Open >= target:
            price, reason = float(bar.Open), "target"
        elif bar.Low <= stop:
            price, reason = stop, "stop"
        elif bar.High >= target:
            price, reason = target, "target"
        else:
            continue
        break
    else:
        day, price, reason = window.index[-1], float(window.Close.iloc[-1]), "timeout"
    exit_price = price * (1 - costs.slippage)
    net = exit_price * (1 - costs.fee) / (entry * (1 + costs.fee)) - 1
    return {"signal_date": str(signal_date), "entry_date": str(window.index[0]), "exit_date": str(day), "entry": entry, "exit": exit_price, "return": net, "reason": reason, "horizon": horizon}


def metrics(trades, equity=None):
    if not trades:
        return {"trades": 0, **{k: None for k in ("target_rate", "stop_rate", "win_rate", "mean_return", "profit_factor", "max_drawdown", "expectancy")}}
    r = np.array([t["return"] for t in trades])
    loss = -r[r < 0].sum()
    curve = np.array(equity if equity is not None else np.cumprod(1 + r), dtype=float)
    curve = np.r_[1., curve]
    return {"trades": len(trades), "target_rate": sum(t["reason"] == "target" for t in trades) / len(trades), "stop_rate": sum(t["reason"] == "stop" for t in trades) / len(trades), "win_rate": float((r > 0).mean()), "mean_return": float(r.mean()), "profit_factor": float(r[r > 0].sum() / loss) if loss else None, "max_drawdown": float((curve / np.maximum.accumulate(curve) - 1).min()), "expectancy": float(r.mean())}


def portfolio(signals, prices, calendar, max_positions=5, costs=Costs()):
    """Equal fixed 1/N capital slots; no leverage, duplicate ticker or exit-day reuse.

    Mark positions to daily close for drawdown. No forward outcome selects entries.
    """
    cash, active, completed, curve = 1., [], [], []
    by_day = {str(day): group.sort_values(["score", "ticker"], ascending=[False, True]) for day, group in signals.groupby("date")}
    for day in calendar:
        key = str(day)
        # Orders selected yesterday fill today before today's exits free capital.
        pending = by_day.get(str(calendar[calendar.get_loc(day) - 1])) if calendar.get_loc(day) else None
        if pending is not None:
            for _, signal in pending.iterrows():
                ticker = signal.ticker
                if len(active) >= max_positions or any(t["ticker"] == ticker for t in active) or cash < 1 / max_positions - 1e-10:
                    continue
                result = trade(prices[ticker], signal.date, costs=costs)
                if result is None or result["entry_date"] != key:
                    continue
                allocation = 1 / max_positions
                cash -= allocation
                active.append({**result, "ticker": ticker, "allocation": allocation})
        remaining = []
        for t in active:
            if t["exit_date"] == key:
                cash += t["allocation"] * (1 + t["return"])
                completed.append(t)
            else:
                remaining.append(t)
        active = remaining
        value = cash
        for t in active:
            bars = prices[t["ticker"]]
            close = float(bars.loc[bars.index <= day].Close.iloc[-1])
            value += t["allocation"] * close * (1 - costs.slippage) * (1 - costs.fee) / (t["entry"] * (1 + costs.fee))
        curve.append(value)
    # Caller purges signals whose complete 20-session horizon lies outside calendar.
    return {"metrics": metrics(completed, curve), "trades": completed, "equity": [{"date": str(d), "value": v} for d, v in zip(calendar, curve)]}


def label_outcomes(bars, horizon=20, costs=Costs()):
    """Vectorized barrier labels, exactly matching trade() ordering and censoring.

    Codes: -1 censored, 0 timeout, 1 stop, 2 target. Research only, never features.
    """
    n = len(bars)
    outcome = np.zeros(n, dtype=np.int8)
    alive = np.ones(n, dtype=bool)
    entry = bars.Open.shift(-1).to_numpy() * (1 + costs.slippage)
    stop, target = entry * .95, entry * 1.10
    for k in range(1, horizon + 1):
        opened = bars.Open.shift(-k).to_numpy()
        low = bars.Low.shift(-k).to_numpy()
        high = bars.High.shift(-k).to_numpy()
        stop_gap = opened <= stop
        target_gap = opened >= target
        hit_stop = stop_gap | (~target_gap & (low <= stop))
        hit_target = ~stop_gap & (target_gap | ((low > stop) & (high >= target)))
        outcome[alive & hit_stop] = 1
        outcome[alive & hit_target] = 2
        alive &= ~(hit_stop | hit_target)
    outcome[max(0, n-horizon):] = -1
    return pd.Series(outcome, index=bars.index)
