"""Tuning-aware chroma profile matching; tonal ambiguity stays visible."""

import warnings

import librosa
import numpy as np

NOTES = ["C", "C♯", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B"]
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def profile_candidates(chroma):
    vector = np.asarray(chroma, dtype=float)
    centered = vector - vector.mean()
    magnitude = np.linalg.norm(centered)
    if magnitude < 1e-9:
        return []
    candidates = []
    for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
        for tonic, note in enumerate(NOTES):
            rotated = np.roll(profile, tonic)
            rotated -= rotated.mean()
            correlation = float(np.dot(centered, rotated) / (magnitude * np.linalg.norm(rotated)))
            candidates.append({"key": f"{note} {mode}", "tonic": note, "mode": mode,
                               "correlation": correlation})
    return sorted(candidates, key=lambda row: (-row["correlation"], row["key"]))


def analyze_tonal_segment(samples, start, rate=22050):
    if len(samples) < rate * .5 or np.mean(samples ** 2) < 1e-10:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        spectrum = np.abs(librosa.stft(samples, n_fft=4096, hop_length=1024))
        tuning = float(librosa.estimate_tuning(S=spectrum, sr=rate, n_fft=4096))
        chroma = librosa.feature.chroma_stft(S=spectrum ** 2, sr=rate, n_fft=4096,
                                            hop_length=1024, tuning=tuning)
    energy = np.sum(spectrum ** 2, axis=0)
    active = energy > np.max(energy) * .001
    if not np.any(active):
        return None
    vector = np.average(chroma[:, active], axis=1, weights=energy[active])
    probabilities = vector / max(vector.sum(), 1e-10)
    entropy = -np.sum(probabilities * np.log(probabilities + 1e-12)) / np.log(12)
    candidates = profile_candidates(vector)
    if not candidates:
        return None
    gap = candidates[0]["correlation"] - candidates[1]["correlation"]
    tonal = bool(entropy < .98 and candidates[0]["correlation"] > .5 and gap > .035)
    return {"time": float(start + len(samples) / (2 * rate)),
            "chroma": vector.tolist(), "tuning_cents": tuning * 100,
            "candidates": candidates[:4], "tonal": tonal,
            "concentration": float(1 - entropy), "gap": float(gap)}


def summarize_tonality(segments: list[dict]) -> dict:
    if not segments:
        return {"key": "unknown", "mode": "unknown", "key_candidates": [],
                "key_reliability": 0., "key_curve": [], "tuning_cents": None}
    vector = np.mean([segment["chroma"] for segment in segments], axis=0)
    candidates = profile_candidates(vector)
    valid = [segment for segment in segments if segment["tonal"]]
    if not candidates or not valid:
        return {"key": "unknown", "mode": "unknown", "key_candidates": candidates[:4],
                "key_reliability": 0., "key_curve": segments,
                "tuning_cents": float(np.median([s["tuning_cents"] for s in segments]))}
    top = candidates[0]
    gap = top["correlation"] - candidates[1]["correlation"]
    mode_agreement = sum(s["candidates"][0]["mode"] == top["mode"] for s in valid) / len(valid)
    key_agreement = sum(s["candidates"][0]["key"] == top["key"] for s in valid) / len(valid)
    mode = top["mode"] if mode_agreement >= .7 else "mixed"
    key = top["key"] if key_agreement >= .7 and gap > .035 else "mixed/ambiguous"
    if len(valid) / len(segments) < .5 or top["correlation"] < .5:
        mode, key = "unknown", "unknown"
    reliability = max(0, min(1, gap * 5)) * key_agreement * len(valid) / len(segments)
    return {"key": key, "mode": mode, "key_candidates": candidates[:4],
            "key_reliability": float(reliability), "key_curve": segments,
            "tuning_cents": float(np.median([s["tuning_cents"] for s in segments]))}
