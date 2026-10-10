# Music Analyzer

A native desktop workspace for arranging instrumental music by measured dynamics,
rhythm, and perceived emotion. macOS is the first supported distribution target.

Analyze 100–200 instrumental tracks, review uncertain interpretations by listening,
and export a proposed album with numbered files in **Positive Valence** and
**Negative Valence** folders. Audio stays on your computer. This is a Python/Qt
desktop application with no browser or server.

## Get the application

Initial package target: **Apple Silicon, macOS 14 or later**. The implementation
is in stacked review PRs; `main` contains the approved plan until those PRs are
merged. The complete application is on `pr16-macos-delivery`.

The **Tests** workflow creates an unsigned review `.app` only after Linux and
macOS core checks pass. Download `macos-arm64-review` from the successful run for
the reviewed commit; extract the ZIP and move **Music Analyzer.app** to
Applications. Review builds are not signed for public distribution. Follow the
[Mac checklist](docs/MAC_RELEASE_CHECKLIST.md) for verification and release status.

## Arrange an album

1. Create a project through **File → New project**. Projects save analysis and
   edits automatically in a local `.ma-project` SQLite file. **Save project as**
   creates a backup copy.
2. Choose **Local model → Install / verify model** once (about 780 MB). Genre and
   emotion need this model; acoustic measurements work independently. Subsequent
   inference is offline. Preferences offers full or sampled model coverage, CPU
   or optional Apple MPS, and an explicit FFmpeg executable location.
3. Add files or drag a folder onto the window, then choose **Analyze**. Import
   supports WAV, AIFF, FLAC, MP3, OGG, OPUS, AAC, and M4A, subject to codec support.
   AAC/M4A and other unsupported codecs need a separately installed FFmpeg CLI.
   This initial version analyzes mono and stereo; multichannel files report an
   explicit error. Cancel/reopen resumes incomplete work; repeated audio uses a
   content-and-settings cache. Duplicate recordings can be retained or skipped.
4. Review the track table and inspector: LUFS, volume spread and LRA, BPM and local
   tempo variation, key/mode candidates, genre candidates, positivity, and mood.
   Listen with optional playback loudness matching. Correct the estimates or
   choose the positive/negative folder for neutral, mixed, or uncertain tracks.
   Automatic results remain available separately from your corrections. Use
   **Accept suggested assignments** only after reviewing the suggestions.
5. Choose **Recalculate scales** when changing the corpus or profile. Dynamics
   and tempo are 0–100 comparisons. Positivity is 0 negative, 50 neutral, 100
   positive; its separate corpus rank does not assign folders. **Tools → Reference
   anchors** can map your actual quiet and dense recordings to dynamics 5 and 95
   and learn personal preferences from reviewed corrections and listening pairs.
6. In **Album order**, use the recommended perceived-intensity profile or
   **Dynamics + tempo**. Build the proposal, drag tracks, or pin positions. Each
   valence group rises in intensity. The proposal prefers a positive opening and
   a negative/positive finale, explaining conflicts with unequal groups or pins.
7. Preview **Export**. Copy is the default; move is available explicitly. Padding
   makes folder name sorting match global album positions, for example
   `001_original-name.wav`. Each group is ascending in intensity. The output also
   includes a combined M3U8 playlist, analysis CSV/JSON, and a hash manifest.
   **Tools → Recover export / Undo export** uses the retained journal.

Read [export recovery](docs/EXPORT_RECOVERY.md) before relocating or deleting
export journals. Files are copied byte for byte, hash checked, and published
without overwriting unrelated files.

## What the scores mean

Dynamics emphasizes average original-level loudness, louder passages, and sustained
energy. LRA and volume spread remain separate: a quiet piece with a large crescendo
should not automatically become more intense than dense metal. Tempo uses robust
local pulse estimates and retains half/double-time ambiguity. Mode may be major,
minor, mixed, or unknown; it does not determine emotion.

Genre and mood use the pinned music CLAP model with generic instrumental prompts.
The model sees sound, never filenames, tags, or lyrics. Similarity and reliability
indicators are not probabilities. The default intensity weights are 40% dynamics,
25% rhythmic drive, 20% estimated arousal, and 15% acoustic density. The simpler
profile averages dynamics and tempo, preserving the same ordering as their sum.

Synthetic measurements and the 200-track pipeline benchmark pass. Held-out
instrumental listening accuracy and the requested Clair de Lune/Useless Sacrifice
reference scores still need actual cleared recordings and listener labels. See
[evaluation](docs/EVALUATION.md) and [implementation status](docs/IMPLEMENTATION_STATUS.md)
for evidence and outstanding release gates.

## Develop and build

Use Python 3.12 and the implementation branch while PRs are under review:

```bash
git clone https://github.com/neophilism/Music-Analyzer.git
cd Music-Analyzer
git checkout pr16-macos-delivery
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

For actual model checks, explicitly install a pack, then run offline:

```bash
python -m music_analyzer --install-model model-pack
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 MUSIC_ANALYZER_TEST_MODEL=model-pack python -m pytest tests/test_models.py
```

Build on an Apple Silicon Mac; macOS binaries cannot be built on Linux:

```bash
python packaging/collect_notices.py
python -m PyInstaller --clean --noconfirm packaging/desktop.spec
"dist/Music Analyzer.app/Contents/MacOS/MusicAnalyzer" --verify-package --model-directory "$PWD/model-pack" --verification-report build/frozen-verification.json
```

Each CI build records exact installed dependencies, third-party notices, artifact
hashes, and verification reports. Preserve those with the commit to reproduce a
review build. Optional signing/notarization is a separate manually dispatched
workflow requiring the Apple credentials described in the Mac checklist; it
produces a review artifact without publishing a GitHub release.

## Plan and contributor handoff

- [Complete approved development plan, including every PR](docs/DEVELOPMENT_PLAN.md)
- [Roadmap and acceptance gates](docs/ROADMAP.md)
- [Architecture](docs/ARCHITECTURE.md) and [model provenance](docs/MODELS.md)
- [Implementation status and next-agent instructions](docs/IMPLEMENTATION_STATUS.md)
- [Third-party notices and replacement guidance](docs/THIRD_PARTY.md)

Application source is MIT licensed. Dependencies and optional weights retain
their own licenses.
