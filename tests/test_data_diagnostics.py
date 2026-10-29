from screener import _price_failure_category


def test_yahoo_rate_limit_is_categorized():
    message = "yfinance: RuntimeError: YFRateLimitError too many requests"
    assert _price_failure_category(message) == "yahoo_rate_limit"


def test_empty_yahoo_history_is_categorized_as_empty_history():
    message = "yfinance: RuntimeError: Yahoo Finance returned an empty daily-history frame"
    assert _price_failure_category(message) == "empty_price_history"


def test_stale_price_is_categorized_separately():
    message = "yfinance: ValueError: stale daily close: expected 2026-10-28, received 2026-10-27"
    assert _price_failure_category(message) == "stale_or_unconfirmed_close"


def test_network_timeouts_are_categorized():
    message = "yfinance: TimeoutError: connection timed out"
    assert _price_failure_category(message) == "network_timeout_or_connection"


def test_nonpositive_price_is_reported_as_invalid_price_data():
    message = "yfinance: RuntimeError: yfinance failed: ValueError: nonpositive price"
    assert _price_failure_category(message) == "invalid_price_data"
