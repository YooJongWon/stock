"""Manual full-universe research; chronological split, purging, frozen validation."""
import argparse
from datetime import date, datetime, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
from momentum.data import universe, collect, shares_facts, asof_cap, write_json
from momentum.features import features, FEATURES
from momentum.backtest import trade, portfolio, Costs, label_outcomes
from momentum.model import fit, candidates, score, uncertainty

LIMITATIONS = [
    '현재 상장 디렉터리로 구성: 생존자 편향. 상장폐지·합병 소멸 종목 미포함.',
    '무료 Yahoo 일봉: intraday 경로·호가·거래정지 체결 검증 불가. 동일 봉 충돌은 손절 우선.',
    '분할 발생 종목은 엔진 지원 전까지 제외: 기업행동 선택 편향. 현금배당 재투자 미반영.',
    '공시시점 시가총액 미확인 종목은 별도 unknown 그룹. 현재 시총·섹터 소급 대입 금지.',
    '시점별 섹터 이력 미확보: unknown으로 표시. 섹터별 유효성 미검증.',
    '여러 조건 탐색 및 시장 내 상관관계로 과최적화 가능. 단일 검증 구간은 성과 보장이 아님.',
    'Wilson 구간은 기술통계: 종목·기간 간 의존성을 교정한 통계적 유의성 검정이 아님.',
]


def observations(prices, members, start, end, split, metadata_errors):
    frames, snapshot_frames = [], []
    spy = prices['SPY']
    for number, member in enumerate(members):
        ticker = member['ticker']
        if ticker not in prices:
            continue
        bars = prices[ticker]
        f = features(bars, spy)
        try:
            records = shares_facts(member)
        except Exception as exc:
            records = []
            metadata_errors.append({'ticker': ticker, 'error': str(exc)})
        f['market_cap'] = [asof_cap(records, d, c) for d, c in zip(f.index, f.close)]
        last_label = pd.Series(bars.index, index=bars.index).shift(-20)
        mature = last_label.notna()
        eligible = (f.index >= start) & (f.index <= end) & f[FEATURES].notna().all(axis=1) & (f.close >= 10) & (f.dollar_volume30 >= 20_000_000) & (f.market_cap.isna() | (f.market_cap >= 1_000_000_000)) & mature
        # Full-horizon purge even when target/stop occurs early.
        eligible &= (f.index >= split) | (last_label.fillna(end) < split)
        positions = np.flatnonzero(eligible)
        if not len(positions):
            continue
        labels = {h: label_outcomes(bars, h) for h in (5,10,20)}
        selected = f.iloc[positions].copy()
        selected['ticker'], selected['sector'] = ticker, 'unknown'
        selected['date'] = selected.index
        selected['cap_group'] = np.where(selected.market_cap.notna(), 'gte_1bn', 'unknown')
        selected['success'] = labels[20].iloc[positions].to_numpy() == 2
        selected['partition'] = np.where(selected.index < split, 'train', 'validation')
        selected['label_end'] = last_label.iloc[positions].astype(str).to_numpy()
        frames.append(selected.reset_index(drop=True))
        for horizon in (5,10,20):
            codes = labels[horizon].iloc[positions].to_numpy()
            for lag in (1,3,5,10):
                before = f.iloc[positions + 1 - lag][FEATURES + ['ema20', 'sma50', 'sma200', 'market_cap']].copy()
                before['ticker'], before['sector'] = ticker, 'unknown'
                before['feature_date'] = before.index.astype(str)
                before['entry_date'] = bars.index[positions + 1].astype(str)
                before['lag'], before['horizon'] = lag, horizon
                before['success'] = codes == 2
                before['outcome'] = np.select([codes == 1, codes == 2], ['stop','target'], default='timeout')
                snapshot_frames.append(before.reset_index(drop=True))
        if number % 100 == 0:
            print(f'Features {number + 1}/{len(members)}; eligible tickers {len(frames)}', flush=True)
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), pd.concat(snapshot_frames, ignore_index=True) if snapshot_frames else pd.DataFrame())


def summaries(snapshots):
    output = []
    if snapshots.empty:
        return output
    for (horizon, lag), group in snapshots.groupby(['horizon', 'lag']):
        for name in FEATURES + ['ema20', 'sma50', 'sma200', 'market_cap']:
            stats = {}
            for label, subset in [('success', group[group.success]), ('failure', group[~group.success])]:
                v = subset[name].dropna()
                stats[label] = {'n': len(v), 'mean': v.mean() if len(v) else None, 'median': v.median() if len(v) else None, 'q10': v.quantile(.1) if len(v) else None, 'q25': v.quantile(.25) if len(v) else None, 'q75': v.quantile(.75) if len(v) else None, 'q90': v.quantile(.9) if len(v) else None}
            a, b = stats['success']['mean'], stats['failure']['mean']
            output.append({'horizon': horizon, 'lag': lag, 'feature': name, **stats, 'mean_difference': a-b if a is not None and b is not None else None})
    return output


def signals(frame, model):
    selected = frame.copy()
    selected['score'] = score(selected, model['rules'])
    return selected[selected.score >= model['score_threshold']]


def run(args):
    start, end, split = map(date.fromisoformat, (args.start, args.end, args.split))
    if not start < split < end:
        raise ValueError('Require start < split < end')
    members = universe()
    universe_size = len(members)
    if args.limit:
        members = members[:args.limit]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    prices, errors = collect(members, start, end, args.cache, args.refresh)
    report = {'schema_version': 1, 'status': 'insufficient_data', 'generated_at': datetime.now(timezone.utc).isoformat(), 'period': {'start': args.start, 'end': args.end, 'split': args.split}, 'universe_count': universe_size, 'requested_count': len(members), 'downloaded_count': len(set(prices) - {'SPY'}), 'analyzed_count': 0, 'observations': 0, 'limitations': LIMITATIONS, 'data_errors': errors, 'adopted_model': None, 'validation': None}
    if 'SPY' not in prices:
        report['limitations'] += ['SPY 기준일 데이터 확보 실패: 분석 중단.']
        write_json(output / 'research.json', report)
        return report
    metadata_errors = []
    frame, snapshots = observations(prices, members, start, end, split, metadata_errors)
    report.update(analyzed_count=frame.ticker.nunique() if not frame.empty else 0, observations=len(frame), metadata_errors=metadata_errors)
    if frame.empty:
        write_json(output / 'research.json', report)
        return report
    frame.to_csv(output / 'observations.csv', index=False)
    snapshots.to_csv(output / 'pre-event-features.csv', index=False)
    write_json(output / 'feature-statistics.json', summaries(snapshots))
    write_json(output / 'group-statistics.json', frame.groupby(['partition', 'sector', 'cap_group'], dropna=False).agg(observations=('success', 'size'), success_rate=('success', 'mean')).reset_index().to_dict('records'))
    report['cap_known_observations'] = int(frame.market_cap.notna().sum())
    train, validation = frame[frame.partition == 'train'], frame[frame.partition == 'validation']
    calendar = prices['SPY'].index
    train_calendar = calendar[(calendar >= start) & (calendar < split)]
    validation_calendar = calendar[(calendar >= split) & (calendar <= end)]
    report['train_observations'], report['validation_observations'] = len(train), len(validation)
    report['train_tickers'], report['validation_tickers'] = train.ticker.nunique(), validation.ticker.nunique()
    report['risk_quantiles'] = {name: float(train[name].quantile(.9)) for name in ('rsi14', 'rvol', 'atr_pct', 'return5')}
    latest = frame.sort_values('date').groupby('ticker').tail(1).sort_values('dollar_volume30', ascending=False).head(200)
    by_ticker = {m['ticker']: m for m in members}
    report['daily_universe'] = [by_ticker[t] for t in latest.ticker]
    rules = fit(train)
    if rules is None or validation.empty:
        report['limitations'] += ['학습 표본 부족: 최소 200 관측·20종목·성공/실패 모두 필요. 추천 비활성.']
        write_json(output / 'research.json', report)
        return report
    trials = []
    for model in candidates(rules):
        tested = portfolio(signals(train, model), prices, train_calendar)
        m = tested['metrics']
        trials.append({'model': model, 'metrics': m})
    # Minimum 30 completed training trades; validation is never a selection input.
    eligible = [t for t in trials if t['metrics']['trades'] >= 30]
    report['training_search'] = trials
    if not eligible:
        report['limitations'] += ['학습 완료 거래 30건 미만: 조건 채택 보류.']
        write_json(output / 'research.json', report)
        return report
    chosen = max(eligible, key=lambda t: t['metrics']['expectancy'])
    model = chosen['model']
    tested = portfolio(signals(validation, model), prices, validation_calendar)
    simple = validation.copy()
    simple['score'] = simple.return20 * 100
    # Fixed baseline: positive 20-day price momentum, same execution and capacity.
    simple = simple[simple.return20 > 0]
    simple_result = portfolio(simple, prices, validation_calendar)
    spy_signals = pd.DataFrame({'date': validation.date.unique(), 'ticker': 'SPY', 'score': 100.})
    spy_result = portfolio(spy_signals, prices, validation_calendar, max_positions=1)
    spy_bars = prices['SPY'].loc[(calendar >= split) & (calendar <= end)]
    buy_hold = float(spy_bars.Close.iloc[-1] * (1-.001) * (1-.0005) / (spy_bars.Open.iloc[0] * (1+.001) * (1+.0005)) - 1)
    m = tested['metrics']
    report.update(status='not_validated', selected_model=model, training_metrics=chosen['metrics'], validation=tested, baselines={'simple_momentum': simple_result, 'spy_same_exits': spy_result, 'spy_buy_hold_return': buy_hold}, target_rate_wilson95=uncertainty(tested['trades']))
    # Conservative operational gate, not a claim of statistical significance.
    gates = {'sample': m['trades'] >= 100 and validation.ticker.nunique() >= 30, 'positive_expectancy': (m['expectancy'] or 0) > 0, 'profit_factor': (m['profit_factor'] or 0) > 1, 'baseline_expectancy': (m['expectancy'] or 0) > (simple_result['metrics']['expectancy'] or 0), 'full_universe': not bool(args.limit), 'cap_coverage': report['cap_known_observations'] == len(frame)}
    report['validation_gates'] = gates
    if all(gates.values()):
        report.update(status='validated_exploratory', adopted_model=model)
    else:
        report['limitations'] += ['검증 게이트 미충족: 채택 조건 없음. 점수와 후보 추천 비활성.']
    write_json(output / 'research.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', default='2025-11-17')
    parser.add_argument('--end', default='2026-11-16')
    parser.add_argument('--split', default='2026-07-01')
    parser.add_argument('--cache', default='work/momentum/prices')
    parser.add_argument('--output', default='work/momentum/research')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    report = run(args)
    print(json.dumps({k: report[k] for k in ('status', 'universe_count', 'requested_count', 'downloaded_count', 'analyzed_count', 'observations')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
