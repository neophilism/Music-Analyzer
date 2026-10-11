> **Canonical PR work plan:** [`registry/roadmap.json`](../registry/roadmap.json). The 16 approved first-release PRs are tracked there. Optional PRs 17–18 remain conditional; the detailed plan below is preserved.

<!-- Complete text of the user-approved plan. The original DOCX is archived beside this file. -->

# Music Analyzer Development Plan

macOS desktop application for instrumental album sequencing

Approval proposal dated October 10, 2026. The proposed application analyzes 100 to 200 instrumental audio files locally, explains their intensity and perceived emotion, and produces an editable initial album order. The release will have a simple native desktop interface and an open-source codebase.

The recommendation is to combine reliable acoustic measurements with pretrained music models and a short review workflow. Preserve the requested dynamics, tempo, and positivity scales, while distinguishing musical intensity from loudness and keeping emotion independent of major or minor key. Use your tempo-plus-volume rule as one selectable ordering profile.

### Scope to approve

| Included in the first release | Result |
| --- | --- |
| Batch audio analysis | BPM and tempo changes; average loudness and loudness changes; genre candidates; major or minor mode and key candidates; mood, valence, and arousal estimates. |
| Comparison and review | Three scores from 0 to 100, confidence indicators, editable results, audio preview, reference anchors, and a frozen comparison corpus. |
| Album preparation | Two folders ordered by intensity, numbered filenames, an alternating album proposal, a playlist, and CSV and JSON reports. |
| Desktop delivery | A packaged macOS application with local processing, resumable analysis, project saving, export preview, and undo for supported file operations. |

### Decisions embodied in this plan

Target macOS first. Propose Python with PySide6 native Qt widgets, background analysis processes, and SQLite project storage. Test both Apple Silicon and Intel compatibility in PR 01 before promising the release matrix. Retain an existing sound repository architecture if it already satisfies these requirements.

The base roadmap contains 16 PRs. Two additional PRs are a defined contingency if available redistributable models fail the instrumental benchmark. PR 01 settles feasibility early; later work implements the approved behavior. Approval of this plan precedes repository implementation.

Apply your exemption from the linked website and web-app security architecture standard to this desktop application. Ordinary local-file integrity, dependency maintenance, and release signing remain part of making the application dependable.

## Measurements and stored results

Analyze the audio signal itself. Filenames, artist identities, internet lookups, and existing genre or emotion tags will not determine predictions. Existing metadata may be displayed for navigation. No lyrics, lyric retrieval, or transcription is needed.

| Measurement | Stored and displayed result |
| --- | --- |
| Tempo | Representative BPM from reliable segments; alternative half-time or double-time hypotheses; local BPM curve; robust range and relative variability; beat confidence and valid coverage. |
| Average loudness | Integrated LUFS on original channel audio, plus RMS as a secondary descriptor. Retain sample peak and true peak for diagnostics rather than using peak amplitude as average volume. |
| Loudness variation | Loudness Range in LU, short-term loudness percentiles, robust envelope spread, and crest factor. Show average, loud sections, and sustained energy separately. |
| Tonality | Dominant tonic and major or minor mode, competing relative-key candidates, segment changes, and a tonal-strength indicator. Allow modal, mixed, atonal, and uncertain results. |
| Genre | Several plausible genres or styles with relevance scores, a broad genre grouping, segment support, and an unknown result when evidence is weak. |
| Emotion | Positivity, arousal, multiple mood tags, segment agreement, and mixed or uncertain status. Keep estimated results and user edits as separate fields. |
| Project provenance | Track ID, original filename and path, content hash, duration, sample rate, channels, decoder version, model versions, score profile, corpus snapshot, and analysis coverage. |

### Analyze the whole recording

Run loudness and rhythm measurements over the full audible recording. Use the original channel signal for loudness and suitable resampled views for rhythm, tonality, and each model. Chunk long files with enough overlap to avoid boundary artifacts. Keep trailing silence and unusual sections visible in diagnostics rather than hiding them in a cropped excerpt.

Standard emotion analysis covers the recording using windows appropriate to the selected model. An optional faster mode samples stratified windows across the recording and labels its coverage. A sampled result cannot claim that an unobserved section has a particular mood. Exclude silence from model aggregation and report files too short or too silent to support a result.

BPM variability must reflect musical changes rather than alternating 80 and 160 BPM tracking errors. Resolve pulse hypotheses before computing variability, and exclude unreliable segments. For free-time or beatless music, report no stable beat instead of inventing a precise BPM. Librosa provides local-pulse analysis suited to varying tempo [2].

## Scores and reference calibration

Use three principal scales from 0 to 100, with raw measurements available in the track inspector. Keep score definitions and calibration versions in the saved project so the same analysis and profile reproduce the same order.

### Dynamics and volume

Interpret the requested dynamics score as perceived loudness and sustained sonic power. A large dynamic range means strong contrast between quiet and loud passages; it does not automatically mean high intensity. Measure Loudness Range separately using the EBU descriptor [1].

The initial composite uses 65 percent normalized average LUFS, 25 percent normalized 90th-percentile short-term loudness, and 10 percent sustained energy. Express each component on a 0 to 100 scale. Define sustained energy as the fraction of audible time above a fixed loudness threshold stored with the calibration. The average and upper percentile capture quiet versus loud sections; their relationship and the sustained fraction capture behavior across time. Inspect LRA and crest factor without blindly rewarding larger variability.

These starting weights are engineering choices to validate, not established perceptual constants. Retain the original measurements. A separate playback-adjusted intensity profile may analyze a gain-adjusted copy to reduce mastering differences; exported audio stays byte-identical.

### Tempo

Use the confidence-weighted representative pulse, with logarithmic BPM mapping before normalization. Keep onset density and rhythmic drive as additional intensity descriptors, because the felt activity of a slow heavy track and a fast delicate track can differ from BPM. Tempo variability stays an independent measurement rather than automatically increasing the tempo score.

### Within corpus comparison

Map composite dynamics and tempo values using the corpus fifth and ninety-fifth percentiles, clipping values outside that interval to 0 or 100. This reduces the influence of a single outlier and retains more distance information than rank alone. For a tiny or degenerate corpus, use a documented fallback; equal finite values receive equal comparison scores, and missing values remain missing.

Also retain a corpus percentile rank and a separate reference-calibrated score. Corpus comparison answers where a track sits among these tracks; reference calibration supports consistent readings across projects. Freeze the corpus after analysis. Adding or removing tracks creates a new comparison snapshot only when the user chooses to recalculate.

### Your two reference tracks

Treat actual recordings of Clair de Lune and Useless Sacrifice as calibration anchors, or accept equivalent recordings you supply. Target a quiet piano reference below 10 and a dense metal reference in the 90s on the reference-calibrated dynamics scale. Confirm this on audio, including nearby similar examples. Recording level and mastering affect the result; a corpus rank cannot guarantee these values in every possible corpus. The application never assigns a score merely from the track name.

## Emotion and perceived intensity

### Positivity and arousal

Positivity is an estimate of perceived valence: 0 is strongly negative, 50 is neutral or ambiguous, and 100 is strongly positive. Arousal describes activation from calm to highly energized. Preserve this semantic midpoint when normalizing positivity. An entirely sad corpus must remain negative rather than forcing its happiest member to appear strongly positive.

Provide a secondary corpus rank for positivity to satisfy comparison within the imported tracks. Keep that rank separate from the semantic score and never use it to decide the positive or negative folder. A model output is a perceptual estimate, not a measurement of how every listener will feel.

| Valence and activation | Suggested mood family |
| --- | --- |
| Positive with lower activation | Peaceful, warm, tender, contented |
| Positive with higher activation | Joyful, uplifting, celebratory, exuberant |
| Negative with lower activation | Sad, melancholic, mournful |
| Negative with higher activation | Angry, aggressive, tense |
| Mixed or uncertain evidence | Bittersweet, ominous, ambiguous, or needs review |

Use model evidence for specific labels such as angry, sad, dark, and celebratory. The quadrant is a useful organization rule, but high activation alone cannot distinguish anger from excitement. A major key is not a rule for happiness, and a minor key is not a rule for sadness. Genre also remains a descriptor rather than a rule for valence.

### Two intensity profiles

Simple profile: take the arithmetic mean of the dynamics score and tempo score. This gives the same ordering as adding the two scores and keeps the result on a 0 to 100 scale. It directly implements your proposed rule.

Recommended perceived-intensity profile: start with 40 percent dynamics and loudness, 25 percent rhythmic drive, 20 percent estimated arousal, and 15 percent acoustic density or roughness. Rhythmic drive initially combines 70 percent tempo with 30 percent onset activity. Validate the texture features and the weights against listening comparisons. Valence never increases or decreases intensity.

A slow, dense, aggressive recording can therefore rank high without an artificially high BPM. Tempo-free music can still receive an intensity estimate from available features, with the missing component and reweighting disclosed. The simple profile will similarly show when a missing tempo component changes its meaning. Use the full precision score for sorting and a rounded score only for display.

### Review and personalization

Use a neutral band, provisionally 40 to 60, plus model reliability and segment disagreement to flag tracks for review. Let users choose a folder, correct BPM, override mode or mood, and set an intensity adjustment. Keep automatic estimates intact. Optional pairwise comparisons and reference anchors tune weights without requiring the user to label the entire corpus. Confidence labels remain evidence indicators until calibrated on held-out data; similarity scores are not probabilities.

## Sequencing rules and edge cases

The two required groups are Positive Valence and Negative Valence. Sort each group from lowest to highest intensity under the selected profile. Keep this order stable when the analysis is unchanged, with a deterministic tie-breaker and optional user preferences for exact ties.

### Initial album proposal

Start with the least intense positive track and place the least intense negative track second when compatible with the finale. Prefer alternating valence as intensity rises within each group. Reserve the most intense negative track for the penultimate position and the most intense positive track for the final position. Include every selected track exactly once.

Strict alternation can conflict with the requested endpoints. With equal group sizes, starting positive and alternating throughout ends negative. For three tracks in each group, one valid endpoint-preserving proposal is P1, N1, P2, N2, N3, P3. P and N indicate valence; the number indicates increasing intensity within that group.

Unequal group sizes create additional same-valence neighbors. Intensity may also fall between neighboring tracks from different groups even when each group rises consistently. The preview shows these exceptions instead of claiming the sequence is strictly increasing overall.

### Ordering algorithm

Merge the two sorted lists with a small dynamic-programming search. Its state tracks how many items have been taken from each group and the last group used. Hard constraints preserve each group order and the feasible first two and final two positions. The objective penalizes repeated valence, large intensity drops, and abrupt jumps. Store weights and tie-break rules so results are reproducible. Two hundred tracks are small enough for this search; exhaustive permutation search is unnecessary.

Expose an endpoint-preserving default, a strict-alternation preference that relaxes endpoints when necessary, and a global-intensity preference that relaxes valence pattern. Label which requirements each mode satisfies. Preserve manual drag-and-drop edits and pinned tracks in a custom sequence. Report conflicts with automatic constraints before regenerating.

### Incomplete and unusual projects

Too few tracks in either group can make the requested beginning and finale incompatible. One negative track in a longer album cannot be both second and penultimate. Prefer the finale when these conflict, show relaxed constraints, and never duplicate or silently omit tracks. Apply the same accounting to exclusions and analysis failures.

Mixed or uncertain tracks stay in a review filter inside the application. For a two-folder export, each included track must have a bucket assignment. Users may accept the suggested assignments in one action, change individual tracks, or exclude selected tracks. The export summary accounts for every imported track and creates only the two required audio subfolders.

### Transition refinements

Use intro and outro loudness, audio similarity, or tonal compatibility only as optional refinements. They may improve listening transitions, but can conflict with your intensity goal. In the strict group-order mode, they affect exact ties or interleaving choices; any mode that permits broader reordering must say so. No crossfades or audio editing are needed for the first release.

## Desktop workflow and export behavior

### A small native interface

Use one main window. A toolbar provides Add Tracks, Analyze, Build Order, and Export. The center is a sortable track table showing filename, intensity, dynamics, tempo, positivity, mood, mode, and genre. Keep detailed acoustic units and extra columns in an inspector so the initial screen stays simple.

The inspector includes play and seek controls, a waveform, loudness and tempo curves, analyzed emotion segments, candidate genres and keys, and editable values. Provide a loudness-matched audition switch so users can compare musical character without a playback-level bias. It changes playback gain only.

A small intensity-versus-positivity plot allows selection and comparison. Positive and negative filters and a Needs Review filter make corrections quick. The album view supports drag-and-drop, pinning, and a visible intensity curve. Export preview displays final paths, names, order, exclusions, and any unresolved assignments. Support keyboard navigation, macOS shortcuts, light and dark appearances, and accessible labels.

### Two audio folders and a combined playlist

Organize This Folder moves and renames selected originals into Positive Valence and Negative Valence subfolders of the selected source folder. Export Copies produces the same structure in a chosen output directory. Recommend copies for a first trial, while fully supporting the requested in-place organization.

Default to a global one-based album number across both folders. Use the width of N, so 200 tracks are named 001_original.flac through 200_original.flac. Each folder remains increasing in intensity because album generation preserves its group order. Nonconsecutive numbers in a folder preserve the combined album positions.

Offer literal 1_ through N_ prefixes if preferred. Zero padding gives predictable lexical ordering in more tools. Preserve each original basename and extension, including existing numbers that were already part of the original name. Re-exporting a project replaces the application-added prefix once, rather than stacking prefixes.

Write album.m3u8 with relative paths so a player can reconstruct the combined album across both folders. A parent folder containing two subfolders does not itself define playback alternation. Export analysis.csv with measurements and scores, analysis.json with detailed results and provenance, and a manifest with original-to-export mappings, bucket ranks, album positions, and hashes.

### Dependable file operations

Build and display a complete operation plan before applying it. Preflight collisions, available space, path lengths, case-insensitive names, permissions, and changed source files. Never overwrite an unrelated file. Preserve file bytes and metadata embedded inside audio; there is no re-encoding or loudness processing.

Use staged operations and a durable journal for completion, recovery, and undo. A multi-file batch can stop partway through, so simulate interruption and reconcile completed steps on restart. Verify copied bytes before any cross-volume move removes its source. If a later external change makes undo unsafe, report that conflict and retain recoverable files.

## Architecture and approaches considered

Proposed stack: a pinned supported Python version, PySide6 native Qt widgets, NumPy and SciPy, librosa, soundfile and an audited FFmpeg build, an independently checked loudness implementation, and a model backend using PyTorch or ONNX Runtime when model compatibility permits. Package a real .app; no browser window or local HTTP server is necessary. Qt supports desktop deployment [6].

Run decoding, acoustic analysis, and model inference in bounded background processes. Keep GUI work on its main thread. Persist project data and operation journals in SQLite, with large cached arrays in a project cache. Cache by content hash plus decoder, algorithm, model, and parameter versions. Recalibration or reordering should reuse analysis rather than decode every file again.

| Approach | Decision and reason |
| --- | --- |
| Acoustic rules alone | Use for loudness, tempo, and tonal features. They cannot reliably provide the requested genre and nuanced emotional labels. |
| Permissive music CLAP | First candidate for the redistributable default. Its music checkpoint advertises Apache 2.0 and supports audio-to-description similarity. Validate instrumentals and calibrate score meaning [3]. |
| Specialized music models | Benchmark dedicated genre and valence or mood models. Essentia has relevant models, but checkpoints have distribution restrictions. Music2Emo is a useful candidate whose MERT dependency has a noncommercial license [4, 5]. |
| Train supervised heads | Contingency over permitted pretrained embeddings using cleared external labeled data. The user corpus can remain unlabeled. Training from scratch is a larger project. |
| Large audio language models | Consider only if smaller models fail. Their size, runtime, and variable text outputs make them a weaker first desktop dependency. |
| Cloud analysis services | Could supply predictions, but add uploads, vendor dependency, and ongoing cost. Keep the approved first release local. |
| SwiftUI or webview shell | SwiftUI is a viable Mac-only alternative with a bridge to the audio engine. Python with native Qt reduces that integration work. A webview shell offers less benefit for this request. |

Code and model licenses are separate. Do not call an application fully open source merely because its source is public while required weights prohibit some uses. Choose a redistributable default after inspecting the exact checkpoint and dependency licenses. Keep restricted optional research packs separate and clearly labeled; converting formats does not remove restrictions.

Bundle a verified model pack or provide an explicit download and local-import workflow. Once installed, analysis works offline. Pin source revisions and weight hashes. Avoid unreviewed remote code and arbitrary checkpoint execution. CPU execution must work; Mac GPU acceleration is an optimization, with a tested fallback.

## PR roadmap for foundations

### PR 01 Validate models and record architecture

This is the first PR.

Audit the provided repository, its contribution rules, and existing licenses. Compare the permissive music CLAP candidate with dedicated mood, valence, and genre models on representative instrumentals. Record checkpoint and dependency rights, packaging constraints, Mac runtime, memory, output coverage, and a proposed minimum macOS version. Prototype packaged inference early.

Acceptance: An architecture decision names usable models for every learned output, distinguishes similarities from probabilities, and records a lawful distribution path. Benchmark against held-out listening judgments. If quality is inadequate, activate PRs 17 and 18 or present a concrete scope revision before committing the remaining implementation.

### PR 02 Create the native application foundation

Depends on PR 01.

Build the native Qt application shell, settings, logging, domain interfaces, model registry contracts, and a repeatable development setup. Establish CI with meaningful core checks and a minimal Mac package smoke test. Separate GUI, analysis, sequencing, and file operations.

Acceptance: A minimal .app opens on a clean supported Mac without a developer Python installation. The GUI remains responsive while a sample worker runs. The approved repository license and dependency notices are retained.

### PR 03 Import tracks and save projects

Depends on PR 02.

Add file and folder selection, drag-and-drop, optional recursive import, format probing, stable track identities, metadata display, duplicate handling, SQLite migrations, and project reopen and relink behavior. Support WAV, AIFF, FLAC, MP3, AAC or M4A, and Ogg where the verified decoder supports them.

Acceptance: A mixed 200-file project imports and reopens with the same identities. Duplicate audio and duplicate names are distinct cases. Unsupported, missing, or corrupt files show per-file status instead of aborting the project.

### PR 04 Run resumable analysis jobs

Depends on PR 03.

Implement bounded decoding and analysis workers, chunked long-file handling, progress and ETA, cancellation and resume, per-stage failures, versioned caches, and model loading once per worker. Prevent simultaneous exports or analyses from racing over the same project.

Acceptance: Cancellation, a killed worker, and an application restart preserve completed results and can resume remaining jobs. Repeating unchanged analysis uses the cache. Memory does not grow with the total decoded corpus.

## PR roadmap for acoustic analysis

### PR 05 Measure loudness and dynamic variation

Depends on PR 04.

Implement original-channel integrated LUFS, short-term loudness, EBU Loudness Range, RMS, crest factor, loudness percentiles, sustained energy, and compact loudness curves. Include silence gating, clipped audio diagnostics, and defined behavior for short files.

Acceptance: Compare LUFS and LRA with independent known reference measurements. Exercise stereo and mono files, gain changes, fades, silence, crescendos, and compressed music. A quieter copy changes original-level loudness without changing source bytes.

### PR 06 Measure tempo and tempo variation

Depends on PR 04.

Add onset extraction, beat tracking, a local tempo path, confidence-weighted representative BPM, half-time and double-time candidates, reliable-segment coverage, and robust variability. Support tap-tempo and factor-of-two corrections through the shared edit model.

Acceptance: Click tracks and tempo ramps meet specified numerical tolerances. Rubato, weak beats, ambient passages, and pulse ambiguity remain explicit. Stable 80 versus 160 BPM hypotheses do not falsely appear as repeated tempo changes.

### PR 07 Estimate key and major or minor mode

Depends on PR 04.

Estimate tuned chroma or HPCP features, compare tonal profiles, retain alternative keys, and aggregate segment tonality. Record major or minor evidence, tonal strength, and mixed, modal, atonal, or unknown states. Benchmark an additional estimator only if it improves useful accuracy.

Acceptance: Known tonal examples produce expected candidates. Relative-key ambiguity, modulation, sparse melody, percussion-only audio, and nonstandard tuning do not receive fabricated high confidence. Mode does not decide the emotion bucket.

### PR 08 Add local models and genre candidates

Depends on PR 01 and 04.

Implement verified model installation or bundling, input preprocessing, fixed prompt or label-taxonomy versions, reusable embeddings, local CPU inference, optional acceleration, segment aggregation, and several genre candidates. Separate broad genres from uncertain narrow styles.

Acceptance: The approved model runs offline after installation and predicts from audio alone. Changed filenames and supplied tags do not change the outputs. Model, taxonomy, license, checksum, and coverage appear in project provenance.

## PR roadmap for scoring and review

### PR 09 Estimate emotion from instrumental audio

Depends on PR 08.

Add valence, arousal, and mood inference using the selected backend. Aggregate windows by audible duration without double-counting overlaps, retain segment disagreement, and flag mixed or weak evidence. Calibrate prompt-based scores using separate development labels and evaluate on held-out audio; softmax similarity is not a psychological probability.

Acceptance: Clear joyful, sad, angry, calm, and ominous examples are evaluated separately. Sad versus angry depends on evidence beyond negative valence. Changing metadata does not alter predictions, and uncertainty survives track-level aggregation.

### PR 10 Create normalized comparison scales

Depends on PR 05 through 09.

Implement the three requested 0 to 100 scores, robust corpus normalization, semantic positivity, reference calibration, corpus percentile ranks, simple and perceived-intensity profiles, missing-feature rules, frozen corpus snapshots, and deterministic precision and sorting behavior.

Acceptance: Outliers, equal values, tiny corpora, missing estimates, and all-positive or all-negative corpora behave as documented. Scores stay reproducible for a frozen snapshot. Re-scoring weights reuses the cache. Anchor recordings pass their agreed calibration checks.

### PR 11 Generate two groups and an album order

Depends on PR 10.

Sort the valence groups, implement the constrained merge, add endpoint-preserving and alternate preferences, pin and exclusion semantics, tie handling, and explicit relaxation messages. Retain the requested simple tempo-plus-volume sorting option.

Acceptance: Every included track appears once. Each automatic group order is nondecreasing. The first two and final two positions hold when feasible. Equal and unequal groups, missing groups, endpoint conflicts, ties, and pins have deterministic behavior and a truthful explanation.

### PR 12 Complete the analysis and ordering interface

Depends on PR 03 and 05 through 11.

Finish the track table, waveform and curve inspector, preview playback, loudness-matched audition, comparison plot, review filters, inline overrides, album drag-and-drop, pinning, and export-plan preview. Apply macOS shortcuts, accessibility, and light and dark styling.

Acceptance: A user can import, analyze, compare two tracks, correct a result, build an order, and reach an export preview without a terminal. Background processing does not block playback controls or editing.

## PR roadmap for calibration and release

### PR 13 Add anchors and personalized presets

Depends on PR 10 and 12.

Add user-selected quiet and intense references, optional pairwise intensity comparisons, versioned weight presets, positivity and review settings, and saved overrides. Make recalibration transparent and maintain independent automatic results.

Acceptance: The same preset reproduces the same results after reopen. Changing anchors or weights previews affected scores and order. Personal corrections apply to that project or explicitly selected preset and cannot silently rewrite other projects.

### PR 14 Export numbered folders with recovery

Depends on PR 11 and 12.

Implement in-place organize and copy export, global album numbering, configurable padding, basename preservation, deterministic collision handling, relative M3U8, CSV, JSON, manifests, staging, durable journals, restart recovery, and conflict-aware undo.

Acceptance: Exported file hashes equal their sources. All intended paths and order entries reconcile with the manifest. Fault injection covers disk failure, interrupted renames, changed files, permissions, Unicode and case collisions, re-export, and cross-volume movement.

### PR 15 Validate audio quality and batch performance

Depends on PR 05 through 14.

Run end-to-end tests and an instrumental listening benchmark using cleared fixtures and a representative 200-track project. Check invariance to filenames and key-based shortcuts, uncertainty coverage, ordering constraints, scoring stability, cache reuse, cancellation, memory, and package behavior.

Acceptance: Publish measured tolerances and held-out metrics with per-genre breakdowns. No fixture labels leak into predictions. Every success, failure, exclusion, review item, and exported track is accounted for. Address regressions before release.

### PR 16 Package and document the macOS release

Depends on PR 15.

Produce reproducible Mac builds for verified architectures, model-pack installation or bundling, project migrations, user documentation, developer setup, third-party notices, model cards, and release artifacts. Configure signing and notarization for use with an available Apple developer identity.

Acceptance: A clean Mac installs or opens the packaged app, analyzes a folder, reopens a project, and exports offline. Clearly state supported hardware and macOS versions. Signing credentials are supplied separately; an unsigned review build remains available until signing can run.

## Validation targets and model contingency

These are proposed acceptance targets. PR 01 confirms feasibility on the selected Mac and records model limitations. Use representative owner recordings when available and cleared reference audio for early testing.

| Area | Proposed check |
| --- | --- |
| Loudness | Integrated LUFS within 0.2 LU and LRA within 0.5 LU of independent reference results on the fixture suite, with silence and short-file exceptions explicitly defined. |
| Tempo | Stable synthetic click tracks within 1 BPM; tempo ramps within 5 percent in confident regions. Report real-music error both with and without allowing half-time or double-time equivalence. |
| Mode and key | Test major, minor, modulation, ambiguous relatives, and non-tonal audio. Report mode and exact-key accuracy separately, including uncertain coverage. |
| Emotion and genre | Separate development and held-out examples by recording or source. Aim for at least 80 percent agreement on clear positive versus negative examples and 75 percent on selected clear mood families, with accepted coverage reported. Evaluate broad-genre top-three recall separately from narrow styles. |
| Perceived intensity | Aim for at least 80 percent agreement on held-out listening pairs. Check quiet piano versus dense metal anchors and neighboring examples. Report performance for original-level and playback-adjusted profiles. |
| Batch behavior | Process 200 mixed-format tracks without losing project state. Target a responsive GUI, prompt cancellation acknowledgment, bounded worker memory, and cached reordering in under two seconds. |
| Mac performance | Measure full and faster modes on a 16 GB Apple Silicon Mac. Set runtime and memory budgets in PR 01 and publish measured results. |
| Export integrity | Every included file and playlist entry reconciles. Hashes match; unrelated files are preserved; tested interrupted operations recover or clearly report the remaining conflict. |

Use owner judgments and, where practical, multiple listeners. Preserve disagreement and report both quality and the proportion classified confidently. Include difficult examples. General music benchmark accuracy does not establish accuracy on this instrumental corpus.

### PR 17 Prepare cleared training and evaluation data

Activate if PR 01 or PR 15 finds inadequate redistributable models. Verify external dataset and checkpoint rights, prepare instrumental subsets and held-out splits, retain label disagreement, and document provenance. Acceptance requires a reproducible pipeline with adequate distribution rights. The user tracks need no preexisting labels.

### PR 18 Train and distribute supervised prediction heads

Depends on PR 17 and PR 08. Train compact mood, valence, arousal, or genre heads over permitted embeddings. Evaluate calibration and bias, package weights and model cards, and rerun PR 15. If lawful data or useful quality remains unavailable, present concrete alternatives for approval. Do not substitute a key or tempo heuristic for emotion.

## Release scope and technical sources

### What completion means

The release is complete when a packaged Mac application can analyze a representative 100 to 200-track instrumental corpus, save and reopen results, provide all requested measurements and three scales, expose uncertainty and corrections, propose the required intensity and emotion progression, and create verified numbered files in the two valence folders with a combined playlist.

The base release includes local inference and existing pretrained assets selected in PR 01. It does not include cloud accounts, music streaming integration, DAW plugins, lyric interpretation, automatic mastering, audio rendering, crossfades, or Windows and Linux release packaging. These may be separate future projects. Model-head training remains the explicit contingency in PRs 17 and 18.

### Implementation after approval

After approval and receipt of the GitHub repository link, inspect its instructions and map these PRs to existing modules. Make necessary implementation choices within the approved scope, keep PRs reviewable, and run the checks relevant to each change. The repository audit may change filenames or exact dependency versions; it should not silently change the requested product behavior.

### Primary technical references

[1] EBU Loudness Range and R 128. Definitions for loudness and loudness variation.

https://tech.ebu.ch/publications/tech3342

https://tech.ebu.ch/publications/r128

[2] Librosa local pulse and tempo. Support for local pulse and changing-tempo analysis.

https://librosa.org/doc/0.11.0/generated/librosa.beat.plp.html

https://librosa.org/doc/0.11.0/generated/librosa.feature.tempo.html

[3] Music CLAP checkpoint and project. Candidate embedding and description-similarity model. The checkpoint card lists Apache 2.0.

https://huggingface.co/laion/larger_clap_music

https://github.com/LAION-AI/CLAP

[4] Essentia model catalog and licensing. Dedicated genre, mood, and valence candidates. Check the exact checkpoint license; the documentation lists restricted model terms.

https://essentia.upf.edu/models.html

https://essentia.upf.edu/licensing_information.html

[5] Music2Emo and its MERT dependency. A dedicated emotion candidate; its released inference uses MERT-v1-95M, whose card lists CC BY-NC 4.0.

https://github.com/AMAAI-Lab/Music2Emotion

https://huggingface.co/m-a-p/MERT-v1-95M

[6] Qt for Python desktop deployment. Native GUI framework and packaging options.

https://doc.qt.io/qtforpython-6/deployment/index.html

https://pyinstaller.org/en/stable/usage.html
