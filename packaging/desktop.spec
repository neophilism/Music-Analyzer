# Build on the target OS; weights remain in the user's separate local model store.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

root = Path(SPECPATH).parent
datas = collect_data_files('music_analyzer')
notices = root / 'build/third-party-notices'
if notices.is_dir():
    datas.append((str(notices), 'third-party-notices'))
for name in ('torch', 'transformers', 'huggingface-hub', 'tokenizers', 'safetensors',
             'numpy', 'scipy', 'packaging', 'PySide6', 'soundfile', 'librosa'):
    datas += copy_metadata(name)
hidden = ['transformers.models.clap.configuration_clap',
          'transformers.models.clap.modeling_clap',
          'transformers.models.clap.processing_clap',
          'transformers.models.clap.feature_extraction_clap',
          'transformers.models.roberta.tokenization_roberta',
          'transformers.models.roberta.tokenization_roberta_fast',
          'tokenizers', 'safetensors.torch', 'certifi']
identity = os.environ.get('MUSIC_ANALYZER_CODESIGN_IDENTITY') or None

a = Analysis(
    [str(root / 'packaging/launcher.py')],
    pathex=[str(root / 'src')],
    datas=datas,
    hiddenimports=hidden,
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'matplotlib', 'tensorflow', 'torchvision',
              'torchaudio', 'PySide6.QtCharts', 'PySide6.QtWebEngineCore',
              'PySide6.QtWebEngineWidgets', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets'],
    module_collection_mode={'librosa': 'py', 'numba': 'py', 'transformers': 'py'},
    runtime_hooks=[str(root / 'packaging/runtime.py')],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MusicAnalyzer',
          console=False, strip=False, upx=False,
          target_arch='arm64' if sys.platform == 'darwin' else None,
          codesign_identity=identity,
          entitlements_file=str(root / 'packaging/macos-entitlements.plist') if identity else None)
coll = COLLECT(exe, a.binaries, a.datas, name='MusicAnalyzer')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Music Analyzer.app', bundle_identifier='org.neophilism.music-analyzer',
                 info_plist={'NSHighResolutionCapable': True,
                             'LSMinimumSystemVersion': '14.0',
                             'CFBundleShortVersionString': '0.1.0',
                             'NSHumanReadableCopyright': 'Music Analyzer contributors · MIT license'})
