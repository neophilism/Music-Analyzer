# Implementation and next-agent handoff

Updated 2026-10-10. The complete user-approved plan is
[DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md), already on `main`. The original plan
document is archived as [DEVELOPMENT_PLAN.docx](DEVELOPMENT_PLAN.docx). Do not replace
the approved scope with this status summary.

## Review stack

All implementation PRs are drafts stacked on their predecessor. The complete
application is on `pr16-macos-delivery`; main remains plan/documentation only.
No implementation has been merged and no release has been published.

| PR | Implementation | Current verification |
| --- | --- | --- |
| [01](https://github.com/neophilism/Music-Analyzer/pull/1) | Native architecture, model/license choice, full plan | Documentation only; no code CI |
| [02](https://github.com/neophilism/Music-Analyzer/pull/2) | Python/Qt shell, entry point, core CI | Linux + macOS green |
| [03](https://github.com/neophilism/Music-Analyzer/pull/3) | Imports, hashes, stable IDs, duplicates, SQLite | Linux + macOS green |
| [04](https://github.com/neophilism/Music-Analyzer/pull/4) | Bounded spawned workers, cache, cancel/resume | Linux + macOS green |
| [05](https://github.com/neophilism/Music-Analyzer/pull/5) | Streaming original-level LUFS, LRA, volume variability | Linux + macOS green |
| [06](https://github.com/neophilism/Music-Analyzer/pull/6) | Local tempo, variability, ambiguity, tap support | Linux + macOS green |
| [07](https://github.com/neophilism/Music-Analyzer/pull/7) | Tuned chroma, key/mode candidates, mixed/unknown | Linux + macOS green |
| [08](https://github.com/neophilism/Music-Analyzer/pull/8) | Verified pinned model installation, offline genres | Linux + macOS green; actual checkpoint also tested locally |
| [09](https://github.com/neophilism/Music-Analyzer/pull/9) | Instrumental valence/arousal/moods, segment disagreement | Linux + macOS green; accuracy gate remains open |
| [10](https://github.com/neophilism/Music-Analyzer/pull/10) | Frozen corpus/reference scales, intensity presets | Linux + macOS green |
| [11](https://github.com/neophilism/Music-Analyzer/pull/11) | Ascending buckets, DP album proposal, endpoints/pins | Linux + macOS green |
| [12](https://github.com/neophilism/Music-Analyzer/pull/12) | Native listening/review/plots, album editing | Linux + macOS green; real playback still needs listening |
| [13](https://github.com/neophilism/Music-Analyzer/pull/13) | Personal anchors, positivity corrections, intensity pairs | Linux + macOS green |
| [14](https://github.com/neophilism/Music-Analyzer/pull/14) | Verified numbered copy/move, reports, resume, undo | Linux + macOS green, including platform collision checks |
| [15](https://github.com/neophilism/Music-Analyzer/pull/15) | 200-track benchmark and independent evaluation tools | Linux + macOS green, including 200-track benchmark |
| [16](https://github.com/neophilism/Music-Analyzer/pull/16) | Mac bundle, model/package verification, notices, docs, manual signing workflow | In progress: native artifact CI must pass before ready for review |

## Earlier CI failure and repair

Development was paused after the user identified failed earlier PR checks. Every
failed check was inspected. PR02–PR13 failed on Linux because Qt could not load
`libEGL.so.1`; macOS passed. The workflow now installs the Qt/audio runtime
libraries before running the same tests. PR14's two Mac failures came from tests
assuming case/Unicode collisions would be rejected only during execution; macOS
correctly rejected them at preview. Tests now cover both rejection points and
still verify unrelated bytes, source-change rejection, and permissions.

The fixes are fast-forward commits on each affected GitHub branch, retaining the
repaired preceding branch as an ancestor. No tests were removed or disabled.
All PR02–PR15 runs subsequently passed both matrix jobs. Exact branch heads and
successful run links are recorded in
[ci-repair-2026-10-10.json](../validation/ci-repair-2026-10-10.json).
Historical red runs remain in Actions history; judge current PR checks at the
current head. The contributor rule now requires earlier checks to pass before
starting a later stage. Package builds also depend on both core jobs succeeding.

## Evidence and limits

The final analysis stack passes 76 core tests locally; its two actual-model tests
are separate from the ordinary lightweight source matrix. The pinned checkpoint
has passed actual CPU inference and a check that identical audio under opposite
names and opposite listener overrides produces identical automatic analysis.
Loudness is compared independently against DeMan/reference BS.1770 and FFmpeg;
tempo uses stable clicks and ramps, and mode uses tuned chord fixtures. Sequencing
has brute-force checks for small cases. Export tests inject interruptions around
publication, source removal, prior-output backup, recovery, and undo.

[batch-200-linux.json](../validation/batch-200-linux.json) records 200 unique 12.5 s
WAV/FLAC/AIFF/OGG fixtures (50 each), one worker, cancellation after five saved
tracks and restart of the remaining 195. Analysis including restart took 18.95 s;
cached rerun 0.97 s; scoring/order 0.047 s; verified 200-file export 3.28 s. Largest
parent/individual child RSS was 489.5 MiB, not aggregate memory. These are short
synthetic acoustic fixtures with models disabled. Manual fixture labels exercise
sequencing/export mechanics; they are not predictions or listening-quality data.
Both platforms also publish fresh benchmark reports as CI artifacts.

PR16 adds an actual frozen-executable verification: native GUI, spawned worker,
model outputs offline, project close/reopen, album order, and verified two-file
export. Synthetic listener assignments are explicitly limited to this smoke
test's ordering/export step. Linux frozen model inference/export has passed;
final Mac reports will be recorded after native CI. Installing a missing model
asset through the frozen CLI checks certificate handling separately from offline
inference. Do not claim a native Mac pass until the workflow evidence is present.

The following remain external release gates: recording-disjoint held-out genre,
valence and mood evaluation; intensity listening pairs; actual quiet piano/metal
anchors; full-length 100–200-track runtime/memory on a 16 GB Mac; actual audio
playback/appearance/accessibility checks; final linked-library notice/source and
replacement audit; Apple signing/notarization and clean-device Gatekeeper checks.
The user has not supplied recordings, listener annotations, or Apple credentials.
Conditional PR17–18 require evidence that the baseline is inadequate plus cleared
labeled data. They have not been fabricated or automatically activated.

## Where to work

| Area | Modules |
| --- | --- |
| Domain, project and import | `domain.py`, `project.py`, `audio.py` |
| Cache and spawned analysis | `jobs.py`, `engine.py` (algorithm version 6) |
| Acoustic measurements | `loudness.py`, `rhythm.py`, `tonality.py` |
| Learned interpretation | `models.py`, `emotion.py`, `resources/clap_manifest.json` |
| Scores, personal fitting and order | `scoring.py`, `calibration.py`, `sequencing.py` |
| Native desktop | `app.py`, `window.py`, `ui_support.py` |
| Export and recovery | `exporting.py`; `docs/EXPORT_RECOVERY.md` |
| Benchmark/held-out evaluation | `benchmark.py`, `evaluation.py`; `docs/EVALUATION.md` |
| Frozen delivery | `package_check.py`, `packaging/`, `.github/workflows/` |

Use the setup/check commands in README. Pin and verify the existing checkpoint;
do not fetch arbitrary model revisions. Preserve original-level measurements and
immutable automatic results. Never infer mood from filenames, tags, lyrics,
major/minor, or a hand-written tempo rule. Review unknown outputs rather than
turning absent model results into synthetic positive/negative assignments.

Before merging, verify all current checks. Merge numeric order with merge commits
so the stack keeps its shared ancestry. Avoid squash/rebase unless deliberately
restacking dependent PRs. Before release, complete the
[Mac checklist](MAC_RELEASE_CHECKLIST.md) and update this evidence, the PR body,
and [EVALUATION.md](EVALUATION.md). Keep the complete plan in the repo for the next
agent regardless of whether PRs are still open or have been merged.
