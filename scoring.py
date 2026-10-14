"""Scoring and final quantitative BUY/WATCH/REJECT decisions."""
from __future__ import annotations
import json
from config import SETTINGS


def score_snapshot(t: dict) -> int:
    rsi = t.get("rsi14")
    return (2*bool(t.get("trend_stack")) + int(bool(t.get("sma50_rising"))) +
            2*int((t.get("relative_strength") or 0) > 0) +
            2*int(bool(t.get("pullback_recent"))) + int(bool(t.get("strong_bull_candle"))) +
            int(bool(t.get("volume_expansion"))) + int(rsi is not None and 55 <= rsi < 68))


def classify(ticker: str, technical: dict, fundamental: dict | None, meta: dict | None = None, settings=SETTINGS) -> dict:
    meta, f = meta or {}, fundamental or {}
    price = technical.get("price")
    checks = {
        "Price >= $10": price is not None and price >= settings.price_min,
        "Market Cap >= $2B": f.get("market_cap") is not None and f["market_cap"] >= settings.market_cap_min,
        "PE > 0": f.get("pe") is not None and f["pe"] > settings.pe_min,
        "PE < 40": f.get("pe") is not None and f["pe"] < settings.pe_max,
        "ROE > 15%": f.get("roe") is not None and f["roe"] > settings.roe_min,
        "Sales Growth 5Y > 5%": f.get("sales_growth_5y") is not None and f["sales_growth_5y"] > settings.sales_growth_5y_min,
        "Average Volume >= 1M": technical.get("average_volume") is not None and technical["average_volume"] >= settings.avg_volume_min,
        "Average Dollar Volume >= $30M": technical.get("average_dollar_volume") is not None and technical["average_dollar_volume"] >= settings.avg_dollar_volume_min,
        "Market Regime BULL": technical.get("market_regime") == "BULL",
        "Trend Stack EMA20 > SMA50 > SMA200": bool(technical.get("trend_stack")),
        "SMA50 Rising": bool(technical.get("sma50_rising")),
        "Relative Strength > 0": technical.get("relative_strength") is not None and technical["relative_strength"] > 0,
        "RSI >= 55": technical.get("rsi14") is not None and technical["rsi14"] >= 55,
        "RSI < 68": technical.get("rsi14") is not None and technical["rsi14"] < 68,
        "Recent 50MA Pullback": bool(technical.get("pullback_recent")),
        "Recent Volume Dry-up": bool(technical.get("volume_dryup_recent")),
        "Volume Expansion": bool(technical.get("volume_expansion")),
        "Strong Bull Candle": bool(technical.get("strong_bull_candle")),
        "50MA Distance 0..2 ATR": technical.get("distance_from_50_atr") is not None and 0 <= technical["distance_from_50_atr"] <= 2,
        "ATR Stop <= 5%": technical.get("atr_stop_pct") is not None and technical["atr_stop_pct"] <= settings.max_stop_loss_pct,
    }
    score = score_snapshot(technical)
    checks["Score >= 7"] = score >= settings.score_min
    required = ("market_cap", "pe", "roe", "sales_growth_5y")
    fundamental_ok = bool(f) and f.get("fundamental_quality") != "UNAVAILABLE" and all(f.get(k) is not None for k in required)
    failed = [name for name, passed in checks.items() if not passed]
    if not fundamental_ok:
        failed.insert(1, "Fundamental data unavailable")
    buy = fundamental_ok and all(checks.values())
    core_keys=("Price >= $10","Market Cap >= $2B","PE > 0","PE < 40","ROE > 15%","Sales Growth 5Y > 5%",
               "Average Volume >= 1M","Average Dollar Volume >= $30M","Trend Stack EMA20 > SMA50 > SMA200",
               "SMA50 Rising","Relative Strength > 0")
    timing_keys={"Market Regime BULL","RSI >= 55","RSI < 68","Recent 50MA Pullback","Recent Volume Dry-up",
                 "Volume Expansion","Strong Bull Candle","50MA Distance 0..2 ATR","Score >= 7"}
    watch = (not buy and fundamental_ok and score >= settings.watch_score_min and
             all(checks[key] for key in core_keys) and
             all(passed or key in timing_keys for key,passed in checks.items()))
    final = "BUY" if buy else "WATCH" if watch else "REJECT"
    entry = price
    initial_stop = technical.get("atr_stop_price")
    one_r = technical.get("one_r")
    return {
        "Ticker":ticker,"Company Name":meta.get("name"),"Exchange":meta.get("exchange"),"Data Source":meta.get("data_source"),
        "Fundamental Source":f.get("fundamental_source"),"Fundamental Quality":f.get("fundamental_quality","UNAVAILABLE"),
        "Fundamental Period Start":f.get("period_start"),"Fundamental Period End":f.get("period_end"),"Fundamental Filing Date":f.get("filing_date"),
        "Fundamental Form":f.get("form"),"Fundamental Basis":f.get("fundamental_basis"),"Fundamental Source Detail":f.get("source_detail"),
        "Market Cap Source":f.get("market_cap_source"),"Reference Date":technical.get("reference_date"),"Price":price,
        "Market Cap":f.get("market_cap"),"PE":f.get("pe"),"ROE":f.get("roe"),"Sales Growth 5Y":f.get("sales_growth_5y"),
        "Average Volume":technical.get("average_volume"),"Average Dollar Volume":technical.get("average_dollar_volume"),
        "RSI14":technical.get("rsi14"),"EMA10":technical.get("ema10"),"EMA20":technical.get("ema20"),"SMA50":technical.get("sma50"),"SMA200":technical.get("sma200"),
        "ATR14":technical.get("atr14"),"ROC63":technical.get("roc63"),"SPY ROC63":technical.get("spy_roc63"),"Relative Strength":technical.get("relative_strength"),
        "Market Regime":technical.get("market_regime"),"50MA Distance ATR":technical.get("distance_from_50_atr"),
        "Pullback Recent":technical.get("pullback_recent"),"Volume Dry-up Recent":technical.get("volume_dryup_recent"),
        "Volume Expansion":technical.get("volume_expansion"),"Strong Bull Candle":technical.get("strong_bull_candle"),
        "Trend Stack":technical.get("trend_stack"),"SMA50 Rising":technical.get("sma50_rising"),"ATR Stop Price":initial_stop,
        "ATR Stop %":technical.get("atr_stop_pct"),"Entry Plan":entry,"Initial Stop":initial_stop,"1R":one_r,
        "2R Target":technical.get("two_r_target"),"Entry Plan Rule":"Next trading day open; displayed prices use signal close as estimate",
        "Break-even Trigger":(entry+one_r if entry is not None and one_r is not None else None),
        "Trailing Start":(entry+1.5*one_r if entry is not None and one_r is not None else None),
        "Trailing Stop Formula":"EMA10 - 0.5*ATR14","Max Holding Days":settings.max_holding_days,
        "Score":score,"BUY Checks Passed":sum(checks.values()),"Final":final,"Fail Reason":"; ".join(failed),
        # These are the same booleans used above to classify BUY/WATCH/REJECT.
        # The cloud JSON exposes them without reimplementing or changing strategy rules.
        "Filter Results":json.dumps(checks,ensure_ascii=False),
    }
