from providers.yfinance_provider import is_us_common_equity

def test_common_us_equity_only():
    assert is_us_common_equity({"quoteType":"EQUITY","exchange":"NMS"})
    assert is_us_common_equity({"quoteType":"EQUITY","exchange":"NYQ"})
    assert not is_us_common_equity({"quoteType":"ETF","exchange":"PCX"})
    assert not is_us_common_equity({"quoteType":"EQUITY","exchange":"NSE"})
    assert not is_us_common_equity({"quoteType":"MUTUALFUND","exchange":"NMS"})
