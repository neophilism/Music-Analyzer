from music_analyzer.emotion import MOODS, summarize_emotion
from music_analyzer.models import GENRES


def segment(mood, start=0, duration=10):
    scores = {f"mood:{label}": .1 for label in MOODS}
    scores[f"mood:{mood}"] = .4
    scores.update(dict.fromkeys(GENRES, .2))
    return {"time": start, "duration": duration, "scores": scores}


def test_semantic_valence_does_not_depend_on_corpus_or_key():
    positive = summarize_emotion([segment("celebratory")], 10)
    negative = summarize_emotion([segment("angry")], 10)
    calm_negative = summarize_emotion([segment("sad")], 10)
    assert positive["valence"] > 90
    assert negative["valence"] < 15 and negative["arousal"] > 90
    assert calm_negative["valence"] < 15 and calm_negative["arousal"] < 20
    assert "uncalibrated" in positive["emotion_method"]


def test_segment_disagreement_and_coverage_trigger_review():
    mixed = summarize_emotion([segment("celebratory"), segment("angry", 10)], 20)
    assert 40 <= mixed["valence"] <= 60 and mixed["needs_review"]
    assert mixed["valence_std"] > 30
    sparse = summarize_emotion([segment("happy")], 60)
    assert sparse["model_coverage"] < .5 and sparse["needs_review"]
    assert summarize_emotion([], 60)["valence"] is None
