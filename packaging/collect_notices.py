"""Collect the actual installed runtime dependency inventory and available licenses."""

import argparse
import json
import shutil
from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def collect(root):
    root.mkdir(parents=True, exist_ok=True)
    pending, processed, components = [("music-analyzer-desktop", {"models"}), ("pyinstaller", set())], set(), {}
    while pending:
        name, extras = pending.pop()
        name = canonicalize_name(name)
        key = (name, tuple(sorted(extras)))
        if key in processed:
            continue
        processed.add(key)
        package = distribution(name)
        if name not in components:
            item = {"name": name, "version": package.version,
                    "license": package.metadata.get("License-Expression") or package.metadata.get("License") or "See packaged license files and upstream metadata",
                    "upstream": package.metadata.get_all("Project-URL", []), "license_files": []}
            for relative in package.files or []:
                basename = Path(str(relative)).name.lower()
                if not (basename.startswith(("license", "copying", "notice")) or "/licenses/" in str(relative).lower()):
                    continue
                source = Path(package.locate_file(relative))
                if not source.is_file():
                    continue
                safe_path = Path(*[p for p in Path(str(relative)).parts if p not in {"..", ".", "/"}])
                target = root / name / safe_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                item["license_files"].append(target.relative_to(root).as_posix())
            components[name] = item
        for text in package.requires or []:
            requirement = Requirement(text)
            if requirement.marker and not any(requirement.marker.evaluate({"extra": extra}) for extra in {"", *extras}):
                continue
            pending.append((requirement.name, set(requirement.extras)))
    for source in Path("licenses").glob("*"):
        if source.is_file():
            shutil.copyfile(source, root / source.name)
    for source in [Path("LICENSE"), Path("docs/THIRD_PARTY.md"), Path("docs/MODELS.md")]:
        if source.is_file():
            shutil.copyfile(source, root / source.name)
    inventory = {"scope": "Installed runtime dependency closure including the optional models extra; verify actual bundled libraries before public release",
                 "components": sorted(components.values(), key=lambda item: item["name"]),
                 "qt_sources": "https://code.qt.io/cgit/qt/qt5.git/?h=v6.10.3",
                 "qt_attributions": "https://doc.qt.io/qt-6.10/licenses-used-in-qt.html"}
    (root / "dependency-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    return len(components)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/third-party-notices"))
    args = parser.parse_args()
    print(f"Collected {collect(args.output)} runtime dependency notices.")
