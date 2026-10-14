import pandas as pd
from providers.fallback_provider import FallbackMarketDataProvider

class Good:
    def history(self,*a): return pd.DataFrame({"Close":[1]})
class Bad:
    def history(self,*a): raise RuntimeError("offline")

def test_yfinance_success():
    result=FallbackMarketDataProvider(Good(),Bad()).history("ABC","2026-01-01")
    assert result.source=="yfinance" and result.error is None

def test_fallback_and_total_failure():
    result=FallbackMarketDataProvider(Bad(),Good()).history("ABC","2026-01-01")
    assert result.source=="stooq_fallback" and "offline" in result.error
    failed=FallbackMarketDataProvider(Bad(),Bad()).history("ABC","2026-01-01")
    assert failed.frame is None and "stooq" in failed.error
