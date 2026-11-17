from datetime import date, timedelta
import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from momentum.features import features, FEATURES
from momentum.backtest import trade, portfolio, metrics, Costs
from momentum.model import fit, score
from momentum.data import asof_cap, write_json
from momentum.screen import build_candidates


def bars(n=350):
    dates = pd.bdate_range('2025-01-01', periods=n).date
    close = 100 + np.arange(n) * .03 + np.sin(np.arange(n))
    return pd.DataFrame({'Open': close, 'High': close+1, 'Low': close-1, 'Close': close, 'Volume': 1_000_000}, index=dates)


def test_features_are_prefix_invariant_and_future_mutations_do_not_leak():
    original = bars()
    cutoff = original.index[299]
    expected = features(original.iloc[:300], original.iloc[:300])
    mutated = original.copy()
    mutated.loc[mutated.index > cutoff, ['Open','High','Low','Close','Volume']] *= 100
    actual = features(mutated, mutated).loc[:cutoff]
    assert_frame_equal(expected, actual)
    assert set(FEATURES) <= set(actual)


def test_rvol_excludes_today_from_reference_volume():
    data = bars()
    data.iloc[-1, data.columns.get_loc('Volume')] = 10_000_000
    assert features(data, data).rvol.iloc[-1] == 10


def test_next_open_and_ambiguous_bar_stop_first():
    data = bars(25)
    signal = data.index[0]
    data.loc[data.index[1], ['Open','High','Low','Close']] = [200,230,180,210]
    result = trade(data, signal)
    assert result['entry'] == pytest.approx(200.2)
    assert result['reason'] == 'stop'
    assert result['return'] < -.05
    assert result['entry_date'] == str(data.index[1])


def test_open_gap_stop_fills_at_open_and_target_gap_before_intraday_stop():
    data = bars(25)
    data.loc[:, ['Open','High','Low','Close']] = [100,101,99,100]
    data.loc[data.index[2], ['Open','High','Low','Close']] = [85,100,80,90]
    result = trade(data, data.index[0])
    assert result['exit'] == pytest.approx(85*.999)
    assert result['reason'] == 'stop'
    data.loc[data.index[2], ['Open','High','Low','Close']] = [115,120,80,90]
    assert trade(data, data.index[0])['reason'] == 'target'


def test_horizon_censoring_not_failure_and_timeout_costs():
    data = bars(25)
    assert trade(data, data.index[-5], 5) is None
    result = trade(data, data.index[0])
    assert result['reason'] == 'timeout'
    assert result['exit_date'] == str(data.index[20])
    assert result['return'] < data.Close.iloc[20] / data.Open.iloc[1] - 1


def test_five_ten_twenty_labels_and_stop_precedes_target():
    data = bars(30)
    data.loc[:, ['Open','High','Low','Close']] = [100,101,99,100]
    data.loc[data.index[8], 'High'] = 112
    assert trade(data, data.index[0], 5)['reason'] == 'timeout'
    assert trade(data, data.index[0], 10)['reason'] == 'target'
    assert trade(data, data.index[0], 20)['reason'] == 'target'
    data.loc[data.index[3], 'Low'] = 90
    assert trade(data, data.index[0], 20)['reason'] == 'stop'


def test_portfolio_capacity_duplicates_and_daily_drawdown():
    data = bars(50)
    data.loc[:, ['Open','High','Low','Close']] = [100,101,99,100]
    # Large temporary mark-to-market drawdown followed by recovery, no intraday stop hit.
    data.loc[data.index[4], ['Open','High','Low','Close']] = [96,100,95.2,96]
    rows = [{'date': d, 'ticker': ticker, 'score': 100-i} for d in data.index[:5] for i,ticker in enumerate(['A','B','C'])]
    result = portfolio(pd.DataFrame(rows), {t:data for t in ['A','B','C']}, data.index, max_positions=2)
    assert len(result['trades']) == 2
    assert {t['ticker'] for t in result['trades']} == {'A','B'}
    assert result['metrics']['max_drawdown'] < -.035
    assert all(t['entry_date'] == str(data.index[1]) for t in result['trades'])


def test_point_in_time_market_cap_filters_future_filings_and_stale_facts():
    d = date(2026,1,15)
    facts = [{'filed': d-timedelta(days=1), 'end': d-timedelta(days=30), 'val': 10}, {'filed': d, 'end': d, 'val': 1000}, {'filed': d+timedelta(days=1), 'end': d, 'val': 10000}]
    assert asof_cap(facts, d, 100) == 1000
    assert asof_cap(facts, d+timedelta(days=200), 100) is None


def test_model_is_train_only_frozen_and_refuses_tiny_samples():
    data = features(bars(), bars()).dropna()
    data['ticker'] = ['T'+str(i%30) for i in range(len(data))]
    data['success'] = np.arange(len(data)) % 2 == 0
    assert fit(data) is None
    train = pd.concat([data]*3, ignore_index=True)
    rules = fit(train)
    assert rules
    before = score(data, rules).copy()
    validation = data.copy()
    validation['success'] = ~validation.success
    assert_frame_equal(pd.DataFrame(before), pd.DataFrame(score(validation, rules)))


def test_unvalidated_research_never_publishes_candidates():
    rows, diagnostics = build_candidates({}, [], {'status':'not_validated', 'adopted_model':None}, date(2026,11,16))
    assert rows == []
    assert diagnostics
    assert metrics([])['target_rate'] is None


def test_json_never_serializes_nan_or_fictional_metrics(tmp_path):
    path = tmp_path/'report.json'
    write_json(path, {'metrics': metrics([]), 'missing': float('nan')})
    contents = path.read_text()
    assert 'NaN' not in contents
    assert '"target_rate": null' in contents


def test_training_labels_purged_and_snapshot_dates_precede_entry(monkeypatch):
    from momentum.research import observations
    import momentum.research as research
    data = bars(350)
    # Liquid, enough history; deterministic no-target observations remain valid failures.
    monkeypatch.setattr(research, 'shares_facts', lambda member: [])
    split = data.index[310]
    frame, snapshots = observations({'SPY': data, 'A': data}, [{'ticker':'A'}], data.index[260], data.index[-1], split, [])
    assert not frame.empty
    train = frame[frame.partition == 'train']
    assert (pd.to_datetime(train.label_end).dt.date < split).all()
    assert set(frame.partition) == {'train','validation'}
    assert (pd.to_datetime(snapshots.feature_date) < pd.to_datetime(snapshots.entry_date)).all()
    assert set(snapshots.lag) == {1,3,5,10}
    assert set(snapshots.horizon) == {5,10,20}
    # No observation for the last 20 sessions, including early target outcomes.
    assert frame.date.max() == data.index[-21]


def test_research_end_must_precede_live_screen_date():
    report = {'status':'validated_exploratory', 'adopted_model':{'rules':[]}, 'period':{'end':'2026-11-16'}}
    rows, diagnostics = build_candidates({}, [], report, date(2026,11,16))
    assert rows == []
    assert '이후' in diagnostics[0]['error']


def test_vectorized_labels_match_execution_for_every_horizon_and_signal():
    from momentum.backtest import label_outcomes
    data = bars(100)
    rng = np.random.default_rng(20261117)
    base = np.cumprod(1 + rng.normal(0,.03,100)) * 100
    data['Open'] = base
    data['Close'] = base * (1 + rng.uniform(-.01,.01,100))
    data['High'] = data[['Open','Close']].max(axis=1) * (1+rng.uniform(0,.12,100))
    data['Low'] = data[['Open','Close']].min(axis=1) * (1-rng.uniform(0,.08,100))
    for horizon in (5,10,20):
        labels = label_outcomes(data, horizon)
        for d in data.index:
            result = trade(data,d,horizon)
            expected = -1 if result is None else {'timeout':0,'stop':1,'target':2}[result['reason']]
            assert labels.loc[d] == expected


def test_collector_rejects_split_and_stale_data_and_deduplicates_failures(tmp_path, monkeypatch):
    import momentum.data as data_module
    data = bars(300)
    end = data.index[-1]
    spy = data.copy()
    split = data.copy()
    split['Stock Splits'] = 0.
    split.iloc[270, split.columns.get_loc('Stock Splits')] = 2.
    calls = []
    def download(symbols, **kwargs):
        calls.append(symbols)
        return pd.concat({'SPY':spy, 'SPLIT':split, 'STALE':data.iloc[:-1]}, axis=1)
    monkeypatch.setattr(data_module.yf,'download',download)
    monkeypatch.setattr(data_module.yf,'set_tz_cache_location',lambda path:None)
    members = [{'ticker':'SPLIT'},{'ticker':'STALE'}]
    prices, errors = data_module.collect(members, data.index[0], end, tmp_path)
    assert set(prices) == {'SPY'}
    assert len(errors) == 2
    assert any('split' in e['error'] for e in errors)
    assert any('stale' in e['error'] for e in errors)
    again, same_errors = data_module.collect(members,data.index[0],end,tmp_path)
    assert set(again) == {'SPY'}
    assert same_errors == errors
    assert len(calls) == 1


def test_single_slot_spy_benchmark_reinvests_after_first_loss():
    data = bars(70)
    data.loc[:, ['Open','High','Low','Close']] = [100,101,99,100]
    signals = pd.DataFrame({'date':data.index[:50], 'ticker':'SPY', 'score':100.})
    result = portfolio(signals,{'SPY':data},data.index,max_positions=1)
    assert len(result['trades']) == 3
    assert result['trades'][0]['return'] < 0  # round trip costs, not an inability to buy again
    assert result['trades'][1]['allocation'] < 1


def test_missing_vendor_session_is_not_counted_as_an_extra_holding_day():
    from momentum.features import session_windows
    spy = bars(600)
    missing = spy.index[300]
    stock = spy.drop(missing)
    past, future = session_windows(stock,spy)
    assert past.loc[spy.index[299]]
    assert not past.loc[spy.index[301]]
    assert past.loc[spy.index[553]]
    assert future.loc[spy.index[279]]
    assert not future.loc[spy.index[280]]  # would otherwise stretch 20 bars over 21 sessions
    assert not future.iloc[-1]
    # The past mask is invariant to future gaps/outcomes.
    cutoff = spy.index[299]
    assert past.loc[:cutoff].equals(session_windows(stock.loc[:cutoff],spy.loc[:cutoff])[0])


def test_frozen_model_json_retains_full_float_precision(tmp_path):
    import json
    precise = .03412737297656643
    path=tmp_path/'model.json'
    write_json(path, {'model':{'threshold':precise},'numpy':np.float64(precise)})
    restored=json.loads(path.read_text())
    assert restored['model']['threshold'] == precise
    assert restored['numpy'] == precise


def test_failed_momentum_run_clears_candidates_without_touching_swing_result(tmp_path):
    import json
    from scripts.write_momentum_failure import record_failure
    legacy = tmp_path/'latest-results.json'
    legacy.write_text('{"status":"success","buy_count":3}')
    before=legacy.read_bytes()
    snapshot=tmp_path/'latest-momentum.json'
    snapshot.write_text('{"status":"success","candidates":[{"ticker":"OLD"}]}')
    research=tmp_path/'research.json'
    research.write_text('{"generated_at":"frozen"}')
    record_failure(snapshot,research)
    result=json.loads(snapshot.read_text())
    assert result['status']=='failed'
    assert result['candidates']==[]
    assert result['research_generated_at']=='frozen'
    assert legacy.read_bytes()==before


def test_published_trade_popup_uses_only_actual_validation_and_display_metadata():
    from copy import deepcopy
    from scripts.publish_momentum_research import trade_snapshot
    trade = {'ticker':'ABC','entry_date':'2026-07-02','return':-.05,'reason':'stop'}
    unknown = {'ticker':'XYZ','entry_date':'2026-07-03','return':.09,'reason':'target'}
    report = {'generated_at':'frozen', 'adopted_model':None, 'validation':{'trades':[trade,unknown]},'baselines':{'simple_momentum':{'trades':[{'ticker':'OTHER'}]}}}
    original = deepcopy(report)
    snapshot = trade_snapshot(report,[{'ticker':'ABC','name':'ABC Corporation','exchange':'NYSE'}])
    assert snapshot['research_generated_at']=='frozen'
    assert [t['ticker'] for t in snapshot['trades']]==['ABC','XYZ']
    assert snapshot['trades'][0]['company_name']=='ABC Corporation'
    assert snapshot['trades'][0]['return']==trade['return']
    assert snapshot['trades'][1]['company_name']=='XYZ'
    assert snapshot['trades'][1]['exchange'] is None
    assert report==original
