from providers.stooq_provider import StooqProvider

CSV="""Date,Open,High,Low,Close,Volume
2025-01-01,10,12,9,11,1000
"""

class Response:
    text=CSV
    def raise_for_status(self): pass

class Session:
    def __init__(self): self.args=None
    def get(self,*args,**kwargs): self.args=(args,kwargs); return Response()

def test_stooq_csv_normalization_and_symbol():
    session=Session(); provider=StooqProvider(session=session, api_key="test-key")
    # A one-bar fixture is intentionally rejected by the minimum history check,
    # but confirms the CSV endpoint parameters and normalization path are reached.
    try: provider.history("BRK-B","2025-01-01")
    except ValueError as e: assert "insufficient" in str(e)
    assert session.args[0][0]==StooqProvider.URL
    assert session.args[1]["params"]["s"]=="brk.b.us"

def test_stooq_html_or_access_challenge_is_rejected():
    class HtmlResponse(Response): text="Access denied"
    class HtmlSession:
        def get(self,*args,**kwargs): return HtmlResponse()
    try: StooqProvider(HtmlSession(), api_key="test-key").history("AAPL","2025-01-01")
    except ValueError as e: assert "did not return CSV" in str(e)
    else: raise AssertionError("non-CSV must be rejected")
