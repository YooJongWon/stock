from screener import _price_failure_category


def test_yahoo_rate_limit_is_not_hidden_by_missing_stooq_key():
    message = (
        "yfinance: RuntimeError: yfinance failed: YFRateLimitError too many requests; "
        "stooq: not attempted (STOOQ_API_KEY is not configured)"
    )
    assert _price_failure_category(message) == "yahoo_rate_limit"


def test_empty_yahoo_history_is_categorized_as_empty_history():
    message = (
        "yfinance: RuntimeError: yfinance failed: Yahoo Finance returned an empty daily-history frame; "
        "stooq: not attempted (STOOQ_API_KEY is not configured)"
    )
    assert _price_failure_category(message) == "empty_price_history"


def test_stooq_authorization_error_is_visible_when_primary_error_is_generic():
    message = "yfinance: RuntimeError: symbol data unavailable; stooq: HTTPError 403 access denied"
    assert _price_failure_category(message) == "fallback_provider_unavailable"
