"""Optional listener calibration. Training fit is not held-out model accuracy."""

import numpy as np
from scipy.optimize import minimize

from music_analyzer.scoring import DEFAULT_WEIGHTS, finite, validate_weights


def fit_valence_anchors(tracks):
    anchors = [(t.analysis.get("valence"), t.overrides.get("valence"), t.id)
               for t in tracks if t.reviewed and finite(t.analysis.get("valence")) and finite(t.overrides.get("valence"))]
    if len(anchors) < 3:
        raise ValueError("Review and correct positivity on at least three model-analyzed tracks first.")
    # Pool adjacent violators; conflicting listener labels remain in provenance.
    points = [(0., 0., 1e6), (100., 100., 1e6)] + [(x, y, 1.) for x, y, _ in anchors if 0 < x < 100]
    xs = sorted({x for x, _, _ in points})
    blocks = []
    for index, x in enumerate(xs):
        matching = [(y, weight) for px, y, weight in points if px == x]
        weight = sum(w for _, w in matching)
        blocks.append([index, index, sum(y * w for y, w in matching) / weight, weight])
        while len(blocks) >= 2 and blocks[-2][2] > blocks[-1][2]:
            right, left = blocks.pop(), blocks.pop()
            total = left[3] + right[3]
            blocks.append([left[0], right[1], (left[2] * left[3] + right[2] * right[3]) / total, total])
    ys = np.zeros(len(xs))
    for first, last, value, _ in blocks:
        ys[first:last + 1] = value
    ys[0], ys[-1] = 0., 100.
    return {"x": xs, "y": ys.tolist(), "anchors": [{"id": tid, "raw": x, "target": y} for x, y, tid in anchors],
            "method": "Listener-specific monotone interpolation; no general accuracy claim"}


def calibrated_valence(raw, calibration):
    if not finite(raw):
        return None
    if not calibration:
        return float(raw)
    return float(np.interp(raw, calibration["x"], calibration["y"]))


def fit_intensity_pairs(scores: dict, pairs: list[dict], prior=None) -> dict:
    prior = prior or DEFAULT_WEIGHTS
    validate_weights(prior)
    names = list(DEFAULT_WEIGHTS)
    rows = []
    for pair in pairs:
        higher, lower = scores.get(pair["higher"]), scores.get(pair["lower"])
        if not higher or not lower or not all(finite(row.get(key)) for row in (higher, lower) for key in names):
            continue
        rows.append([(higher[key] - lower[key]) / 100 for key in names])
    if len(rows) < 3:
        raise ValueError("Add at least three comparisons with complete dynamics, rhythm, arousal, and density values.")
    matrix = np.asarray(rows)
    baseline = np.array([prior[key] for key in names], dtype=float)
    baseline /= baseline.sum()
    def objective(weights):
        return float(np.mean(np.logaddexp(0, -matrix @ weights * 6)) + .05 * np.sum((weights - baseline) ** 2))
    fit = minimize(objective, baseline, method="SLSQP", bounds=[(0, 1)] * len(names),
                   constraints={"type": "eq", "fun": lambda weights: weights.sum() - 1})
    if not fit.success:
        raise ValueError("Could not fit a stable preference profile. Keep the current weights.")
    weights = {key: float(value) for key, value in zip(names, fit.x, strict=True)}
    return {"weights": weights, "pairs_used": len(rows),
            "training_pair_agreement": float(np.mean(matrix @ fit.x > 0)),
            "note": "Agreement on your fitting comparisons; not an independent quality benchmark"}
