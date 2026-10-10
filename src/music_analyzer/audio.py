"""Streaming decoding without altering source files."""

import hashlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import soundfile as sf

SUPPORTED_EXTENSIONS = {".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus"}


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_ffmpeg(explicit: str = "") -> str | None:
    if explicit:
        candidate = Path(explicit).expanduser()
        return str(candidate) if candidate.is_file() else None
    return shutil.which("ffmpeg") or next(
        (str(p) for p in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")) if p.is_file()),
        None,
    )


@contextmanager
def decoded_audio(path: str | Path, ffmpeg_path: str = "") -> Iterator[sf.SoundFile]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Audio file is missing: {source.name}")
    try:
        handle = sf.SoundFile(source)
    except (sf.LibsndfileError, RuntimeError):
        ffmpeg = find_ffmpeg(ffmpeg_path)
        if not ffmpeg:
            raise ValueError("This codec requires FFmpeg. Install FFmpeg or choose a WAV/AIFF/FLAC file.") from None
        with tempfile.TemporaryDirectory(prefix="music-analyzer-decode-") as directory:
            decoded = Path(directory) / "decoded.wav"
            result = subprocess.run(
                [ffmpeg, "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0",
                 "-vn", "-c:a", "pcm_f32le", "-rf64", "auto", str(decoded)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=3600,
            )
            if result.returncode:
                detail = result.stderr.decode(errors="replace")[-1000:]
                raise ValueError(f"Cannot decode audio: {detail}") from None
            with sf.SoundFile(decoded) as handle:
                yield handle
    else:
        with handle:
            yield handle


def probe_audio(path: str | Path, ffmpeg_path: str = "") -> dict:
    with decoded_audio(path, ffmpeg_path) as handle:
        if handle.frames < 1 or handle.samplerate < 8000:
            raise ValueError("Empty audio or unsupported sample rate below 8000 Hz.")
        if handle.channels not in {1, 2}:
            raise ValueError("First release supports mono/stereo; multichannel loudness needs an explicit speaker layout.")
        data = handle.read(min(handle.frames, handle.samplerate), always_2d=True, dtype="float32")
        if not np.isfinite(data).all():
            raise ValueError("Audio contains non-finite samples.")
        return {"duration": handle.frames / handle.samplerate,
                "sample_rate": handle.samplerate, "channels": handle.channels}


def iter_audio_chunks(handle: sf.SoundFile, seconds: float, overlap: float = 0.0):
    frames = max(1, round(seconds * handle.samplerate))
    step = max(1, round((seconds - overlap) * handle.samplerate))
    position = 0
    while position < handle.frames:
        handle.seek(position)
        data = handle.read(frames, always_2d=True, dtype="float32")
        if not np.isfinite(data).all():
            raise ValueError("Audio contains non-finite samples.")
        yield position / handle.samplerate, data
        position += step
