"""Lightweight screening from a frozen, validated research artifact. No model refit."""
import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import pandas as pd
from market_calendar import latest_completed_session
from momentum.data import collect, write_json, shares_facts, asof_cap
from momentum.features import features, FEATURES
from momentum.model import score


def build_candidates(prices, members, report, reference_date):
    model = report.get('adopted_model')
    if report.get('status') != 'validated_exploratory' or not model:
        return [], [{'error': '검증된 채택 조건 없음: 추천 비활성'}]
    if date.fromisoformat(report['period']['end']) >= reference_date:
        return [], [{'error': '연구 종료일 이후 거래일부터만 동결 모델로 스크리닝 가능'}]
    spy = prices.get('SPY')
    if spy is None or spy.index[-1] != reference_date:
        return [], [{'error': 'SPY 기준일 가격 미확인'}]
    candidates, diagnostics = [], []
    for member in members:
        ticker = member['ticker']
        bars = prices.get(ticker)
        if bars is None or bars.index[-1] != reference_date:
            diagnostics.append({'ticker': ticker, 'error': '가격 누락 또는 오래된 데이터'})
            continue
        row = features(bars, spy).iloc[-1]
        if row[FEATURES].isna().any():
            diagnostics.append({'ticker': ticker, 'error': '지표 계산 이력 부족 또는 누락'})
            continue
        if row.close < 10 or row.dollar_volume30 < 20_000_000:
            continue
        try:
            cap = asof_cap(shares_facts(member), reference_date, row.close)
        except Exception as exc:
            cap = None
            diagnostics.append({'ticker': ticker, 'error': f'시총 미확인: {exc}'})
        if cap is None or cap < 1_000_000_000:
            continue
        points = float(score(pd.DataFrame([row]), model['rules']).iloc[0])
        if points < model['score_threshold']:
            continue
        total = sum(r['weight'] for r in model['rules'])
        reasons = []
        for rule in model['rules']:
            value = float(row[rule['feature']])
            passed = (value-rule['threshold']) * rule['direction'] >= 0
            if passed:
                reasons.append(f"{rule['feature']} {value:.4f} {'≥' if rule['direction'] > 0 else '≤'} {rule['threshold']:.4f}: +{rule['weight']/total*100:.1f}점")
        already = bool(row.return5 >= .10 or row.return10 >= .10 or row.return20 >= .10)
        warnings = []
        for name in ('rsi14', 'rvol', 'atr_pct', 'return5'):
            threshold = report.get('risk_quantiles', {}).get(name)
            if threshold is not None and row[name] > threshold:
                warnings.append(f'{name}: 학습 표본 상위 10% 위험 구간')
        if already:
            warnings.append('최근 5·10·20일 중 +10% 이상 상승: 추격 진입 및 갭 위험')
        candidates.append({**row.to_dict(), 'ticker': ticker, 'name': member.get('name'), 'score': points, 'market_cap': cap, 'stage': 'already_surged' if already else 'early', 'reasons': reasons, 'warnings': warnings})
    candidates.sort(key=lambda r: (-r['score'], r['ticker']))
    return candidates, diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--research', default='web/public/data/momentum-research.json')
    parser.add_argument('--output', default='web/public/data/latest-momentum.json')
    parser.add_argument('--cache', default='work/momentum/daily-prices')
    parser.add_argument('--skip-unchanged', action='store_true')
    args = parser.parse_args()
    reference = latest_completed_session()
    report = json.loads(Path(args.research).read_text())
    path = Path(args.output)
    if args.skip_unchanged and path.exists():
        current = json.loads(path.read_text())
        if current.get('data_date') == str(reference) and current.get('research_generated_at') == report.get('generated_at') and current.get('status') in ('success', 'not_validated'):
            print('Already published this session and frozen model; skipped.')
            return
    payload = {'schema_version': 1, 'data_date': str(reference), 'generated_at': datetime.now(timezone.utc).isoformat(), 'research_generated_at': report.get('generated_at'), 'status': 'not_validated', 'candidates': [], 'diagnostics': [], 'universe_count': 0}
    if report.get('status') != 'validated_exploratory' or not report.get('adopted_model'):
        payload['diagnostics'] = [{'error': '실제 연구의 검증 게이트 미충족: 추천·점수 미표시'}]
    else:
        members = report.get('daily_universe', [])
        if not members or len(members) > 200:
            raise ValueError('Frozen daily universe must contain 1..200 members')
        if (reference - date.fromisoformat(report['period']['end'])).days > 90:
            payload['diagnostics'] = [{'error': '연구 종료 후 90일 초과: 수동 재검증 필요'}]
        else:
            prices, errors = collect(members, reference - pd.Timedelta(days=365), reference, args.cache)
            rows, diagnostics = build_candidates(prices, members, report, reference)
            payload.update(status='degraded' if errors or diagnostics else 'success', candidates=rows, diagnostics=errors + diagnostics, universe_count=len(members))
    write_json(path, payload)


if __name__ == '__main__':
    main()
