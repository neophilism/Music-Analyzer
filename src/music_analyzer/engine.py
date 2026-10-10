"""Worker-only analysis. No Qt objects or project connections cross processes."""

import hashlib
import json
from pathlib import Path

import numpy as np

from music_analyzer import ANALYSIS_VERSION
from music_analyzer.audio import decoded_audio, file_hash, iter_audio_chunks
from music_analyzer.domain import AnalysisSettings


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
    square_sum, sample_count, peak = 0.0, 0, 0.0
    with decoded_audio(source, options.ffmpeg_path) as audio:
        for start, data in iter_audio_chunks(audio, options.chunk_seconds):
            if cancel.is_set():
                raise AnalysisCancelled()
            square_sum += float(np.sum(data.astype(np.float64) ** 2))
            sample_count += data.size
            peak = max(peak, float(np.max(np.abs(data))))
            # At most 2000 envelope bins, irrespective of recording duration.
            bin_size = max(1, int(audio.frames / 2000))
            for offset in range(0, len(data), bin_size):
                waveform.append([start + offset / audio.samplerate,
                                 float(np.max(np.abs(data[offset:offset + bin_size])))])
            progress(min(0.98, (start + len(data) / audio.samplerate) / track["duration"]), "Audio measurements")
    if file_hash(source) != track["sha256"]:
        raise ValueError("Source changed while it was being analyzed; the result was discarded.")
    rms = np.sqrt(square_sum / max(sample_count, 1))
    return {"duration": track["duration"], "rms_dbfs": float(20 * np.log10(max(rms, 1e-12))),
            "peak_dbfs": float(20 * np.log10(max(peak, 1e-12))), "waveform": waveform,
            "analysis_version": ANALYSIS_VERSION, "warnings": ["Acoustic feature pipeline is being established."]}
