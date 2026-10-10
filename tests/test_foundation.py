import subprocess
import sys


def test_native_app_launches_and_exits():
    result = subprocess.run(
        [sys.executable, "-m", "music_analyzer", "--smoke"],
        capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr.decode()
