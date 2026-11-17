from copy import deepcopy
from datetime import timedelta
from momentum.observations import build_observations
from tests.test_momentum import bars


def setup(monkeypatch):
    import momentum.observations as module
    data=bars(350)
    data.loc[:, 'Volume']=2_000_000
    end=data.index[-1]
    report={'generated_at':'frozen','period':{'end':str(end)},'selected_model':{'rules':[{'feature':'atr_pct','direction':1,'threshold':0.}, {'feature':'high20_gap','direction':-1,'threshold':0.}, {'feature':'high252_gap','direction':-1,'threshold':0.}]},'adopted_model':None}
    monkeypatch.setattr(module,'shares_facts',lambda member:[])
    return data,end,report


def test_current_all_conditions_pool_is_distinct_from_recommendations(monkeypatch):
    data,end,report=setup(monkeypatch)
    original=deepcopy(report)
    result=build_observations({'SPY':data,'A':data},[{'ticker':'A','name':'A Company','exchange':'NYSE'}],report,end)
    assert result['status']=='success'
    assert len(result['items'])==1
    item=result['items'][0]
    assert item['technical_pass_count']==item['technical_total']==3
    assert all(check['passed'] for check in item['checks'])
    assert item['market_cap_status']=='unknown'
    assert '전략 수익성·표본 검증 미통과' in item['warnings']
    assert report==original
    assert report['adopted_model'] is None
    assert 'score' not in item  # no unvalidated recommendation score
    assert [s['count'] for s in result['stages']]==[1]*7


def test_prefix_only_observations_ignore_future_bars(monkeypatch):
    data,end,report=setup(monkeypatch)
    future=bars(360)
    future.loc[future.index>end,['Open','High','Low','Close','Volume']]*=100
    future.loc[data.index]=data
    a=build_observations({'SPY':data,'A':data},[{'ticker':'A'}],report,end)
    b=build_observations({'SPY':future,'A':future},[{'ticker':'A'}],report,end)
    assert a==b


def test_funnel_is_cumulative_and_failed_rule_stops_following_counts(monkeypatch):
    data,end,report=setup(monkeypatch)
    report['selected_model']['rules'][1]['threshold']=-1
    result=build_observations({'SPY':data,'A':data},[{'ticker':'A'}],report,end)
    assert result['items']==[]
    counts=[s['count'] for s in result['stages']]
    assert counts==[1,1,1,1,0,0,0]


def test_stale_prices_and_known_small_caps_are_not_current_watch_candidates(monkeypatch):
    data,end,report=setup(monkeypatch)
    import momentum.observations as module
    result=build_observations({'SPY':data,'A':data.iloc[:-1]},[{'ticker':'A'}],report,end)
    assert result['items']==[]
    monkeypatch.setattr(module,'asof_cap',lambda records,day,close:500_000_000)
    result=build_observations({'SPY':data,'A':data},[{'ticker':'A'}],report,end)
    assert result['items']==[]
    assert result['known_small_cap_excluded']==1


def test_spy_confirmation_and_model_age_are_required(monkeypatch):
    data,end,report=setup(monkeypatch)
    result=build_observations({'SPY':data.iloc[:-1],'A':data},[{'ticker':'A'}],report,end)
    assert result['status']=='unavailable'
    assert result['items']==[]
    result=build_observations({'SPY':data,'A':data},[{'ticker':'A'}],report,end+timedelta(days=91))
    assert result['status']=='unavailable'
    assert result['items']==[]


def test_daily_shadow_run_keeps_gate_closed_and_deduplicates(monkeypatch, tmp_path):
    import json
    import sys
    import momentum.screen as screen
    data,end,report=setup(monkeypatch)
    report.update(status='not_validated',daily_universe=[{'ticker':'A'}])
    source=tmp_path/'research.json'
    source.write_text(json.dumps(report))
    output=tmp_path/'snapshot.json'
    calls=[]
    errors=[]
    def collect(*args):
        calls.append(True)
        return {'SPY':data,'A':data},errors
    monkeypatch.setattr(screen,'collect',collect)
    monkeypatch.setattr(screen,'latest_completed_session',lambda:end)
    monkeypatch.setattr(sys,'argv',['screen','--research',str(source),'--output',str(output),'--skip-unchanged'])
    screen.main()
    result=json.loads(output.read_text())
    assert result['status']=='not_validated'
    assert result['candidates']==[]
    assert len(result['observations']['items'])==1
    assert errors==[]  # recommendation diagnostics must not mutate download errors
    screen.main()
    assert len(calls)==1


def test_daily_without_selected_conditions_never_fetches_or_fabricates(monkeypatch,tmp_path):
    import json,sys
    import momentum.screen as screen
    source=tmp_path/'research.json'
    source.write_text(json.dumps({'generated_at':'frozen','adopted_model':None,'selected_model':None}))
    output=tmp_path/'snapshot.json'
    monkeypatch.setattr(sys,'argv',['screen','--research',str(source),'--output',str(output)])
    monkeypatch.setattr(screen,'collect',lambda *args: (_ for _ in ()).throw(AssertionError('unnecessary fetch')))
    screen.main()
    result=json.loads(output.read_text())
    assert result['candidates']==[]
    assert result['observations']['items']==[]
    assert result['observations']['status']=='not_applicable'
