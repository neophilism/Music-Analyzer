# Model and dependency audit

Exact upstream assets are pinned in the model manifest in the application.

| Candidate | Upstream terms | Decision |
| --- | --- | --- |
| `laion/larger_clap_music` | Model card metadata Apache-2.0; Transformers Apache-2.0; Torch BSD-3-Clause | Default music-specific local inference baseline; CPU first |
| `laion/clap-htsat-unfused` | Model metadata Apache-2.0 | General-audio comparison candidate; not the default |
| Music2Emo / MERT | Head/repository permissive terms do not override MERT's CC-BY-NC-4.0 encoder | Not distributed as the default open-source model |
| MTG Essentia models | Checkpoint-specific noncommercial Creative Commons terms; Essentia code AGPL | Not bundled; code license and weight licenses are separate |
| Compact supervised heads on CLAP embeddings | Depends on licenses of each training/evaluation recording and its labels | Conditional PRs 17–18; do not invent training data |

The CLAP model card declares Apache-2.0, but that does not establish ownership of
every upstream training recording or guarantee accuracy on this user's music.
We retain the model card and attribution and state these limitations. Its raw
similarities and prompt-derived scales are not calibrated probabilities.

Sources checked on 2026-10-10:

- <https://huggingface.co/laion/larger_clap_music>
- <https://huggingface.co/laion/larger_clap_music/tree/a0b4534a14f58e20944452dff00a22a06ce629d1>
- <https://github.com/LAION-AI/CLAP> (code CC0-1.0)
- <https://huggingface.co/m-a-p/MERT-v1-95M>
- <https://github.com/AMAAI-Lab/Music2Emotion>
- <https://essentia.upf.edu/models.html>
- <https://essentia.upf.edu/licensing_information.html>
- <https://tech.ebu.ch/publications/tech3342>
- <https://librosa.org/doc/0.11.0/>
- <https://doc.qt.io/qtforpython-6/deployment/index.html>
- <https://pyinstaller.org/en/stable/usage.html>

The deployment notices must include actual installed dependency licenses, not
just this overview. NumPy/SciPy/librosa/SoundFile use permissive licenses, Qt and
PySide6 require LGPL compliance, libsndfile is LGPL, and optional FFmpeg has a
build-dependent license. Source and dynamic-library replacement instructions
accompany packaged builds. Dependency/model license inspection is a release gate.
