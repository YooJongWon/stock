from indicators import normalize_ohlcv

def validate_ohlcv(frame, reference_date=None):
    return normalize_ohlcv(frame, reference_date)
