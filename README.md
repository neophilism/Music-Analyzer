# Music Analyzer

A native desktop workspace for arranging instrumental music by measured dynamics,
rhythm, and perceived emotion. Audio stays on your computer; there is no browser
or server.

## Download and start using the app

**Apple Silicon Mac, macOS 14 or later. No separate Python installation needed.**
Intel Macs are not supported by this review package.

[Download the verified Mac review build](https://github.com/neophilism/Music-Analyzer/actions/runs/38070930610/artifacts/11676882107)
(about 238 MB; sign into the GitHub account with access to this private repository).
If the direct link does not open, use the
[verified build page](https://github.com/neophilism/Music-Analyzer/actions/runs/38070930610)
and select **macos-arm64-review** under **Artifacts**.

This is the build of merged commit `50b0c3cb11d8934c3123932e3bb458c86518c0a4`.
Linux/macOS core tests, the macOS 14 package check, and the separate macOS 15
clean-install/offline-model check all passed in that run. The artifact expires
on November 9, 2026; retain your downloaded copy. Later builds must be verified
against their own source commit and checks rather than assumed equivalent.

Unzip the download, then unzip **Music-Analyzer-macos-arm64-unsigned-review.zip**
inside it. Move **Music Analyzer.app** to **Applications** and open it. The model
weights are installed separately using the app's **Local model...** button.

**[Installation, first album, and troubleshooting](docs/GETTING_STARTED.md)**

The application is ad-hoc signed, **not Apple Developer ID signed or notarized**.
The getting-started guide explains Apple's per-app opening process and when to
stop rather than override a warning. Do not disable Gatekeeper globally.
This is a working review build for evaluation, not a claim that every release
quality gate is complete. See the [Mac checklist](docs/MAC_RELEASE_CHECKLIST.md).

## Arrange an album

1. Create a project through **File > New project**. Projects save analysis and
   edits automatically in a local `.ma-project` SQLite file. **Save project as**
   creates a backup copy.
2. Choose **Local model... > Install / verify model** once (about 780 MB). Genre
   and emotion need this model; acoustic measurements work independently.
   Subsequent inference is offline. Preferences offers full or sampled model
   coverage, CPU or optional Apple MPS, and an explicit FFmpeg executable path.
3. Add files or drag a folder onto the window, then choose **Analyze**. Start
   with a few WAV or FLAC copies before a large batch. Import supports WAV,
   AIFF, FLAC, MP3, OGG, OPUS, AAC, and M4A, subject to codec support. AAC/M4A
   and other unsupported codecs need a separately installed FFmpeg CLI.
   Mono and stereo are supported; multichannel files report an explicit error.
   Cancel/reopen resumes incomplete work; repeated audio uses a content-and-settings
   cache. Duplicate recordings can be retained or skipped.
4. Review the table and inspector: LUFS, LRA, volume spread, BPM and its local
   variation, key/mode candidates, genre candidates, positivity, and mood.
   Listen with optional playback loudness matching. Correct estimates and choose
   positive/negative folders for uncertain tracks. Automatic results remain
   separate. Use **Accept suggested assignments** only after reviewing them.
5. Choose **Recalculate scales** when changing the corpus or profile. Dynamics
   and tempo are 0-100 comparisons. Positivity is 0 negative, 50 neutral, 100
   positive; its separate corpus rank does not assign folders. Reference anchors
   can map actual quiet/dense recordings to dynamics 5/95 and learn preferences
   from reviewed corrections and listening pairs.
6. In **Album order**, select perceived intensity or **Dynamics + tempo**.
   Build the proposal, drag tracks, or pin positions. The automatic rising-group
   mode preserves increasing intensity within each valence group and explains
   conflicts between alternation, endpoints, unequal groups, and pins.
7. Preview **Export** and choose copies for the first trial; move is an explicit
   separate choice. Files receive global album positions, such as
   `001_original-name.wav`. The output includes **Positive Valence** and
   **Negative Valence** folders, a combined M3U8 playlist, CSV/JSON reports,
   and a hash manifest. **Tools > Recover export / Undo export** uses the journal.

Read [export recovery](docs/EXPORT_RECOVERY.md) before relocating or deleting
journals. Audio is copied byte for byte, hash checked, and published without
silently overwriting unrelated files.

## What the scores mean

Dynamics emphasizes original-level average loudness, louder passages, and sustained
energy. LRA and volume spread remain separate: a quiet piece with a large crescendo
is not automatically more intense than dense metal. Tempo retains half/double-time
ambiguity. Mode may be major, minor, mixed, or unknown; it does not decide emotion.

Genre and mood use the pinned music CLAP model with generic instrumental prompts.
The model sees audio, never filenames, tags, or lyrics. Similarity and reliability
indicators are not probabilities. Default intensity weights are 40% dynamics,
25% rhythmic drive, 20% estimated arousal, and 15% acoustic density. The simple
profile averages dynamics and tempo, preserving the same ordering as their sum.

Synthetic measurements and 200-track pipeline fixtures have passed. Held-out
instrumental listening accuracy, actual Clair de Lune/Useless Sacrifice anchor
scores, real full-length 16 GB Mac performance, manual playback/accessibility,
linked-library replacement, and Apple signing remain separate unverified gates.
See [evaluation](docs/EVALUATION.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md).
An uncertain prediction needs listening and review, not a fabricated confident label.

## Develop and build

PR01-PR16 are merged. Use `main` for development; the instructions above do not
require cloning the source or installing development dependencies.

```bash
git clone https://github.com/neophilism/Music-Analyzer.git
cd Music-Analyzer
git checkout main
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,models]'
python -m music_analyzer
```

Core checks and the pipeline benchmark:

```bash
python -m ruff check .
QT_QPA_PLATFORM=offscreen python -m pytest
python -m music_analyzer.benchmark --output benchmark-output/local-200
```

Actual model checks require an explicitly installed pack:

```bash
python -m music_analyzer --install-model model-pack
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MUSIC_ANALYZER_TEST_MODEL=model-pack python -m pytest tests/test_models.py
```

Build on an Apple Silicon Mac; Linux cannot produce the macOS application:

```bash
python packaging/collect_notices.py
python -m PyInstaller --clean --noconfirm packaging/desktop.spec
"dist/Music Analyzer.app/Contents/MacOS/MusicAnalyzer" --verify-package --model-directory "$PWD/model-pack" --verification-report build/frozen-verification.json
```

The verified Mac package and optional signing workflows select Python 3.12.10.
Each build retains resolved dependency versions, third-party notices, archive hashes,
and verification reports. Preserve them with the source commit. Signing/notarization
is a separate manual workflow requiring configured Apple credentials; it creates
a review artifact without publishing a GitHub release.

## Plan and contributor handoff

- [Complete approved plan, including every PR](docs/DEVELOPMENT_PLAN.md)
- [Roadmap and acceptance gates](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md) and [model provenance](docs/MODELS.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Third-party notices and replacement guidance](docs/THIRD_PARTY.md)

Application source is MIT licensed. Dependencies and weights retain their own licenses.

## End-to-End Everywhere progress

The canonical [security/e2eesa-status.json](security/e2eesa-status.json) records standard implementation, complete testing and independent expert review separately. Engine Room reads it automatically from GitHub. All initial stages are pending; existing profile locks and approved decisions remain authoritative. Read [adoption and independent-account instructions](docs/E2EESA_ADOPTION.md), and run `python3 scripts/validate_e2eesa_status.py`. Record validation does not establish product security or certification.
