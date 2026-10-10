"""Worker-only analysis. No Qt objects or project connections cross processes."""

import hashlib
import json
from pathlib import Path

import numpy as np

from music_analyzer import ANALYSIS_VERSION
from music_analyzer.audio import decoded_audio, file_hash, iter_audio_chunks
from music_analyzer.domain import AnalysisSettings
from music_analyzer.loudness import LoudnessMeter
from music_analyzer.rhythm import mono_resample, summarize_tempo, tempo_windows


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
    tempos, acoustic_features = [], []
    previous = np.zeros(0, dtype=np.float32)
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
            previous = mono[-round(options.overlap_seconds * options.acoustic_rate):]
            # At most 2000 envelope bins, irrespective of recording duration.
            bin_size = max(1, int(audio.frames / 2000))
            for offset in range(0, len(data), bin_size):
                waveform.append([start + offset / audio.samplerate,
                                 float(np.max(np.abs(data[offset:offset + bin_size])))])
            progress(min(0.98, (start + len(data) / audio.samplerate) / track["duration"]), "Audio measurements")
    if file_hash(source) != track["sha256"]:
        raise ValueError("Source changed while it was being analyzed; the result was discarded.")
    features = {key: float(np.mean(values)) if (values := [row[key] for row in acoustic_features if row[key] is not None]) else None
                for key in ("onset_rate", "density_raw")}
    return {**meter.finish(), **summarize_tempo(tempos), **features,
            "duration": track["duration"], "waveform": waveform,
            "analysis_version": ANALYSIS_VERSION, "warnings": []}
