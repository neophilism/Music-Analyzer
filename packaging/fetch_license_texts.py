"""Fetch standard copyleft texts from their original publisher for distribution."""

import hashlib
import json
import urllib.request
from pathlib import Path

SOURCES = {"LGPL-3.0.txt": "https://www.gnu.org/licenses/lgpl-3.0.txt",
           "GPL-3.0.txt": "https://www.gnu.org/licenses/gpl-3.0.txt",
           "LGPL-2.1.txt": "https://www.gnu.org/licenses/old-licenses/lgpl-2.1.txt"}

if __name__ == "__main__":
    root = Path("licenses")
    root.mkdir(exist_ok=True)
    inventory = []
    for name, url in SOURCES.items():
        request = urllib.request.Request(url, headers={"User-Agent": "MusicAnalyzer/license-text-collection"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = response.read()
        if b"GNU" not in content[:500] or b"<html" in content[:500].lower():
            raise RuntimeError(f"Unexpected license response from {url}")
        (root / name).write_bytes(content)
        inventory.append({"file": name, "source": url, "sha256": hashlib.sha256(content).hexdigest()})
    (root / "sources.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
