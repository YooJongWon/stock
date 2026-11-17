import json
import sys
from momentum.data import current_us_universe, US_UNIVERSE_SCOPE


def test_current_exchange_universe_is_not_limited_to_200(monkeypatch):
    import momentum.data as data
    members=[{'ticker':f'A{i:03}','name':'Common stock','exchange':'NASDAQ','universe_source':'Nasdaq Trader fallback'} for i in range(301)]
    members += [{'ticker':'NY','exchange':'NYSE','universe_source':'SEC company_tickers_exchange + Nasdaq Trader'}, {'ticker':'AM','exchange':'NYSE AMERICAN','universe_source':'Nasdaq Trader fallback'}, {'ticker':'KR','exchange':'KOSDAQ','universe_source':'Nasdaq Trader fallback'}, {'ticker':'ARC','exchange':'NYSE Arca','universe_source':'Nasdaq Trader fallback'}, {'ticker':'UNVERIFIED','exchange':'NYSE','universe_source':'SEC company_tickers_exchange'}]
    monkeypatch.setattr(data,'universe',lambda:members)
    result=current_us_universe()
    assert len(result)==303
    assert {r['exchange'] for r in result}=={'NASDAQ','NYSE','NYSE American'}
    assert {'KR','ARC','UNVERIFIED'}.isdisjoint({r['ticker'] for r in result})


def test_missing_verified_directory_is_not_replaced_by_frozen_top200(monkeypatch):
    import pytest
    import momentum.data as data
    monkeypatch.setattr(data,'universe',lambda:[])
    with pytest.raises(RuntimeError,match='No verified'):
        current_us_universe()


def test_old_200_snapshot_is_migrated_and_partial_full_scan_is_deduplicated(monkeypatch,tmp_path):
    import momentum.screen as screen
    from tests.test_momentum import bars
    prices=bars(350)
    end=prices.index[-1]
    report={'generated_at':'frozen','period':{'end':str(end)},'status':'not_validated','adopted_model':None,'selected_model':{'rules':[{'feature':'atr_pct'}]},'daily_universe':[{'ticker':'OLD'}]}
    source=tmp_path/'research.json'; source.write_text(json.dumps(report))
    output=tmp_path/'snapshot.json'
    output.write_text(json.dumps({'data_date':str(end),'research_generated_at':'frozen','status':'not_validated','observations':{'version':1,'status':'success'}}))
    members=[{'ticker':f'A{i:03}','exchange':'NASDAQ'} for i in range(301)]
    seen=[]
    def collect(rows,*args):
        seen.append(len(rows))
        return {'SPY':prices},[{'ticker':'A000','error':'missing price'}]
    monkeypatch.setattr(screen,'latest_completed_session',lambda:end)
    monkeypatch.setattr(screen,'current_us_universe',lambda:members)
    monkeypatch.setattr(screen,'collect',collect)
    monkeypatch.setattr(screen,'build_observations',lambda *args:{'version':1,'status':'degraded','stages':[{'key':'data','count':200}],'items':[]})
    monkeypatch.setattr(sys,'argv',['screen','--research',str(source),'--output',str(output),'--skip-unchanged'])
    screen.main()
    result=json.loads(output.read_text())
    assert seen==[301]
    assert result['universe_count']==301
    assert result['universe_scope']['id']==US_UNIVERSE_SCOPE
    assert result['universe_scope']['limited'] is False
    assert result['candidates']==[]
    assert result['status']=='degraded'
    assert result['scan_complete'] is True
    screen.main()
    assert seen==[301]


def test_full_scan_reuses_sec_transport_and_rate_limiter(monkeypatch):
    import momentum.data as data
    made=[]; requests=[]
    class Provider:
        def __init__(self): made.append(self)
        def _get_json(self,url,key,ttl): requests.append((id(self),url)); return {'facts':{}}
        def _records(self,*args): return []
    data._shares_provider.cache_clear()
    monkeypatch.setattr(data,'SECFundamentalProvider',Provider)
    try:
        assert data.shares_facts({'cik':'1'})==[]
        assert data.shares_facts({'cik':'2'})==[]
        assert len(made)==1
        assert len(requests)==2
        assert requests[0][0]==requests[1][0]
    finally:
        data._shares_provider.cache_clear()
