# Mac build and release checklist

## Current target and build artifacts

Initial target: Apple Silicon, macOS 14 or later, Python 3.12 runtime bundled in
the app. Intel is not advertised: the selected recent PyTorch Mac distribution
does not supply a supported Intel wheel. Linux verifies core logic and package
behavior but is not a substitute for native Mac verification.

The Tests workflow runs the Linux/macOS source suite and a 200-track mixed-format
fixture benchmark. Only if both pass does it build on macOS 14, test actual
offline model inference, freeze the app, and verify GUI/worker/project/export
behavior. It then unpacks the artifact on a separate macOS 15 runner and installs
the pinned model using the packaged executable, with no developer dependency
installation. Inference verification runs with Hugging Face offline flags.

Review artifacts contain the ZIP, SHA256SUMS, exact installed dependency versions,
notices, and JSON verification reports. GitHub retains them for 30 days; archive
the successful reviewed commit's artifacts before expiration. The automatic build
uses ad-hoc signing for Apple Silicon execution; it is **not Developer ID signed
or notarized** and is named `unsigned-review`. No workflow publishes a release.

## Reproduce a reviewed build

Use an Apple Silicon Mac with macOS 14+, Python 3.12.15, and Xcode command-line
tools. Check out the recorded source SHA. Create a fresh virtual environment,
install the successful artifact's `macos-arm64-build-requirements.txt`, then
install this checkout with `pip install --no-deps -e .`. The saved dependency file
pins the exact resolved build rather than resolving the broad development bounds
again. Architecture, OS toolchain, and signatures can change binary bytes; retain
the archive hash and all provenance for the actual distributed artifact.

```bash
python packaging/collect_notices.py
python -m PyInstaller --clean --noconfirm packaging/desktop.spec
"dist/Music Analyzer.app/Contents/MacOS/MusicAnalyzer" --install-model model-pack
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "dist/Music Analyzer.app/Contents/MacOS/MusicAnalyzer" --verify-package --model-directory "$PWD/model-pack" --verification-report build/frozen-verification.json
```

The weights are separate from the application. The installer verifies every
asset's byte count and SHA-256, retains verified assets after cancellation, and
loads the pinned tensor checkpoint in restricted `weights_only` mode. Certificate
verification keeps system trust and adds the bundled certifi roots. There is no
TLS-verification bypass. Model or algorithm changes invalidate the analysis cache.
Numba uses a writable per-user cache, not the read-only app bundle.

Projects currently use schema 1. The schema version is checked on open; unsupported
future schemas are rejected clearly. There is no silent destructive migration.
Back up projects with **Save project as** before upgrading. Keep source recordings
and export journals until the desired recovery/undo period ends.

## Before calling a release complete

- [ ] All code PRs pass current CI; merge the stack in numeric order with merge
  commits, preserving ancestry. Main remains plan-only until approved merges.
- [ ] Both native frozen verification jobs pass at the final reviewed commit.
- [ ] Download the actual artifact onto a clean Mac; open from Finder and check
  installation, dark/light appearance, shortcuts, accessibility, and file dialogs.
- [ ] Listen to WAV/AIFF/FLAC/MP3/OGG and supported AAC/M4A examples. Test playback,
  seeking, loudness matching, and a separately installed FFmpeg decoder.
- [ ] Analyze a cleared 100–200-track real instrumental corpus. Measure full and
  sampled inference modes, cache reuse, cancel/reopen, and memory on a **16 GB**
  Apple Silicon Mac. CI synthetic fixtures and smaller runner memory are separate
  evidence; they do not establish this performance gate.
- [ ] Review genre/mood/valence against recording-disjoint held-out listener
  annotations and intensity pairs. Report coverage and per-genre errors. Targets
  of 80% valence, 75% mood-family, and 80% intensity-pair agreement are unverified
  until those measurements run.
- [ ] Import the actual quiet piano and dense metal reference recordings and
  verify the desired dynamics anchors below 10 and in the 90s.
- [ ] Verify numbered copy and move, recovery after interruption, undo, Unicode
  names, collisions, read-only folders, and cross-volume moves on the actual Mac.
- [ ] Reconcile third-party notices with bundled libraries, required sources, and
  replacement instructions; test LGPL library replacement on the final artifact.
- [ ] Sign/notarize/staple and pass Gatekeeper on a clean Mac when credentials are
  provided. Archive notarization result, final ZIP/hash, dependency lock, and notices.
- [ ] Receive the user's approval before merging or publishing a public release.

## Optional Apple signing

The manual **Signed Mac review build** workflow takes a full reviewed source SHA.
It checks the source and builds/signs in a temporary runner keychain, submits a ZIP
with `notarytool`, requires an Accepted result, staples the ticket, and checks
`codesign`, `stapler`, and `spctl`. It uploads a signed review artifact without
publishing a release. Signing has not run unless its evidence is recorded in
[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

Configure these repository secrets separately:

| Secret | Value |
| --- | --- |
| `APPLE_CERTIFICATE_P12_BASE64` | Exported Developer ID Application certificate/private key as base64 P12 |
| `APPLE_CERTIFICATE_PASSWORD` | P12 export password |
| `MUSIC_ANALYZER_CODESIGN_IDENTITY` | Exact Developer ID Application identity |
| `APPLE_NOTARY_KEY_P8_BASE64` | Base64 App Store Connect notarization API private key |
| `APPLE_NOTARY_KEY_ID` | API key ID |
| `APPLE_NOTARY_ISSUER_ID` | API issuer ID |

The entitlements support JIT and dynamic library replacement. Never commit these
credentials or describe an ad-hoc review build as Developer ID signed. The manual
workflow can be dispatched after the workflow is present on the default branch.
