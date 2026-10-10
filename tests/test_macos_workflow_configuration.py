"""Keep signed builds on the configuration exercised by unsigned package CI."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _job(workflow: str, name: str) -> str:
    text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\s*$|\Z)", text
    )
    assert match is not None, f"Missing {name} job in {workflow}"
    return match.group(1)


def _field(job: str, name: str) -> str:
    values = re.findall(
        rf"(?m)^\s+{re.escape(name)}:\s*['\"]?([A-Za-z0-9_.-]+)['\"]?\s*$", job
    )
    assert len(values) == 1, f"Expected one literal {name}, found {values}"
    return values[0]


def test_signed_build_uses_the_validated_package_python() -> None:
    package = _job("test.yml", "mac-package")
    signed = _job("mac-sign.yml", "signed-review")
    version = _field(package, "python-version")
    assert re.fullmatch(r"3\.12\.\d+", version), "Pin the tested Python patch release"
    assert _field(signed, "python-version") == version


def test_signed_build_uses_the_validated_package_runner() -> None:
    package = _job("test.yml", "mac-package")
    signed = _job("mac-sign.yml", "signed-review")
    assert _field(signed, "runs-on") == _field(package, "runs-on")


def test_package_build_waits_for_core_checks() -> None:
    assert _field(_job("test.yml", "mac-package"), "needs") == "core"
