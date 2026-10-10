"""Writable per-user compilation caches for the frozen acoustic engine."""

import os
from pathlib import Path

from platformdirs import user_cache_dir

cache = Path(os.environ.setdefault("NUMBA_CACHE_DIR", str(Path(user_cache_dir("MusicAnalyzer")) / "numba")))
cache.mkdir(parents=True, exist_ok=True)
