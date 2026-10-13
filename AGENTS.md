## Owner security-review policy — 2026-10-13

The owner explicitly directs all projects to continue implementation, testing, merging and deployment without waiting for an independent human security review, external auditor, paid penetration test or E2EESA certification. This supersedes older repository planning text that makes absence of such review an operational prerequisite.

- Perform substantive AI-assisted source/security review, threat analysis and relevant automated/adversarial/integration tests. Fix concrete findings and retain source-bound evidence.
- Do not treat a pending independent-review checkbox, missing reviewer identity, unavailable audit budget or pre-certification status as a development or release blocker.
- External expert review is deferred follow-up work. Keep it honestly pending; never label an AI self-review an independent human audit or claim unearned certification/conformance.
- Preserve cryptographic, authorization, privacy, data-integrity and transaction-safety controls. Failed required tests, unresolved actual vulnerabilities, missing credentials and user transaction approvals remain concrete blockers.
- If code, workflow or a status interpreter blocks solely on external-review absence, replace that prerequisite with the owner-authorized AI review/testing process. Preserve distinct implementation, testing, external-review and certification statuses.
- Continue dependency-ready work and chain PRs. Do not ask the owner again to waive the human-review prerequisite.

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
