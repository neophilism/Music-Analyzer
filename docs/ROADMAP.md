# Approved development and review sequence

Each numbered stage is a separate commit and review branch. Branches are stacked
on their predecessor; merge from 01 to 16. They do not publish a release or merge
the implementation into the default branch automatically.

| PR | Scope | Validation |
| --- | --- | --- |
| 01 | Empty-repository audit, native architecture, model/license comparison | Pinned upstream metadata; explicit release gates |
| 02 | Python/Qt foundation, CI, initial native package | Headless launch; Mac packaging workflow |
| 03 | Import, identities, hashes, duplicates, SQLite projects | Reopen, relocation, malformed files, overrides |
| 04 | Resumable bounded spawned workers, cache, progress, cancel | Failure isolation and restart |
| 05 | Streaming LUFS, short-term curve, LRA, RMS, crest | Independent FFmpeg/reference measurements |
| 06 | Tempo windows, ambiguity, variability, tap correction | Click tracks, ramps, silence |
| 07 | Key/mode candidates and uncertainty | Tuned major/minor chords, unknown inputs |
| 08 | Model installation/provenance, local CLAP genres | Verified assets, offline inference |
| 09 | Valence/arousal and instrumental mood candidates | Segments, disagreement, review flags, no fake probabilities |
| 10 | Frozen corpus/reference scales and intensity presets | Equal/missing/extreme values, all-negative corpus |
| 11 | Two ascending groups, album DP, endpoints, pins | Exhaustive small cases, unequal groups, deterministic ties |
| 12 | Native table, inspector, audio player, plots, album editing | Headless UI interactions and macOS manual checklist |
| 13 | Personal anchors, preferences, pairwise calibration | Calibration independence and persistence |
| 14 | Numbered copy/move, reports, preview, recovery, undo | Byte integrity, collisions, interruption, conflict-aware undo |
| 15 | End-to-end/200-track fixture benchmarks and evaluation tools | Cache, bounded workers, export completeness, measured timing |
| 16 | Mac packaging, release gates, docs and notices | Mac CI, offline model smoke, optional signing/notarization |
| 17* | External labeled instrumental data/license audit | Conditional on inadequate baseline and data availability |
| 18* | Supervised compact heads and calibration | Conditional; independent held-out listening evaluation |

## Release gates and honest reporting

- Integrated LUFS within 0.2 LU, LRA within 0.5 LU of the independent reference.
- Stable synthetic BPM within 1 BPM; ramp regions within 5% where confident.
- Semantic valence agreement target 80% on clear held-out instrumental examples;
  mood-family target 75%, with abstention coverage and genre-wise errors reported.
- Intensity preference target 80% on held-out listening pairs. Anchor recordings
  must actually be provided and measured before claiming Clair de Lune <10 and
  Useless Sacrifice >90 for a particular corpus/profile.
- 200 tracks: no lost project state, bounded process count and memory, responsive
  cancel, cached scoring/order below 2 seconds on the documented benchmark system.
- Real music, listening quality, Mac playback, packaged model inference, and
  16 GB Apple Silicon memory/runtime need external audio and a Mac runner. Synthetic
  fixtures verify implementation but cannot satisfy those quality gates.
- The evaluation tool splits calibration examples from held-out examples by
  recording identity. A target is never presented as an achieved accuracy.
