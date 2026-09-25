"""Build and publish static documentation without application dependencies."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".knowledge-assistant-docs.json"


def sync_site(source: Path, destination: Path) -> None:
    """Copy generated files, removing only previously recorded stale files."""
    destination = destination.resolve()
    manifest = destination / MANIFEST
    old = (
        set(json.loads(manifest.read_text(encoding="utf-8")))
        if manifest.exists()
        else set()
    )
    files = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    for name in old | files:
        relative = PurePosixPath(name)
        target = destination / name
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or ":" in name
            or not target.resolve().is_relative_to(destination)
        ):
            raise ValueError(f"Unsafe publication path: {name}")
        if name in files and target.exists() and name not in old:
            raise ValueError(f"Refusing to overwrite unowned file: {target}")
    destination.mkdir(parents=True, exist_ok=True)
    for name in sorted(files):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    for name in sorted(old - files):
        (destination / name).unlink(missing_ok=True)
    manifest.write_text(json.dumps(sorted(files), indent=2) + "\n", encoding="utf-8")
    print(f"Published {len(files)} files to {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "publish"])
    parser.add_argument(
        "--destination",
        type=Path,
        default=Path("E:/public/_html/tech/knowledge-assistant"),
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="knowledge-assistant-docs-") as folder:
        output = Path(folder) / "html"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "sphinx",
                "-b",
                "html",
                "-n",
                "-W",
                "--keep-going",
                "-d",
                str(Path(folder) / "doctrees"),
                str(ROOT / "docs"),
                str(output),
            ],
            check=True,
        )
        sync_site(output, ROOT / "docs" / "_build" / "html")
        if args.action == "publish":
            sync_site(output, args.destination)


if __name__ == "__main__":
    main()
