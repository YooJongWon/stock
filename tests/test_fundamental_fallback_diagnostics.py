from fundamentals import FallbackFundamentalProvider
from providers.yahoo_fundamentals import FundamentalFallbackWithheldError


class PartialSEC:
    def get_fundamentals(self, cik, reference_date, price):
        return {
            "market_cap": 10_000_000_000,
            "pe": 20.0,
            "roe": None,
            "sales_growth_5y": 0.08,
            "fundamental_source": "SEC",
            "fundamental_quality": "LOW",
            "fundamental_status": "INCOMPLETE_FIELDS",
            "missing_fields": ["roe"],
        }


class WithheldYahoo:
    def get_fundamentals(self, ticker, reference_date, price):
        raise FundamentalFallbackWithheldError(
            "Yahoo fundamentals lack point-in-time filing dates; fallback withheld"
        )


class FailedYahoo:
    def get_fundamentals(self, ticker, reference_date, price):
        raise RuntimeError("Yahoo API timeout")


class CompleteSEC:
    def get_fundamentals(self, cik, reference_date, price):
        return {
            "market_cap": 10_000_000_000,
            "pe": 20.0,
            "roe": 0.18,
            "sales_growth_5y": 0.08,
            "fundamental_source": "SEC",
            "fundamental_quality": "HIGH",
            "fundamental_status": "AVAILABLE",
            "missing_fields": [],
        }


class MustNotCallYahoo:
    def get_fundamentals(self, ticker, reference_date, price):
        raise AssertionError("Yahoo fallback must not run when SEC has all required fields")


def test_point_in_time_guard_is_reported_as_withheld_not_failed():
    result = FallbackFundamentalProvider(
        primary=PartialSEC(),
        fallback=WithheldYahoo(),
    ).get_fundamentals("ABC", "0000000001", "2026-10-28", 100.0)

    assert result["fundamental_fallback_status"] == "WITHHELD"
    assert result["fundamental_fallback_error"].startswith("Yahoo fundamentals lack")
    assert result["fundamental_quality"] == "LOW"
    assert result["missing_fields"] == ["roe"]
    assert "withheld" in result["warning"].lower()
    assert "failed" not in result["warning"].lower()


def test_real_yahoo_error_is_reported_as_failed():
    result = FallbackFundamentalProvider(
        primary=PartialSEC(),
        fallback=FailedYahoo(),
    ).get_fundamentals("ABC", "0000000001", "2026-10-28", 100.0)

    assert result["fundamental_fallback_status"] == "FAILED"
    assert "Yahoo API timeout" in result["fundamental_fallback_error"]
    assert "fallback failed" in result["warning"].lower()


def test_complete_sec_fundamentals_skip_yahoo_fallback():
    result = FallbackFundamentalProvider(
        primary=CompleteSEC(),
        fallback=MustNotCallYahoo(),
    ).get_fundamentals("ABC", "0000000001", "2026-10-28", 100.0)

    assert result["fundamental_sec_status"] == "SUCCESS"
    assert result["fundamental_fallback_status"] == "NOT_NEEDED"
    assert result["fundamental_fallback_error"] is None
