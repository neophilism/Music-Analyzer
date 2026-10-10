# Architecture decision: local native desktop

Status: accepted by the user; macOS first, open-source distribution.

The repository was empty on 2026-10-10. There are no inherited services,
dependencies, or repository instructions to retain. The website-specific security
architecture the user linked does not apply to this desktop application.

## Application

Python 3.12, PySide6/Qt native widgets, SQLite projects, and spawned background
processes. There is no browser, HTTP server, account, or audio upload. File import,
analysis, review, album ordering, and export are one local workflow. The default
worker count is one: predictable memory use matters more than concurrent model
copies on a 16 GB Mac. Deterministic cached analysis is keyed by content hash,
analysis settings, algorithm version, model revision, and prompt version.

All measurements and automatic predictions remain immutable in their analysis
records. Overrides and review decisions are separate. Stable track identifiers
survive relocation. Duplicate recordings are visible and can either be retained
as distinct tracks or skipped. Source hashes are checked again at export.

## Audio

SoundFile handles PCM containers and the codecs supplied by its bundled libsndfile.
FFmpeg is a separately installed fallback for AAC/M4A and unsupported codecs.
It is located explicitly or on PATH; it is not downloaded or silently bundled.
No GPL FFmpeg binary is included. The distribution documents this optional codec
dependency and checks availability before starting a job. Decode to disk-backed
float PCM; original channels feed loudness, with separately resampled mono views
for acoustic and learned features. Process chunks rather than an entire album.

Loudness uses streaming BS.1770 K-weighting and gated block energies; LRA uses
EBU Tech 3342 short-term gating. FFmpeg's ebur128 is the independent check.
Librosa supplies spectral/chroma and rhythm features. Tempo estimates include
local windows, half/double-time alternatives, robust variability, and abstention.
Key estimates include competing tonic/mode candidates and unknown/mixed outcomes.

## Learned interpretation

Use the music-specific LAION CLAP model through Hugging Face Transformers with
explicit local loading. Its Apache-2.0 model metadata permits distribution of
the weights under that license. A pinned revision, asset hashes, model card,
and dependency notices travel with every installed model. Download is a separate,
visible action; subsequent inference is offline. No untrusted repository Python
is executed. The upstream checkpoint is a PyTorch state dictionary: verify its
SHA-256, then load with `weights_only=True`; never call an unsafe pickle loader.

An ensemble of instrumental genre and mood descriptions is embedded locally.
The model sees sound and generic descriptions, never track names or metadata.
Genre results are ranked similarity candidates, not mutually exclusive labels.
Mood descriptions cover positive and negative moods across low and high arousal.
Valence is an explicitly uncalibrated semantic estimate from those prototypes;
it is **not a probability**. Window disagreement, similarity margins, and audio
coverage inform review flags. Unknown is a valid result. A personal anchor
calibration can adapt scores without changing the stored model output.

CLAP is selected as a lawful, functioning baseline, not as proof of the target
accuracy. Real instrumental listening tests remain a release gate. Training the
conditional supervised heads requires lawfully usable labels and independent
evaluation data; labels cannot be fabricated from tempo, key, or genre.

## Scores and ordering

Dynamics measures, tempo, semantic valence, and perceived intensity remain distinct.
Corpus quantile mappings are snapshots, not continuously shifting rankings.
Semantic valence retains a fixed neutral midpoint even for an all-sad corpus.
Reference-calibrated dynamics is optional: importing the user's actual quiet and
dense recordings is necessary to establish the requested <10 and >90 anchors.
Within each valence bucket, intensity is ascending. Dynamic programming merges
the two ascending lists and documents unavoidable alternation/endpoint tradeoffs.
Manual orders and pins are explicit editable constraints.

## Export

Preview before applying. Copy is the default; moving originals is an explicit
choice. Use two folders, global zero-padded album positions, an M3U8 playlist,
CSV/JSON analysis, and a manifest. Stage each byte-identical copy, verify its hash,
and commit using exclusive destination creation. A durable journal records every
transition. Moving deletes a source only after its destination is verified.
Restart recovery and undo check conflicts and hashes. Unrelated files are never
overwritten. Existing numeric prefixes belonging to the original name survive.

## Mac distribution

Primary target: Apple Silicon, macOS 14 or later. PyInstaller builds a native
`.app` on a Mac, with dynamic Qt libraries, LGPL notices and replacement guidance.
The approved architecture audit includes Intel; recent PyTorch macOS wheels do
not provide a supported Intel distribution, so Intel is not advertised for this
first release. Linux CI verifies core logic and headless GUI behavior but cannot
validate macOS playback, packaging, Gatekeeper, GPU behavior, or performance.
Optional signing/notarization reads Apple credentials only in configured CI.
No release is described as signed, notarized, or benchmarked until those checks run.
