# Third-party software and model notices

The application code is MIT licensed. Dependencies retain their own licenses.
The build collects the installed runtime dependency closure (including the model
extra), package license files, exact versions, and the notices here into
`third-party-notices` in the app's resource directory. The same inventory is
uploaded beside each review build. Inspect it against the actual linked binaries
before public distribution; an inventory is not a completed license audit.

## Qt and playback

PySide6, Shiboken6, and the dynamically linked Qt 6.10.3 libraries use the LGPL
option where available. The app does not use GPL-only Qt modules. The LGPL 3.0
text and its referenced GPL 3.0 text are included in `licenses/`. Qt's component
attributions are at <https://doc.qt.io/qt-6.10/licenses-used-in-qt.html>.
Matching source is available from
<https://download.qt.io/archive/qt/6.10/6.10.3/> and the `v6.10.3` source tags in
<https://code.qt.io/cgit/>. PySide/Shiboken source is in the `pyside-setup`
repository there. Record the actual Qt version from each build before release.

Qt Multimedia includes dynamically linked FFmpeg playback libraries. Qt 6.10
identifies its FFmpeg 7.1.3 configuration as LGPL 2.1 or later; the configuration
and notices are at
<https://doc.qt.io/qt-6.10/qtmultimedia-attribution-ffmpeg.html>.
FFmpeg source is at <https://ffmpeg.org/releases/ffmpeg-7.1.3.tar.xz>.
SoundFile's bundled libsndfile also uses LGPL 2.1. Its wheel's COPYING file and
the LGPL 2.1 text are collected. Obtain corresponding sources and build settings
for every version actually shipped before publishing a release.

The optional FFmpeg command-line decoder is separately installed by the user.
It is not included in the application bundle. Its presence on a CI machine does
not mean it is bundled. Its license depends on the user's particular build.

## Replacing libraries

This is an on-directory bundle with dynamic libraries, not a statically linked
executable. On macOS, use **Show Package Contents** and inspect
`Contents/Frameworks` and `Contents/Resources`; on other build hosts inspect
`MusicAnalyzer/_internal`. Users may replace LGPL libraries with compatible
modified builds. The application license does not restrict reverse engineering
needed to debug those modifications. Replacement can invalidate a macOS code
signature; make a copy and re-sign the modified bundle locally. The configured
release entitlements allow library replacement and JIT compilation. The source,
PyInstaller specification, runtime hook, and build workflows in this repository
provide the application's build instructions. Verify replacement on the exact
signed artifact before public distribution.

## Model and remaining dependencies

The optional LAION `larger_clap_music` checkpoint is Apache-2.0, installed
explicitly from the pinned manifest. Its original model card, revision, asset
hashes, and `installation.json` remain beside the weights. See [MODELS.md](MODELS.md)
for the model's intended use and limits. The model is not embedded in the app.

PyTorch, Transformers, tokenizers, NumPy, SciPy, librosa, SoundFile, certifi, and
their runtime dependencies have separate notices in the generated inventory.
Do not substitute the application's MIT license for those notices. PyInstaller's
bootloader license has an exception allowing distribution of bundled applications;
its installed license and exception must accompany distributed builds.

## Public distribution gate

Before a public release, reconcile the inventory with linked libraries, preserve
all required upstream attributions, provide corresponding source and build
information required by the selected licenses, and test dynamic replacement.
Review builds are labeled unsigned and preliminary until the distribution and
native Mac checklist has been completed.
