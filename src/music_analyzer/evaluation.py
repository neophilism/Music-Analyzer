"""Held-out evaluation of immutable audio results, independent of listener overrides."""

import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from music_analyzer.domain import Track
from music_analyzer.scoring import finite, make_snapshot, score_tracks

MOOD_FAMILIES = {"celebratory": "joy", "happy": "joy", "hopeful": "joy",
                 "peaceful": "calm", "tender": "calm", "neutral": "neutral",
                 "bittersweet": "sad", "melancholic": "sad", "sad": "sad",
                 "dark/brooding": "ominous", "angry": "angry", "tense": "tense"}
BROAD_GENRES = {"classical": "classical", "solo piano": "classical",
                "orchestral soundtrack": "soundtrack", "ambient": "ambient",
                "jazz": "jazz", "blues": "blues", "acoustic folk": "folk", "country": "country",
                "rock": "rock", "hard rock": "rock", "heavy metal": "metal", "death metal": "metal",
                "black metal": "metal", "progressive metal": "metal", "punk": "punk",
                "electronic dance": "electronic", "techno": "electronic", "house": "electronic",
                "hip hop instrumental": "hip hop", "funk": "funk", "soul": "soul",
                "Latin": "latin", "reggae": "reggae", "world music": "world"}


def validate_manifest(manifest):
    records = manifest.get("records", [])
    seen, groups = set(), {}
    for record in records:
        sha = record.get("sha256", "")
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha) or sha in seen:
            raise ValueError("Every annotation needs a unique lowercase SHA-256 recording hash.")
        seen.add(sha)
        if record.get("split") not in {"development", "heldout"}:
            raise ValueError("Each recording needs a development or heldout split.")
        identity = record.get("recording_id") or sha
        if identity in groups and groups[identity] != record["split"]:
            raise ValueError("Clips or encodings of one recording cannot cross evaluation splits.")
        groups[identity] = record["split"]
        if record.get("instrumental") is not True or not record.get("license") or not record.get("source"):
            raise ValueError("Document instrumental status, recording rights, and source for each annotation.")
        if record.get("valence") not in {None, "positive", "negative", "uncertain"}:
            raise ValueError("Valence labels must be positive, negative, or uncertain.")
        if record.get("mood_family") not in {None, "uncertain", *MOOD_FAMILIES.values()}:
            raise ValueError("Use a documented mood family or uncertain.")
        if any(genre not in BROAD_GENRES.values() for genre in record.get("genres", [])):
            raise ValueError("Use the documented broad-genre taxonomy.")
    by_hash = {r["sha256"]: r for r in records}
    for pair in manifest.get("intensity_pairs", []):
        lower, higher = pair.get("lower"), pair.get("higher")
        if lower == higher or lower not in by_hash or higher not in by_hash:
            raise ValueError("Intensity pairs must reference two annotated recordings.")
        if by_hash[lower]["split"] != by_hash[higher]["split"] or pair.get("split") != by_hash[lower]["split"]:
            raise ValueError("A preference pair cannot cross evaluation splits.")
    return records


def _agreement(rows, truth, prediction, clear):
    labeled = [row for row in rows if row[truth] in clear]
    classified = [row for row in labeled if row[prediction] is not None]
    accepted = [row for row in classified if not row["needs_review"]]
    return {"labeled": len(labeled), "classified": len(classified), "accepted": len(accepted),
            "accuracy": sum(r[truth] == r[prediction] for r in classified) / len(classified) if classified else None,
            "coverage": len(classified) / len(labeled) if labeled else None,
            "accepted_accuracy": sum(r[truth] == r[prediction] for r in accepted) / len(accepted) if accepted else None,
            "accepted_coverage": len(accepted) / len(labeled) if labeled else None}


def evaluate(tracks, manifest, split="heldout"):
    records = validate_manifest(manifest)
    # Discard all overrides and learned personal calibration. The annotation file
    # never enters analysis, prompts, normalization, or fitting.
    raw = [Track(**{**t.to_dict(), "overrides": {}, "reviewed": False}) for t in tracks]
    by_hash = {t.sha256: t for t in raw if t.sha256 and t.status == "complete"}
    snapshot = make_snapshot(raw)
    scored = score_tracks(raw, snapshot)
    rows = []
    for record in records:
        if record["split"] != split:
            continue
        track = by_hash.get(record["sha256"])
        analysis = track.analysis if track else {}
        valence = analysis.get("valence")
        broad = []
        for candidate in analysis.get("genre_candidates", []):
            label = BROAD_GENRES.get(candidate["label"])
            if label and label not in broad:
                broad.append(label)
        expected = record.get("genres", [])
        bpm = analysis.get("bpm")
        true_bpm = record.get("bpm")
        octave_error = min(abs(bpm * multiplier - true_bpm) / true_bpm for multiplier in (.5, 1, 2)) if finite(bpm) and finite(true_bpm) and true_bpm > 0 else None
        rows.append({"sha256": record["sha256"], "recording_id": record.get("recording_id"),
                     "available": track is not None, "needs_review": analysis.get("needs_review", True),
                     "true_valence": record.get("valence"),
                     "predicted_valence": "positive" if finite(valence) and valence >= 50 else "negative" if finite(valence) else None,
                     "semantic_valence": valence, "true_mood": record.get("mood_family"),
                     "predicted_mood": MOOD_FAMILIES.get(analysis.get("mood")),
                     "expected_genres": expected, "top3_genres": broad[:3],
                     "genre_recall": len(set(expected) & set(broad[:3])) / len(set(expected)) if expected else None,
                     "true_mode": record.get("mode"), "predicted_mode": analysis.get("mode") if analysis.get("mode") in {"major", "minor", "mixed"} else None,
                     "true_key": record.get("key"), "predicted_key": analysis.get("key"),
                     "tempo_relative_error": abs(bpm - true_bpm) / true_bpm if finite(bpm) and finite(true_bpm) and true_bpm > 0 else None,
                     "tempo_octave_relative_error": octave_error,
                     "model_coverage": analysis.get("model_coverage", 0)})
    valence = _agreement(rows, "true_valence", "predicted_valence", {"positive", "negative"})
    mood = _agreement(rows, "true_mood", "predicted_mood", set(MOOD_FAMILIES.values()))
    mode = _agreement([{**row, "needs_review": row["predicted_mode"] is None} for row in rows],
                      "true_mode", "predicted_mode", {"major", "minor", "mixed"})
    def mean(values):
        present = [v for v in values if finite(v)]
        return sum(present) / len(present) if present else None
    pairs = []
    for pair in manifest.get("intensity_pairs", []):
        if pair["split"] != split or pair.get("uncertain"):
            continue
        lower, higher = by_hash.get(pair["lower"]), by_hash.get(pair["higher"])
        a = scored.get(lower.id, {}).get("intensity") if lower else None
        b = scored.get(higher.id, {}).get("intensity") if higher else None
        pairs.append({**pair, "classified": finite(a) and finite(b), "correct": bool(finite(a) and finite(b) and a < b)})
    classified_pairs = [p for p in pairs if p["classified"]]
    intensity = {"labeled": len(pairs), "classified": len(classified_pairs),
                 "agreement": sum(p["correct"] for p in classified_pairs) / len(classified_pairs) if classified_pairs else None}
    per_genre = {}
    for genre in sorted({g for row in rows for g in row["expected_genres"]}):
        members = [r for r in rows if genre in r["expected_genres"]]
        per_genre[genre] = {"records": len(members), "valence": _agreement(members, "true_valence", "predicted_valence", {"positive", "negative"}),
                            "mood": _agreement(members, "true_mood", "predicted_mood", set(MOOD_FAMILIES.values())),
                            "genre_top3_recall": mean(r["genre_recall"] for r in members)}
    exact_keys = [r for r in rows if r["true_key"] and r["predicted_key"] not in {None, "unknown", "mixed/ambiguous"}]
    return {"split": split, "records": len(rows), "available_recordings": sum(r["available"] for r in rows),
            "annotation_rights": [{"sha256": r["sha256"], "source": r["source"], "license": r["license"]} for r in records if r["split"] == split],
            "valence": valence, "mood_family": mood, "mode": mode,
            "exact_key_accuracy": mean(r["true_key"] == r["predicted_key"] for r in exact_keys),
            "exact_key_classified": len(exact_keys), "genre_top3_recall": mean(r["genre_recall"] for r in rows),
            "tempo_relative_error": mean(r["tempo_relative_error"] for r in rows),
            "tempo_octave_relative_error": mean(r["tempo_octave_relative_error"] for r in rows),
            "intensity": intensity, "per_genre": per_genre, "rows": rows, "pairs": pairs,
            "model_identities": sorted({str(t.analysis.get("model_identity")) for t in raw}),
            "status": "No held-out listening evidence supplied" if not rows else "Measured against supplied annotations; representativeness and rights need human review",
            "targets": {"valence": .8, "mood_family": .75, "intensity_pairs": .8},
            "method": "Immutable automatic results; no overrides or fitted listener calibration. Unsupervised scales use the imported corpus."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "heldout"], default="heldout")
    args = parser.parse_args()
    project = args.project.resolve()
    with sqlite3.connect(f"file:{quote(str(project))}?mode=ro", uri=True) as connection:
        tracks = [Track(**json.loads(row[0])) for row in connection.execute("SELECT data FROM tracks")]
    result = evaluate(tracks, json.loads(args.labels.read_text(encoding="utf-8")), args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("records", "status", "valence", "mood_family", "intensity")}, indent=2))


if __name__ == "__main__":
    main()
