from datetime import datetime, timezone

import requests

import monthly_company_risk as review


def test_monthly_review_prioritizes_verified_filing_and_matches_balance_sheet(monkeypatch):
    accession = "0000000001-26-000001"
    rows = {
        "filingDate": ["2026-11-28", "2026-11-26", "2026-11-05"],
        "accessionNumber": ["0000000001-26-000003", "0000000001-26-000002", accession],
        "form": ["8-K", "8-K", "10-Q"],
        "items": ["4.02", "2.04,9.01", ""],
        "reportDate": ["2026-11-28", "2026-11-26", "2026-09-30"],
    }

    def tag(amount):
        return {"units": {"USD": [
            {"end": "2026-09-30", "accn": accession, "val": amount},
            {"end": "2026-09-30", "accn": "other-filing", "val": amount * 2},
        ]}}

    class Sec:
        def _get_json(self, url, key, ttl):
            if "company_tickers_exchange" in url:
                return {"fields": ["ticker", "cik"], "data": [["TEST", 1], ["OFFLINE", 2]]}
            if "CIK0000000002" in url:
                raise requests.Timeout()
            if "/submissions/" in url:
                return {"filings": {"recent": rows}}
            return {"facts": {"us-gaap": {
                "StockholdersEquity": tag(200),
                "AssetsCurrent": tag(25),
                "LiabilitiesCurrent": tag(100),
            }}}

    monkeypatch.setattr(review, "SECFundamentalProvider", Sec)
    basket = {
        "items": [{"ticker": "TEST"}, {"ticker": "OFFLINE"}],
        "daily_risk": {"reference_date": "2026-11-25", "items": {
            "TEST": {"status": "normal", "drawdown_pct": -5},
        }},
    }
    result = review.review_monthly_companies(
        basket, datetime(2026, 11, 27, 0, 0, tzinfo=timezone.utc),
        {"TEST": {"daily_return_pct": -4, "spy_change": -1, "sector_change": -2}},
    )
    item = result["items"]["TEST"]
    assert item["status"] == "review"
    assert item["evidence"][0]["url"].endswith("0000000001-26-000002-index.htm")
    assert len(item["evidence"]) == 2
    assert "0.25배" in item["evidence"][1]["message"]
    assert "SPY 대비 -3.00%p" in item["details"][1]
    assert "인과관계는 확인되지 않았습니다" in item["details"][2]
    assert result["items"]["OFFLINE"]["status"] == "unavailable"


def test_severe_price_drop_alone_is_a_warning():
    result = review.assess_item([], True, True, {"status": "severe", "drawdown_pct": -13}, None, None)
    assert result["status"] == "watch"
    assert result["evidence"] == []
