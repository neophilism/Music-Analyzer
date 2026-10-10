"""Pinned, verified, explicitly installed local models. Inference never uses network."""

import json
import os
import shutil
import ssl
import urllib.request
from importlib.resources import files
from pathlib import Path

import certifi
import numpy as np
from platformdirs import user_data_dir

from music_analyzer.audio import file_hash
from music_analyzer.emotion import mood_prompts

PROMPT_VERSION = "genres-moods-1"
GENRES = ["classical", "orchestral soundtrack", "solo piano", "ambient", "jazz", "blues",
          "acoustic folk", "country", "rock", "hard rock", "heavy metal", "death metal",
          "black metal", "progressive metal", "punk", "electronic dance", "techno",
          "house", "hip hop instrumental", "funk", "soul", "Latin", "reggae", "world music"]


def model_manifest() -> dict:
    return json.loads(files("music_analyzer").joinpath("resources/clap_manifest.json").read_text())


def model_identity() -> str:
    return model_manifest()["revision"] + ":" + PROMPT_VERSION


def default_model_directory() -> Path:
    return Path(user_data_dir("MusicAnalyzer", "MusicAnalyzer")) / "models" / model_manifest()["revision"]


def verify_model(directory: str | Path) -> dict:
    directory = Path(directory)
    manifest = model_manifest()
    for asset in manifest["assets"]:
        path = directory / asset["name"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != asset["size"]:
            raise ValueError(f"Missing or invalid model asset: {asset['name']}. Install the local model.")
        if file_hash(path) != asset["sha256"]:
            raise ValueError(f"Model asset hash mismatch: {asset['name']}. Reinstall the pinned model.")
    return manifest


def model_present(directory: str | Path) -> bool:
    root = Path(directory)
    return all((root / a["name"]).is_file() and (root / a["name"]).stat().st_size == a["size"]
               for a in model_manifest()["assets"])


def install_model(directory: str | Path, progress=lambda *_: None, cancelled=lambda: False):
    """Explicit download action. Existing valid assets are retained on interruption."""
    root = Path(directory).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    manifest = model_manifest()
    total = sum(a["size"] for a in manifest["assets"])
    needed = sum(a["size"] for a in manifest["assets"] if not (root / a["name"]).is_file())
    if shutil.disk_usage(root).free < needed + 100 * 1024 * 1024:
        raise ValueError("Not enough free space to install the local model (about 780 MB).")
    done = 0
    for asset in manifest["assets"]:
        path = root / asset["name"]
        if path.is_symlink():
            raise ValueError("Model installation cannot replace a symbolic link.")
        if path.is_file() and path.stat().st_size == asset["size"] and file_hash(path) == asset["sha256"]:
            done += asset["size"]
            progress(done / total, f"Verified {asset['name']}")
            continue
        partial = path.with_name(path.name + ".download")
        if partial.is_symlink():
            raise ValueError("Invalid temporary model path.")
        url = f"https://huggingface.co/{manifest['model_id']}/resolve/{manifest['revision']}/{asset['name']}"
        try:
            context = ssl.create_default_context()
            context.load_verify_locations(cafile=certifi.where())
            with urllib.request.urlopen(url, timeout=20, context=context) as response, partial.open("wb") as target:
                while block := response.read(1024 * 1024):
                    if cancelled():
                        raise InterruptedError("Model installation cancelled; verified assets were retained.")
                    target.write(block)
                    progress(min(.999, (done + target.tell()) / total), f"Downloading {asset['name']}")
                target.flush()
                os.fsync(target.fileno())
            if partial.stat().st_size != asset["size"] or file_hash(partial) != asset["sha256"]:
                raise ValueError(f"Downloaded asset failed verification: {asset['name']}")
            os.replace(partial, path)
        finally:
            partial.unlink(missing_ok=True)
        done += asset["size"]
    (root / "installation.json").write_text(json.dumps(manifest, indent=2))
    progress(1., "Local model installed and verified")


def prompts():
    genres = {genre: [f"This is an instrumental {genre} music recording.",
                    f"The sound of {genre} music, without singing.",
                    f"An instrumental piece in the style of {genre}."] for genre in GENRES}
    return {**genres, **mood_prompts()}


class ClapBackend:
    def __init__(self, directory: str | Path, device: str = "cpu"):
        import torch
        from transformers import ClapConfig, ClapModel, ClapProcessor

        self.provenance = verify_model(directory)
        self.directory = Path(directory)
        torch.set_num_threads(2)
        if device == "mps" and not torch.backends.mps.is_available():
            raise ValueError("Apple MPS is not available. Choose CPU in analysis settings.")
        self.device = device
        self.torch = torch
        self.processor = ClapProcessor.from_pretrained(str(directory), local_files_only=True)
        config = ClapConfig.from_pretrained(str(directory), local_files_only=True)
        # Pinned and hash-verified state dictionary, restricted tensor deserialization.
        state = torch.load(self.directory / "pytorch_model.bin", map_location="cpu", weights_only=True, mmap=True)
        self.model = ClapModel(config)
        self.model.load_state_dict(state, strict=True)
        self.model.to(device).eval()
        del state
        self.labels = list(prompts())
        vectors = []
        with torch.inference_mode():
            for texts in prompts().values():
                inputs = self.processor(text=texts, return_tensors="pt", padding=True).to(device)
                features = self.model.get_text_features(**inputs)
                vector = features.mean(dim=0)
                vector = vector / vector.norm()
                vectors.append(vector.cpu().numpy())
        self.text_vectors = np.asarray(vectors)

    def infer(self, samples: np.ndarray) -> dict:
        torch = self.torch
        # Each supplied window is <=10 seconds; no random long-audio cropping.
        inputs = self.processor(audio=np.asarray(samples, dtype=np.float32),
                                sampling_rate=48000, return_tensors="pt").to(self.device)
        with torch.inference_mode():
            features = self.model.get_audio_features(**inputs)[0]
            features = features / features.norm()
        similarities = self.text_vectors @ features.cpu().numpy()
        return dict(zip(self.labels, similarities.astype(float).tolist(), strict=True))


_BACKENDS = {}


def get_backend(directory, device="cpu"):
    key = (str(directory), device, PROMPT_VERSION)
    if key not in _BACKENDS:
        _BACKENDS[key] = ClapBackend(directory, device)
    return _BACKENDS[key]


def summarize_genres(segments: list[dict]) -> dict:
    if not segments:
        return {"genres": [], "genre_candidates": [], "genre_margin": None,
                "genre_status": "Local model unavailable or insufficient non-silent audio"}
    durations = [s["duration"] for s in segments]
    means = {label: float(np.average([s["scores"][label] for s in segments], weights=durations)) for label in GENRES}
    ranked = sorted(means, key=lambda label: (-means[label], label))
    candidates = [{"label": label, "similarity": means[label]} for label in ranked[:5]]
    chosen = [label for label in ranked[:3] if means[label] >= .15 and means[label] >= means[ranked[0]] - .025]
    return {"genres": chosen, "genre_candidates": candidates,
            "genre_margin": means[ranked[0]] - means[ranked[1]],
            "genre_status": "Ranked audio/text similarities; not genre probabilities"}
