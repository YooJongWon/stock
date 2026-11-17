"""Free sources, persistent raw OHLCV cache, explicit point-in-time metadata."""
from datetime import date, datetime, timezone
from pathlib import Path
import json
import pandas as pd
import yfinance as yf
from data_provider import UniverseProvider
from indicators import normalize_ohlcv
from providers.sec_fundamentals import SECFundamentalProvider


def universe():
    rows = UniverseProvider().get()
    # Be stricter than the legacy engine without changing its directory parser.
    forbidden = (" etn", " etf", "preferred", "warrant", " units", " rights", "beneficial interest", "closed-end", "closed end")
    return [r for r in rows if not any(s in (' ' + str(r.get('name', '')).lower()) for s in forbidden)]


def collect(members, start, end, cache, refresh=False):
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(cache / 'yahoo'))
    prices, errors = {}, []
    warmup = pd.Timestamp(start) - pd.Timedelta(days=550)
    symbols = list(dict.fromkeys(['SPY'] + [m['ticker'] for m in members]))
    missing = []
    for ticker in symbols:
        path = cache / f'{ticker}.csv'
        failure = cache / f'{ticker}.error.json'
        if not refresh and failure.exists():
            try:
                previous = json.loads(failure.read_text())
                age = datetime.now(timezone.utc).timestamp() - previous['timestamp']
                if previous['end'] == str(end) and age < 3600:
                    errors.append({'ticker': ticker, 'error': previous['error']})
                    continue
            except (OSError, ValueError, KeyError):
                pass
        try:
            if refresh:
                raise FileNotFoundError()
            frame = pd.read_csv(path, index_col=0, parse_dates=True)
            frame = normalize_ohlcv(frame, end)
            if frame.index[-1] != end:
                raise ValueError('cached price is stale')
            prices[ticker] = frame
        except (OSError, ValueError):
            missing.append(ticker)
    for offset in range(0, len(missing), 100):
        chunk = missing[offset:offset + 100]
        print(f'OHLCV {offset + 1}..{offset + len(chunk)}/{len(missing)}', flush=True)
        try:
            downloaded = yf.download(chunk, start=str(warmup.date()), end=str(end + pd.Timedelta(days=1)), auto_adjust=False, actions=True, group_by='ticker', threads=8, progress=False, timeout=20)
        except Exception as exc:
            errors.extend({'ticker': t, 'error': str(exc)} for t in chunk)
            continue
        for ticker in chunk:
            try:
                raw = downloaded[ticker] if isinstance(downloaded.columns, pd.MultiIndex) else downloaded
                # Splits require a position/share adjustment engine. Never silently model a split as a crash.
                splits = raw.get('Stock Splits', pd.Series(0, index=raw.index))
                if (splits.fillna(0) != 0).any():
                    raise ValueError('split in observation/warmup period; excluded, corporate-action coverage limitation')
                frame = normalize_ohlcv(raw, end)
                if frame.index[-1] != end:
                    raise ValueError(f'stale price: {frame.index[-1]}, expected {end}')
                frame.to_csv(cache / f'{ticker}.csv')
                (cache / f'{ticker}.error.json').unlink(missing_ok=True)
                prices[ticker] = frame
            except Exception as exc:
                errors.append({'ticker': ticker, 'error': str(exc)})
                write_json(cache / f'{ticker}.error.json', {'end': str(end), 'timestamp': datetime.now(timezone.utc).timestamp(), 'error': str(exc)})
    return prices, errors


def shares_facts(member):
    """Reuse SEC transport/cache/filing filters; never use current Yahoo market cap."""
    if not member.get('cik'):
        return []
    provider = SECFundamentalProvider()
    cik = str(member['cik']).zfill(10)
    facts = provider._get_json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json', f'companyfacts_{cik}', 86400)
    records = []
    for namespace, tag in [('dei', 'EntityCommonStockSharesOutstanding'), ('us-gaap', 'CommonStockSharesOutstanding')]:
        fact = facts.get('facts', {}).get(namespace, {}).get(tag, {})
        records += provider._records(fact, date.max)
    return [r for r in records if r.get('unit') == 'shares' and not r.get('start') and r['val'] > 0]


def asof_cap(records, day, close):
    # Filing dates lack time-of-day: usable from the following session, conservatively.
    eligible = [r for r in records if r['filed'] < day and r['end'] <= day and (day - r['end']).days <= 180]
    if not eligible:
        return None
    latest = max(eligible, key=lambda r: (r['end'], r['filed']))
    return float(latest['val']) * close


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # pandas normalizes numpy/date types and NaNs, then strict JSON rejects remaining nonfinite values.
    clean = json.loads(pd.Series([payload]).to_json(orient='values', date_format='iso'))[0]
    content = json.dumps(clean, ensure_ascii=False, indent=2, allow_nan=False)
    temp = path.with_suffix('.tmp')
    temp.write_text(content + '\n', encoding='utf8')
    temp.replace(path)
