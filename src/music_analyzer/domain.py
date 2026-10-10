"""Serializable project entities; automatic results and edits stay separate."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Track:
    id: str
    path: str
    original_name: str
    sha256: str = ""
    size: int = 0
    mtime_ns: int = 0
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    status: str = "pending"
    error: str = ""
    duplicate_of: str | None = None
    analysis: dict[str, Any] = field(default_factory=dict)
    overrides: dict[str, Any] = field(default_factory=dict)
    reviewed: bool = False
    excluded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def value(self, field_name: str, default: Any = None) -> Any:
        return self.overrides.get(field_name, self.analysis.get(field_name, default))


@dataclass
class AnalysisSettings:
    acoustic_rate: int = 22050
    chunk_seconds: float = 30.0
    overlap_seconds: float = 3.0
    model_enabled: bool = True
    model_stride_seconds: float = 10.0
    model_profile: str = "original"
    workers: int = 1
    device: str = "cpu"
    ffmpeg_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> None:
        if not 1 <= self.workers <= 2:
            raise ValueError("Choose one or two workers; each model worker uses additional memory.")
        if self.acoustic_rate != 22050 or not 10 <= self.chunk_seconds <= 60:
            raise ValueError("Acoustic rate must be 22050 Hz; chunks must be 10–60 seconds.")
        if not 0 <= self.overlap_seconds < self.chunk_seconds / 2:
            raise ValueError("Chunk overlap must be less than half a chunk.")
        if not 10 <= self.model_stride_seconds <= 120:
            raise ValueError("Model stride must be between 10 and 120 seconds.")
        if self.model_profile not in {"original", "gain-normalized"}:
            raise ValueError("Unknown model analysis profile.")
        if self.device not in {"cpu", "mps"}:
            raise ValueError("Use CPU or optional Apple MPS.")
