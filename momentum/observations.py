"""Current technical observations, independent from validated recommendations."""
from datetime import date
from momentum.data import shares_facts, asof_cap
from momentum.features import features, FEATURES, session_windows

LABELS = {'atr_pct':'ATR14 / 주가', 'high20_gap':'20일 고점 대비 거리', 'high252_gap':'52주 고점 대비 거리'}


def build_observations(prices, members, report, reference_date):
    result = {'version':1, 'status':'unavailable', 'reference_date':str(reference_date), 'research_generated_at':report.get('generated_at'), 'rules':[], 'stages':[], 'items':[], 'diagnostics':[]}
    model = report.get('adopted_model') or report.get('selected_model')
    if not model or not model.get('rules'):
        result['diagnostics'].append({'error':'점검할 학습 기술조건이 없습니다.'})
        return result
    research_end = date.fromisoformat(report['period']['end'])
    if reference_date < research_end or (reference_date - research_end).days > 90:
        result['diagnostics'].append({'error':'연구 기준일 이전이거나 연구 후 90일 초과: 수동 재검증이 필요합니다.'})
        return result
    # Never inspect future bars, even when a caller supplies an untrimmed cache.
    current = {ticker:frame.loc[frame.index <= reference_date] for ticker,frame in prices.items()}
    spy = current.get('SPY')
    if spy is None or spy.empty or spy.index[-1] != reference_date:
        result['diagnostics'].append({'error':'SPY 기준일 가격 미확인: 현재 관찰 목록을 게시하지 않습니다.'})
        return result
    rules = model['rules']
    result['rules'] = [{**r,'label':LABELS.get(r['feature'],r['feature'])} for r in rules]
    data_count, liquid_count = 0, 0
    condition_counts = [0] * len(rules)
    technical_count, below_cap = 0, 0
    for member in members:
        ticker = member['ticker']
        bars = current.get(ticker)
        if bars is None or bars.empty or bars.index[-1] != reference_date:
            result['diagnostics'].append({'ticker':ticker,'error':'기준일 가격 누락 또는 지연'})
            continue
        if not session_windows(bars,spy)[0].iloc[-1]:
            result['diagnostics'].append({'ticker':ticker,'error':'과거 252거래일 가격 누락 또는 이력 부족'})
            continue
        row = features(bars,spy).iloc[-1]
        if row[FEATURES].isna().any():
            result['diagnostics'].append({'ticker':ticker,'error':'기술지표 누락'})
            continue
        data_count += 1
        if row.close < 10 or row.dollar_volume30 < 20_000_000:
            continue
        liquid_count += 1
        checks = []
        cumulative = True
        for i, rule in enumerate(rules):
            value = float(row[rule['feature']])
            passed = (value - rule['threshold']) * rule['direction'] >= 0
            checks.append({'feature':rule['feature'],'label':LABELS.get(rule['feature'],rule['feature']),'value':value,'threshold':rule['threshold'],'direction':rule['direction'],'passed':bool(passed)})
            cumulative = cumulative and passed
            if cumulative:
                condition_counts[i] += 1
        if not cumulative:
            continue
        technical_count += 1
        try:
            cap = asof_cap(shares_facts(member),reference_date,float(row.close))
        except Exception as exc:
            cap = None
            result['diagnostics'].append({'ticker':ticker,'error':f'시점별 시총 미확인: {exc}'})
        if cap is not None and cap < 1_000_000_000:
            below_cap += 1
            continue
        warnings = []
        if cap is None:
            warnings.append('시점별 시가총액 미확인')
        strategy_valid = report.get('status') == 'validated_exploratory' and bool(report.get('adopted_model'))
        if not strategy_valid:
            warnings.append('전략 수익성·표본 검증 미통과')
        if reference_date == research_end:
            warnings.append('연구 종료일과 같은 기준일: 신규 구간 검증 아님')
        if strategy_valid and cap is not None and reference_date > research_end:
            # Verified stocks are handled by the existing recommendation path.
            continue
        already = bool(row.return5 >= .10 or row.return10 >= .10 or row.return20 >= .10)
        if already:
            warnings.append('최근 5·10·20일 중 +10% 이상 상승: 추격 위험')
        for name in ('rsi14','rvol','atr_pct','return5'):
            threshold = report.get('risk_quantiles',{}).get(name)
            if threshold is not None and row[name] > threshold:
                warnings.append(f'{name}: 학습 표본 상위 10% 위험 구간')
        # Secondary watchlist review only: not a learned model or trading signal.
        review_checks = [
            {'label':'시총 확인', 'passed': cap is not None},
            {'label':'급등 전 구간', 'passed': not already},
            {'label':'SPY 대비 강세', 'passed': float(row.relative_strength) > 0},
            {'label':'20일선 위', 'passed': float(row.ema20_gap) > 0},
            {'label':'50일선 위', 'passed': float(row.sma50_gap) > 0},
            {'label':'거래량 1.2배 이상', 'passed': float(row.rvol) >= 1.2},
            {'label':'RSI 50~70', 'passed': 50 <= float(row.rsi14) <= 70},
        ]
        priority = all(check['passed'] for check in review_checks)
        result['items'].append({**row.to_dict(),'ticker':ticker,'name':member.get('name') or ticker,'exchange':member.get('exchange'),'market_cap':cap,'market_cap_status':'unknown' if cap is None else 'verified','technical_pass_count':len(checks),'technical_total':len(checks),'checks':checks,'priority_watch':priority,'review_checks':review_checks,'warnings':warnings,'stage':'already_surged' if already else 'early'})
    result['items'].sort(key=lambda item:(not item['priority_watch'],-item['dollar_volume30'],item['ticker']))
    result['stages'] = [{'key':'universe','label':'관찰 유니버스','count':len(members)},{'key':'data','label':'가격·지표 이력 확인','count':data_count},{'key':'liquidity','label':'주가 $10 · 평균 거래대금 $20M','count':liquid_count}]
    def label(rule):
        threshold = f"{rule['threshold']:.2f}" if rule['feature'] in ('rsi14','rvol') else f"{rule['threshold']*100:.2f}%"
        return f"{LABELS.get(rule['feature'],rule['feature'])} {'≥' if rule['direction']>0 else '≤'} {threshold}"
    result['stages'] += [{'key':f'technical_{i+1}','label':label(rule),'count':condition_counts[i]} for i,rule in enumerate(rules)]
    result['stages'].append({'key':'observations','label':'기술조건 전체 통과 · 관찰 후보','count':len(result['items'])})
    result.update(status='degraded' if result['diagnostics'] else 'success',technical_pass_count=technical_count,known_small_cap_excluded=below_cap,market_cap_unknown_count=sum(item['market_cap'] is None for item in result['items']),sort='priority_watch_then_dollar_volume30_desc_then_ticker',note='연구 기술조건을 모두 통과한 종목만 관찰합니다. 우선 관찰은 시총 확인·미급등·상대강도·추세·거래량·RSI 등 보조 체크 7개를 모두 만족한 경우이며 성과 검증된 매수 신호가 아닙니다.')
    return result
