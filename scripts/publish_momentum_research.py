"""Publish a real manual run's compact report; never invent results or auto-refit."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import pandas as pd
from momentum.data import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', default='work/momentum/research')
    parser.add_argument('--destination', default='web/public/data')
    parser.add_argument('--cache', default='work/momentum/prices')
    args = parser.parse_args()
    source, destination = Path(args.source), Path(args.destination)
    report = json.loads((source / 'research.json').read_text())
    if not report.get('generated_at') or not report.get('period'):
        raise ValueError('Missing real research provenance')
    # Attach frozen daily coverage and risk quantiles for older run-schema compatibility.
    observations_path = source / 'observations.csv'
    if observations_path.exists():
        observations = pd.read_csv(observations_path)
        train = observations[observations.partition == 'train']
        report['risk_quantiles'] = {k: float(train[k].quantile(.9)) for k in ('rsi14', 'rvol', 'atr_pct', 'return5')}
        if 'daily_universe' not in report:
            from momentum.data import universe
            members = {m['ticker']:m for m in universe()}
            latest = observations.sort_values('date').groupby('ticker').tail(1).sort_values('dollar_volume30', ascending=False).head(200)
            report['daily_universe'] = [members[t] for t in latest.ticker if t in members]
    report['execution'] = {'entry':'next_session_open', 'target':.10, 'stop':-.05, 'max_sessions':20, 'slippage_one_way':.001, 'fee_one_way':.0005, 'max_positions':5, 'position_size_initial_capital':.2, 'intraday_collision':'stop_first', 'reuse_exit_day_capital':False, 'dividends':'excluded_price_return'}
    report['provenance'] = {'base_commit':subprocess.check_output(['git','merge-base','HEAD','origin/main'], text=True).strip(), 'code_commit':subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(), 'packages':{p:importlib.metadata.version(p) for p in ('pandas','numpy','yfinance','exchange-calendars')}, 'price_file_count':0, 'price_cache_sha256':None, 'published_at':datetime.now(timezone.utc).isoformat()}
    digest = hashlib.sha256()
    for path in sorted(Path(args.cache).glob('*.csv')):
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        report['provenance']['price_file_count'] += 1
    report['provenance']['price_cache_sha256'] = digest.hexdigest()
    # Detailed trades/equity remain in the reproducible manual artifact, compact metrics in web.
    if report.get('validation'):
        report['validation'] = {'metrics':report['validation']['metrics']}
    for key in ('simple_momentum','spy_same_exits'):
        if report.get('baselines', {}).get(key):
            report['baselines'][key] = {'metrics':report['baselines'][key]['metrics']}
    errors = report.pop('data_errors', [])
    report['data_error_count'] = len(errors)
    report['data_error_examples'] = errors[:20]
    from collections import Counter
    report['data_error_categories'] = dict(Counter(e['error'].split(':')[0] for e in errors))
    metadata = report.pop('metadata_errors', [])
    report['metadata_error_count'] = len(metadata)
    report['metadata_error_examples'] = metadata[:5]
    for filename in ('feature-statistics.json','group-statistics.json'):
        path = source / filename
        if path.exists():
            write_json(destination / ('momentum-' + filename), json.loads(path.read_text()))
    write_json(destination / 'momentum-research.json', report)
    print(json.dumps({k:report.get(k) for k in ('status','analyzed_count','observations','validation_gates')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
