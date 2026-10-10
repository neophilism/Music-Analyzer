# Build on the target OS; models remain in the user's separate local model store.
from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['packaging/launcher.py'],
    pathex=['src'],
    datas=collect_data_files('music_analyzer'),
    hiddenimports=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6'],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MusicAnalyzer',
          console=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name='MusicAnalyzer')
if sys.platform == 'darwin':
    app = BUNDLE(coll, name='Music Analyzer.app', bundle_identifier='org.neophilism.music-analyzer',
                 info_plist={'NSHighResolutionCapable': True,
                             'LSMinimumSystemVersion': '14.0'})
