# Music Analyzer contributor handoff

Read `docs/DEVELOPMENT_PLAN.md`, `docs/IMPLEMENTATION_STATUS.md`, and
`docs/ARCHITECTURE.md` before changing scope. The approved product is a native
desktop app; do not replace it with a web application or an HTTP service.

- Work in the approved stacked PR sequence. Before beginning the next stage,
  verify that every earlier code PR passes its current Linux and macOS CI checks.
  Fix failed checks at the earliest affected branch and carry the repair through
  dependent branches. Preserve ancestry and never silently disable a failing test.
- Do not merge the review PRs or publish a release without the user's instruction.
- Audio stays local. Downloads are an explicit model-install action. Inference
  sees audio and generic prompts; never filenames, tags, or lyrics.
- Keep automatic analysis separate from listener corrections. Missing, ambiguous,
  and neutral results require review rather than fabricated labels.
- Never claim listening accuracy from synthetic fixtures, or claim the requested
  piano/metal anchor scores without measuring the supplied recordings.
- Maintain byte verification, exclusive publication, journals, resume, and undo
  when changing exports. Never overwrite an unrelated file.
- Run ruff, relevant core tests, the batch benchmark for pipeline changes, and
  actual frozen model verification for package/model changes. Record the exact
  commit and CI run, and update the handoff status and PR description.
- macOS 14+ on Apple Silicon is the initial package target. Signing, real playback,
  listening quality, and 16 GB Mac performance are independent release gates.
