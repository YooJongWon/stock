"""Small predeclared search space. Thresholds and weights fit on training data only."""
import itertools
import numpy as np
from momentum.features import FEATURES


def fit(train):
    if len(train) < 200 or train.ticker.nunique() < 20 or train.success.nunique() < 2:
        return None
    y = train.success.astype(float)
    rules = []
    for name in FEATURES:
        values = train[name]
        if values.nunique() < 2:
            continue
        correlation = values.corr(y)
        if not np.isfinite(correlation):
            continue
        direction = 1 if correlation > 0 else -1
        threshold = float(values.quantile(.5))
        rules.append({"feature": name, "direction": direction, "threshold": threshold, "weight": abs(float(correlation))})
    rules.sort(key=lambda r: (-r["weight"], r["feature"]))
    return rules


def score(frame, rules):
    total = sum(r["weight"] for r in rules)
    if not total:
        return np.zeros(len(frame))
    return sum((((frame[r["feature"]] - r["threshold"]) * r["direction"]) >= 0).astype(float) * r["weight"] for r in rules) / total * 100


def candidates(rules):
    # 12 variants, fixed before inspecting validation; train portfolio selects one.
    for size, threshold in itertools.product((3, 5, 8), (50, 65, 80, 95)):
        if len(rules) >= size:
            yield {"rules": rules[:size], "score_threshold": threshold}


def uncertainty(trades):
    """Wilson interval is descriptive: repeated/overlapping market observations aren't IID."""
    n = len(trades)
    if not n:
        return None
    p = sum(t["reason"] == "target" for t in trades) / n
    z = 1.96
    centre = (p + z*z/(2*n)) / (1+z*z/n)
    half = z * ((p*(1-p)/n + z*z/(4*n*n)) ** .5) / (1+z*z/n)
    return [centre-half, centre+half]
