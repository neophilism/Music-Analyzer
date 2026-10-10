"""Instrumental mood prototypes and uncalibrated semantic valence/arousal.

Prototype weights are similarity attention weights, never event probabilities.
Nothing in this module reads lyrics, key, tempo, genre tags, or filenames.
"""

import numpy as np

MOODS = {
    "celebratory": (95, 90, "joyful, triumphant, festive and celebratory"),
    "happy": (85, 65, "happy, cheerful, playful and upbeat"),
    "hopeful": (80, 55, "hopeful, uplifting, optimistic and inspiring"),
    "peaceful": (75, 15, "peaceful, serene, soothing and contented"),
    "tender": (70, 25, "warm, tender, affectionate and gentle"),
    "neutral": (50, 40, "emotionally neutral, matter-of-fact and understated"),
    "bittersweet": (45, 35, "bittersweet, wistful, nostalgic and reflective"),
    "melancholic": (20, 25, "melancholic, lonely, sorrowful and wistful"),
    "sad": (10, 15, "sad, grieving, mournful and heartbroken"),
    "dark/brooding": (15, 45, "dark, ominous, bleak, brooding and foreboding"),
    "angry": (10, 95, "angry, aggressive, furious, hostile and menacing"),
    "tense": (25, 85, "tense, anxious, frantic and threatening"),
}


def mood_prompts():
    return {f"mood:{label}": [f"This instrumental music sounds {description}.",
                              f"An instrumental piece with a {description} emotional mood.",
                              f"The musical sound conveys a {description} feeling."]
            for label, (_, _, description) in MOODS.items()}


def score_segment(scores: dict) -> dict:
    labels = list(MOODS)
    similarities = np.array([scores[f"mood:{label}"] for label in labels])
    attention = np.exp((similarities - similarities.max()) / .035)
    attention /= attention.sum()
    valence = float(sum(weight * MOODS[label][0] for weight, label in zip(attention, labels, strict=True)))
    arousal = float(sum(weight * MOODS[label][1] for weight, label in zip(attention, labels, strict=True)))
    order = np.argsort(-similarities, kind="stable")
    margin = float(similarities[order[0]] - similarities[order[1]])
    return {"valence": valence, "arousal": arousal, "margin": margin,
            "mood": labels[order[0]],
            "mood_candidates": [{"label": labels[i], "similarity": float(similarities[i])} for i in order[:3]]}


def summarize_emotion(segments: list[dict], duration: float) -> dict:
    if not segments:
        return {"valence": None, "arousal": None, "mood": "unknown", "mood_candidates": [],
                "valence_reliability": 0., "model_coverage": 0., "needs_review": True,
                "review_reasons": ["No local emotion inference"], "emotion_curve": [],
                "emotion_method": "unavailable"}
    rows = [{**score_segment(s["scores"]), "time": s["time"], "duration": s["duration"]} for s in segments]
    durations = [r["duration"] for r in rows]
    valences, arousals = [r["valence"] for r in rows], [r["arousal"] for r in rows]
    valence = float(np.average(valences, weights=durations))
    arousal = float(np.average(arousals, weights=durations))
    spread = float(np.sqrt(np.average((np.asarray(valences) - valence) ** 2, weights=durations)))
    coverage = min(1., sum(durations) / max(duration, .001))
    means = {label: float(np.average([s["scores"][f"mood:{label}"] for s in segments], weights=durations)) for label in MOODS}
    ranked = sorted(means, key=lambda label: (-means[label], label))
    # Engineering reliability indicator: deliberately not a calibrated probability.
    margin = float(np.average([r["margin"] for r in rows], weights=durations))
    reliability = min(1., margin / .04) * max(0., 1 - spread / 35) * coverage
    reasons = []
    if 40 <= valence <= 60:
        reasons.append("Neutral or mixed valence (40–60)")
    if reliability < .4:
        reasons.append("Small mood similarity margin; interpretation needs listening")
    if spread > 15:
        reasons.append("Emotion varies substantially across the recording")
    if coverage < .5:
        reasons.append("Less than half the recording has usable model coverage")
    return {"valence": valence, "arousal": arousal, "mood": ranked[0],
            "mood_candidates": [{"label": label, "similarity": means[label]} for label in ranked[:4]],
            "valence_reliability": float(reliability), "valence_std": spread,
            "model_coverage": float(coverage), "needs_review": bool(reasons),
            "review_reasons": reasons, "emotion_curve": rows,
            "emotion_method": "CLAP instrumental prototype similarities; uncalibrated semantic scale"}
