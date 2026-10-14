from scoring import score_snapshot, classify

def candidate():
    t={"price":50,"average_volume":2e6,"average_dollar_volume":100e6,"rsi14":62,"trend_stack":True,"sma50_rising":True,
       "relative_strength":4,"pullback_recent":True,"volume_dryup_recent":True,"volume_expansion":True,
       "strong_bull_candle":True,"distance_from_50_atr":1,"atr_stop_pct":3,"atr_stop_price":48.5,"one_r":1.5,
       "two_r_target":53,"ema10":51,"sma50":48,"sma200":42,"atr14":1,"market_regime":"BULL","reference_date":"2026-01-01"}
    f={"market_cap":3e9,"pe":20,"roe":.2,"sales_growth_5y":.1,"fundamental_quality":"HIGH","fundamental_source":"SEC"}
    return t,f

def test_strategy_score_max_ten():
    t,_=candidate()
    assert score_snapshot(t)==10
    t["relative_strength"]=-1; t["volume_expansion"]=False
    assert score_snapshot(t)==7

def test_buy_requires_all_fundamental_and_technical_hard_filters():
    t,f=candidate()
    assert classify("ABC",t,f)["Final"]=="BUY"
    f["pe"]=40
    row=classify("ABC",t,f)
    assert row["Final"]=="REJECT" and "PE < 40" in row["Fail Reason"]

def test_atr_over_five_percent_cannot_be_buy():
    t,f=candidate(); t["atr_stop_pct"]=5.01
    assert classify("ABC",t,f)["Final"]=="REJECT"

def test_risk_off_blocks_buy():
    t,f=candidate(); t["market_regime"]="RISK_OFF"
    assert classify("ABC",t,f)["Final"]=="WATCH"

def test_watch_only_when_core_filters_pass_and_timing_is_missing():
    t,f=candidate(); t["rsi14"]=53
    row=classify("ABC",t,f)
    assert row["Final"]=="WATCH" and "RSI >= 55" in row["Fail Reason"]
    f["roe"]=.10
    assert classify("ABC",t,f)["Final"]=="REJECT"
