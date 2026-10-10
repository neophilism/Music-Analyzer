# Getting started with Music Analyzer

## Use the packaged app, not the developer setup

You need an Apple Silicon Mac running macOS 14 or later. In the Apple menu,
About This Mac should show an Apple chip, not an Intel processor. The app includes
its Python runtime. You do not need Terminal, Python, an Apple developer account,
or completion of the other neophilism repositories for this review build.

This is an ad-hoc-signed review application, not a Developer ID-signed/notarized
public release. Use copies of recordings for your first trial. Its automated
checks do not establish listening accuracy or manual testing on your own Mac.

## 1. Download the verified application

Sign into GitHub using the account with access to this private repository.

Download:
https://github.com/neophilism/Music-Analyzer/actions/runs/38070930610/artifacts/11676882107

Fallback: open the build page below, scroll to Artifacts, and click
macos-arm64-review. Do not choose the batch report or clean-install report;
those are evidence files, not the application.

https://github.com/neophilism/Music-Analyzer/actions/runs/38070930610

Verified source: 50b0c3cb11d8934c3123932e3bb458c86518c0a4.
Download size: 237,717,221 bytes (about 238 MB).
Artifact expiration: November 9, 2026. Retain a local copy before expiration.
The linked run passed all four jobs, including native package verification and
separate clean installation without developer Python dependencies.

Unzip the outer macos-arm64-review download. Inside it, unzip
Music-Analyzer-macos-arm64-unsigned-review.zip. Move Music Analyzer.app into
Applications. Keep SHA256SUMS, dependency versions, notices, and verification
reports with your archived download; they describe this particular build.

Optional integrity check: the SHA-256 of the OUTER GitHub artifact ZIP is:
0189a3cf0ce1fb6ba5724b29fb0cbc61dafaf31ceeb3578cba03997e8b5505e9

SHA256SUMS inside the download instead describes the INNER application ZIP.
Do not compare the inner ZIP with the outer ZIP's hash. A matching checksum
confirms bytes; it does not replace Apple's signature or malware assessment.

## 2. Open the app

Double-click Music Analyzer.app in Applications.

Because this review build is not Developer ID signed or notarized, macOS may
say Apple cannot check it or cannot verify its developer. Only after confirming
you downloaded the intended build from your repository and it has not been
altered, use Apple's per-app process: after the attempted launch, open
System Settings > Privacy & Security > Open Anyway, then confirm Open.

Do not disable Gatekeeper globally, remove quarantine recursively, or bypass a
warning that the application is damaged or will harm your computer. Stop and
report that exact warning. Managed Macs may prohibit per-app exceptions.

Apple's guidance:
https://support.apple.com/102445

## 3. Install the local music model

In the app, click Local model..., then Install / verify model. This is an explicit
model download of about 780 MB; the installer verifies its assets. Wait for the
background installation to finish before starting analysis. The app does not
upload your recordings. After installation, model inference works offline.

Use Preferences... to keep Device set to cpu for your first trial and enable
Use installed model for genre and emotion. Full coverage is the default; faster
sampling is available but examines less audio and must not be mistaken for full
coverage. An interrupted download can be resumed with Install / verify model.

Without the model, acoustic measurements still work, but do not expect automatic
genre/mood results or silently invented positive/negative assignments.

## 4. Make your first album

Create a project with File > New project and choose a writable location. The
app saves analysis and edits automatically; Save project as creates a backup.
Keep the original recordings and export journals while you may need recovery.

Add a few WAV or FLAC copies using Add tracks..., then click Analyze. Start small
to verify your own installation and listening workflow before a full album.
CPU model analysis of full-length tracks can take substantially longer than the
short synthetic CI fixtures; no full-album runtime is promised.

Select tracks to listen with Play / pause and inspect results. Use Needs review
to find uncertain items. Choose a positive or negative assignment and apply your
review for each included track that still lacks an assignment. Review suggested
assignments before accepting them. Manual corrections stay separate from the
original automatic analysis.

Recalculate scales after changing the comparison corpus or scoring profile.
Open Album order, choose the desired intensity profile, and Build order. The
rising-group mode preserves ascending intensity within each group and explains
unavoidable alternation/end-position conflicts. Review the proposed sequence.

Click Export..., review the complete preview, and choose Export Copies into a
new output location for your first trial. Avoid Organize/move originals until
you have verified the copies and understand recovery/undo.

Expected output: Positive Valence and Negative Valence folders with numbered,
byte-identical audio, album.m3u8 for the combined sequence, analysis.csv,
analysis.json, and a manifest containing mappings and hashes. An unresolved
assignment must be reviewed or explicitly excluded, not silently lost.

## Troubleshooting

GitHub displays 404 or no download: sign into the authorized account. This is a
private repository. Use the build-page fallback above. After November 9, 2026,
this particular application artifact expires and a newly verified build is needed.

You only see JSON reports: select macos-arm64-review, not a benchmark or
clean-install-verification artifact. The actual app is inside the second ZIP.

The app is incompatible: this package targets Apple Silicon and macOS 14+.
It is not an Intel, Windows, or Linux distribution.

AAC/M4A import fails: those formats may require a separately installed FFmpeg
command-line executable. Set its absolute path in Preferences... > FFmpeg
executable. Do not install arbitrary codec packages just to start; WAV/FLAC
copies are the simplest initial check. Stereo and mono are supported;
multichannel analysis reports an error rather than silently downmixing.

Mood/genre is missing: verify the model installation and the model-enabled
preference. Very short, silent, ambiguous, or mixed recordings may legitimately
need review even with the model installed.

Export is blocked: inspect Needs review and the export preview for missing
assignments, source-file changes, collisions, or excluded tracks. Use a new
empty destination for the first copy export. Do not delete recovery journals
to force a blocked operation.

For a problem report, include the exact error text, macOS version, Apple chip,
step that failed, source commit above, and file format. Do not include account
passwords, Apple signing keys, or private recordings unnecessarily.

## What this build does not claim

Held-out instrumental listening accuracy, actual quiet/dense owner anchors,
full-length 100-200-track performance on a 16 GB Mac, manual playback/accessibility,
linked-library replacement, and Apple signing/notarization/Gatekeeper remain
release gates. A personal trial is possible without claiming those gates passed.
Do not use the synthetic benchmark numbers as real-music accuracy or runtime.

GitHub artifact download help:
https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts
