# Validation and listening evaluation

## Reproducing the batch benchmark

Run from a source checkout with Python 3.12 and the development dependencies:

```sh
python -m music_analyzer.benchmark --output benchmark-output/my-200-track-run
```

This creates 200 unique, 12.5-second acoustic fixtures in four formats, imports and
analyzes them in a bounded spawned worker, cancels after five completed recordings,
reopens the project, resumes, verifies cache reuse, scores/orders, and exports every
recording. Test-only listener edits supply valence/arousal for exercising ordering;
raw genre/emotion outputs stay unavailable. This is a mechanics/performance test,
not a listening-quality benchmark or a runtime estimate for 200 full-length songs.

Use `--source-folder /path/to/recordings` for acoustic performance on actual music.
That mode records failures and cache behavior without inventing emotion labels or
moving the supplied recordings. `--workers 2` measures the optional second worker.
Use a new empty output directory for every measured run. `report.json` records the
platform, timings, statuses, cache events, worker count, and peak memory. Child RSS
is the maximum individual child, not simultaneous aggregate memory.

The recorded Linux reference run is in `validation/batch-200-linux.json`. It
completed 200/200, retained five completed results through cancellation/reopen,
cached 200/200, and exported 200/200. Full analysis with restart took 18.95 seconds;
cached batch startup took 0.97 seconds, scoring/ordering 0.047 seconds, and export
3.28 seconds. Peak parent/individual-child RSS was approximately 490 MiB. The
operation journal was approximately 109 KiB: large analysis reports are persisted
once instead of being rewritten inside every journal update. The longest observed
poll was 0.21 seconds; native playback and interactive responsiveness still require
a Mac check. Models were disabled; model memory/runtime is measured separately.

## Evaluating automatic predictions

Analyze the recordings through the application first. Prepare independent listening
annotations using `validation/annotation-template.json`, then run:

```sh
python -m music_analyzer.evaluation \
  --project Album.ma-project \
  --labels annotations.json \
  --output validation-results/heldout.json
```

The project is opened read-only. Evaluation uses immutable automatic results,
discarding user overrides and fitted personal calibration. Annotation text never
enters audio inference, prompt generation, fitting, or normalization. Recording
hashes identify audio; `recording_id` groups alternate encodings or clips of the
same recording and prevents them crossing development/held-out splits. Intensity
pairs cannot cross those splits either. No listening annotations are needed to
analyze the user's unlabeled music.

Each annotated recording must document its instrumental status, rights, and source.
Do not commit audio without redistribution rights. Retain ambiguous/disputed
labels as `uncertain`. Valence is `positive`, `negative`, or `uncertain`. Mood
families are `joy`, `calm`, `sad`, `ominous`, `angry`, `tense`, `neutral`, or
`uncertain`; the mapping from the twelve model prototypes is explicit in
`evaluation.py`. Broad genres use the documented mapping there: classical,
soundtrack, ambient, jazz, blues, folk, country, rock, metal, punk, electronic,
hip hop, funk, soul, latin, reggae, and world. Genre recall compares the top three
distinct broad groups from the stored ranked candidates to all annotated groups.

The report includes positive/negative and mood-family agreement, classified and
accepted coverage, per-genre breakdowns, major/minor/mixed agreement, exact-key
accuracy, tempo error with and without octave equivalence, and intensity-pair
agreement. Missing or uncertain predictions remain visible. An accuracy without
its labeled count and coverage is not a release claim. Unsupervised corpus ranges
use the imported corpus; this baseline evaluation does not assess a fitted
listener preset. Keep any separate calibration evaluation's fitting recordings
out of the held-out set.

## Current quality evidence

Acoustic fixtures meet the numerical checks in the approved plan: LUFS/LRA are
compared with independent DeMan/FFmpeg measurements; click tracks and ramps test
tempo; tuned tonal fixtures test major, minor, ambiguity, and mixed mode. Actual
pinned-model tests verify offline genre/mood inference and invariance to misleading
filenames and manual tags. These establish functioning inference, not emotional
accuracy on real music.

No representative independently labeled instrumental listening corpus, owner
recordings, or actual Clair de Lune/Useless Sacrifice anchors were supplied. The
80% valence, 75% mood-family, and 80% intensity-pair targets remain **unverified**.
The model is an uncalibrated similarity baseline and the GUI requires listening
review of uncertain results. Conditional PRs 17–18 are available if measured
held-out quality is inadequate, with cleared data and independent evaluation.
Synthetic fixture performance also does not establish the planned full/faster
model budgets on a 16 GB Apple Silicon Mac.
