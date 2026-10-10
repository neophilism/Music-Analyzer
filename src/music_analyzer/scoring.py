"""Frozen corpus mappings alongside fixed semantic valence and reference calibration."""

import hashlib
import json
import math
import time
import uuid

import numpy as np

from music_analyzer.domain import Track

DEFAULT_WEIGHTS = {"dynamics": .4, "rhythmic_drive": .25, "arousal": .2, "density": .15}
BOUNDS = {"integrated_lufs": (-36., -6.), "loudness_p90": (-30., -3.),
          "bpm": (math.log(40), math.log(200)), "onset_rate": (.5, 8.), "density_raw": (.01, .6)}


def finite(value):
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def mapped(value, lower, upper):
    if not finite(value):
        return None
    if abs(upper - lower) < 1e-10:
        return 50.
    return float(np.clip((value - lower) / (upper - lower) * 100, 0, 100))


def weighted(values: dict, weights: dict):
    present = {key: value for key, value in values.items() if finite(value) and weights.get(key, 0) > 0}
    denominator = sum(weights[key] for key in present)
    return (sum(value * weights[key] for key, value in present.items()) / denominator if denominator else None,
            denominator / sum(weights.values()) if sum(weights.values()) else 0)


def fingerprint(tracks: list[Track]) -> str:
    values = [{"id": t.id, "hash": t.sha256, "excluded": t.excluded, "status": t.status,
               "inputs": {k: t.value(k) for k in (*BOUNDS, "sustained_fraction", "valence", "arousal")}}
              for t in tracks]
    return hashlib.sha256(json.dumps(values, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_weights(weights):
    if set(weights) != set(DEFAULT_WEIGHTS) or any(not finite(v) or v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
        raise ValueError("Intensity weights must be nonnegative, finite, and have a positive total.")


def make_snapshot(tracks: list[Track], profile="perceived", weights=None, reference_ids=None, valence_calibration=None) -> dict:
    if profile not in {"simple", "perceived"}:
        raise ValueError("Unknown intensity profile.")
    weights = weights or DEFAULT_WEIGHTS.copy()
    validate_weights(weights)
    eligible = [track for track in tracks if not track.excluded and track.status == "complete"]
    ranges = {}
    for key, fallback in BOUNDS.items():
        values = [t.value(key) for t in eligible if finite(t.value(key)) and (key != "bpm" or t.value(key) > 0)]
        if key == "bpm":
            values = [math.log(v) for v in values]
        if len(values) >= 5:
            lower, upper = np.percentile(values, [5, 95])
            source = "corpus q05–q95"
        else:
            lower, upper = fallback
            source = "small corpus: fixed fallback bounds"
        ranges[key] = {"lower": float(lower), "upper": float(upper), "source": source}
    snapshot = {"id": uuid.uuid4().hex, "created": time.time(), "fingerprint": fingerprint(tracks),
                "members": [t.id for t in eligible], "ranges": ranges, "profile": profile,
                "weights": weights, "reference": None, "valence_calibration": valence_calibration}
    if reference_ids:
        by_id = {t.id: t for t in eligible}
        try:
            quiet, dense = (by_id[identifier] for identifier in reference_ids)
        except KeyError as exc:
            raise ValueError("Both reference anchors must be analyzed, included tracks.") from exc
        low, high = fixed_dynamics(quiet), fixed_dynamics(dense)
        if low is None or high is None or high - low < 1:
            raise ValueError("These recordings do not establish distinct increasing volume anchors. Choose suitable recordings.")
        snapshot["reference"] = {"quiet_id": quiet.id, "dense_id": dense.id,
                                 "low": low, "high": high, "quiet_target": 5., "dense_target": 95.}
    return snapshot


def fixed_dynamics(track):
    integrated = mapped(track.value("integrated_lufs"), *BOUNDS["integrated_lufs"])
    p90 = mapped(track.value("loudness_p90"), *BOUNDS["loudness_p90"])
    sustained = track.value("sustained_fraction")
    values = {"integrated": integrated, "p90": p90,
              "sustained": float(np.clip(sustained * 100, 0, 100)) if finite(sustained) else None}
    return weighted(values, {"integrated": .65, "p90": .25, "sustained": .1})[0]


def score_tracks(tracks: list[Track], snapshot: dict) -> dict[str, dict]:
    from music_analyzer.calibration import calibrated_valence

    result = {}
    def positivity(track):
        return track.value("valence") if "valence" in track.overrides else calibrated_valence(track.value("valence"), snapshot.get("valence_calibration"))
    valences = [positivity(t) for t in tracks if not t.excluded and finite(positivity(t))]
    for track in tracks:
        components = {}
        for key, bounds in snapshot["ranges"].items():
            value = track.value(key)
            if key == "bpm":
                value = math.log(value) if finite(value) and value > 0 else None
            components[key] = mapped(value, bounds["lower"], bounds["upper"])
        sustained = track.value("sustained_fraction")
        dynamics, dynamics_coverage = weighted(
            {"integrated": components["integrated_lufs"], "p90": components["loudness_p90"],
             "sustained": float(np.clip(sustained * 100, 0, 100)) if finite(sustained) else None},
            {"integrated": .65, "p90": .25, "sustained": .1},
        )
        corpus_dynamics = dynamics
        reference = snapshot.get("reference")
        reference_dynamics = None
        if reference:
            base = fixed_dynamics(track)
            reference_dynamics = float(np.clip(5 + 90 * (base - reference["low"]) / (reference["high"] - reference["low"]), 0, 100)) if finite(base) else None
            dynamics = reference_dynamics
        tempo = components["bpm"]
        valence = positivity(track)
        valence = float(np.clip(valence, 0, 100)) if finite(valence) else None
        rank = None
        if valence is not None and valences:
            below = sum(v < valence for v in valences)
            tied = sum(v == valence for v in valences)
            rank = 100 * (below + (tied - 1) / 2) / (len(valences) - 1) if len(valences) > 1 else 50.
        simple, simple_coverage = weighted({"dynamics": dynamics, "tempo": tempo}, {"dynamics": .5, "tempo": .5})
        drive, _ = weighted({"tempo": tempo, "onset": components["onset_rate"]}, {"tempo": .7, "onset": .3})
        perceived, perceived_coverage = weighted({"dynamics": dynamics, "rhythmic_drive": drive,
                                                  "arousal": track.value("arousal"), "density": components["density_raw"]}, snapshot["weights"])
        intensity = simple if snapshot["profile"] == "simple" else perceived
        manual_bucket = track.overrides.get("bucket")
        bucket = manual_bucket if manual_bucket in {"positive", "negative"} else ("positive" if valence is not None and valence >= 50 else "negative" if valence is not None else None)
        needs_review = not track.reviewed and (track.analysis.get("needs_review", True) or valence is None or intensity is None)
        result[track.id] = {"dynamics": dynamics, "corpus_dynamics": corpus_dynamics,
                            "reference_dynamics": reference_dynamics, "tempo": tempo, "valence": valence,
                            "valence_corpus_rank": rank, "raw_semantic_valence": track.analysis.get("valence"),
                            "intensity": intensity, "simple_intensity": simple,
                            "perceived_intensity": perceived, "rhythmic_drive": drive, "density": components["density_raw"],
                            "bucket": bucket, "needs_review": needs_review,
                            "coverage": simple_coverage if snapshot["profile"] == "simple" else perceived_coverage,
                            "dynamics_coverage": dynamics_coverage,
                            "missing_components": [key for key, value in {"dynamics": dynamics, "tempo": tempo,
                                                    "arousal": track.value("arousal"), "density": components["density_raw"]}.items() if value is None]}
    return result
