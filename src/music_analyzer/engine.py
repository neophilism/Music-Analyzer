"""Worker-only analysis. No Qt objects or project connections cross processes."""

import hashlib
import json
from pathlib import Path

import numpy as np

from music_analyzer import ANALYSIS_VERSION
from music_analyzer.audio import decoded_audio, file_hash, iter_audio_chunks
from music_analyzer.domain import AnalysisSettings
from music_analyzer.emotion import summarize_emotion
from music_analyzer.loudness import LoudnessMeter
from music_analyzer.models import get_backend, model_identity, summarize_genres
from music_analyzer.rhythm import mono_resample, summarize_tempo, tempo_windows
from music_analyzer.tonality import analyze_tonal_segment, summarize_tonality


class AnalysisCancelled(Exception):
    pass


def cache_key(sha256: str, settings: AnalysisSettings, model_identity: str = "none") -> str:
    values = settings.to_dict()
    for field in ("workers", "device", "ffmpeg_path"):
        values.pop(field)
    return hashlib.sha256(json.dumps(
        {"audio": sha256, "settings": values, "engine": ANALYSIS_VERSION, "model": model_identity},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def analyze_track(track: dict, settings: dict, model_directory: str, cancel, progress) -> dict:
    options = AnalysisSettings(**settings)
    options.validate()
    source = Path(track["path"])
    if file_hash(source) != track["sha256"]:
        raise ValueError("Source content changed since import. Remove and reimport this recording.")
    waveform = []
    tempos, acoustic_features, tonal_segments = [], [], []
    previous = np.zeros(0, dtype=np.float32)
    model_segments, warnings = [], []
    with decoded_audio(source, options.ffmpeg_path) as audio:
        meter = LoudnessMeter(audio.samplerate, audio.channels)
        for start, data in iter_audio_chunks(audio, options.chunk_seconds):
            if cancel.is_set():
                raise AnalysisCancelled()
            meter.feed(data)
            mono = mono_resample(data, audio.samplerate, options.acoustic_rate)
            context = np.concatenate([previous, mono])
            local, features = tempo_windows(context, start - len(previous) / options.acoustic_rate,
                                            options.acoustic_rate)
            tempos.extend(local)
            acoustic_features.append(features)
            tonal = analyze_tonal_segment(mono, start, options.acoustic_rate)
            if tonal:
                tonal_segments.append(tonal)
            previous = mono[-round(options.overlap_seconds * options.acoustic_rate):]
            # At most 2000 envelope bins, irrespective of recording duration.
            bin_size = max(1, int(audio.frames / 2000))
            for offset in range(0, len(data), bin_size):
                waveform.append([start + offset / audio.samplerate,
                                 float(np.max(np.abs(data[offset:offset + bin_size])))])
            progress(min(.55, .55 * (start + len(data) / audio.samplerate) / track["duration"]), "Audio measurements")
        if options.model_enabled and model_directory:
            progress(.55, "Loading verified local model")
            backend = get_backend(model_directory, options.device)
            for start in np.arange(0, track["duration"], options.model_stride_seconds):
                if cancel.is_set():
                    raise AnalysisCancelled()
                audio.seek(round(start * audio.samplerate))
                data = audio.read(round(10 * audio.samplerate), always_2d=True, dtype="float32")
                duration = len(data) / audio.samplerate
                if duration < .5 or not np.isfinite(data).all():
                    continue
                mono = mono_resample(data, audio.samplerate, 48000)
                rms = float(np.sqrt(np.mean(mono ** 2)))
                if rms > 1e-6:
                    if options.model_profile == "gain-normalized":
                        mono = mono * (.1 / rms)
                    model_segments.append({"time": float(start), "duration": duration,
                                           "scores": backend.infer(mono)})
                progress(.55 + .44 * min(1, (start + duration) / track["duration"]), "Local genre and mood model")
        else:
            warnings.append("Genre and emotion need the optional local model. Install it and reanalyze, or enter reviewed values.")
    if file_hash(source) != track["sha256"]:
        raise ValueError("Source changed while it was being analyzed; the result was discarded.")
    features = {key: float(np.mean(values)) if (values := [row[key] for row in acoustic_features if row[key] is not None]) else None
                for key in ("onset_rate", "density_raw")}
    return {**meter.finish(), **summarize_tempo(tempos), **summarize_tonality(tonal_segments), **features,
            **summarize_genres(model_segments), "model_segments": model_segments,
            **summarize_emotion(model_segments, track["duration"]),
            "model_identity": model_identity() if model_segments else None,
            "duration": track["duration"], "waveform": waveform,
            "analysis_version": ANALYSIS_VERSION, "warnings": warnings}
