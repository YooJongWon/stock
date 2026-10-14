from datetime import datetime, date
from zoneinfo import ZoneInfo
from market_calendar import is_exchange_session, latest_completed_session

ET=ZoneInfo("America/New_York")

def test_intraday_uses_prior_session():
    assert latest_completed_session(datetime(2024,7,8,15,30,tzinfo=ET))==date(2024,7,5)

def test_after_close_uses_current_session():
    assert latest_completed_session(datetime(2024,7,8,16,30,tzinfo=ET))==date(2024,7,8)

def test_holiday_skips_and_future_bars_removed():
    assert latest_completed_session(datetime(2024,7,5,17,0,tzinfo=ET))==date(2024,7,5)
    import pandas as pd
    from market_calendar import filter_confirmed_bars
    df=pd.DataFrame({"Open":[1,2],"High":[2,3],"Low":[.5,1],"Close":[1.5,2.5],"Volume":[10,10]},index=pd.to_datetime(["2024-07-05","2024-07-08"]))
    result=filter_confirmed_bars(df,date(2024,7,5))
    assert len(result)==1 and result.index[-1]==date(2024,7,5)

def test_xnys_holiday_is_not_a_session_and_reference_uses_previous_close():
    assert not is_exchange_session(date(2024,7,4))
    assert is_exchange_session(date(2024,7,5))
    assert latest_completed_session(datetime(2024,7,4,18,0,tzinfo=ET))==date(2024,7,3)

def test_thanksgiving_holiday_uses_early_close_session():
    assert not is_exchange_session(date(2024,11,28))
    assert latest_completed_session(datetime(2024,11,29,14,0,tzinfo=ET))==date(2024,11,29)
