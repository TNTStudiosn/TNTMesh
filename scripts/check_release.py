# SPDX-License-Identifier: GPL-3.0-or-later
import re
import sys
import tomllib
from pathlib import Path
from zipfile import ZipFile


def version_from_tag(tag: str) -> str:
    pattern = r"v((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-(?:alpha|beta|rc)\.[1-9]\d*)?)"
    match = re.fullmatch(pattern, tag)
    if match is None:
        raise ValueError(f"Expected a semantic TNTMesh release tag, got {tag!r}")
    return match[1]


def verify(tag: str, packages: Path) -> None:
    version = version_from_tag(tag)
    manifest = Path("tntmesh/blender_manifest.toml").read_bytes()
    expected = tomllib.loads(manifest.decode())
    if expected["version"] != version or expected["id"] != "tntmesh":
        raise ValueError("Release tag and extension manifest do not match")
    copies = sorted(packages.glob(f"*/tntmesh-{version}.zip"))
    if not copies:
        raise ValueError("The verified extension ZIP is missing")
    expected_files = None
    for archive in copies:
        with ZipFile(archive) as package:
            names = package.namelist()
            files = {name: package.read(name) for name in names if not name.endswith("/")}
        if files.get("blender_manifest.toml") != manifest or "LICENSE" not in files:
            raise ValueError(f"Manifest or license mismatch in {archive}")
        if expected_files is None:
            expected_files = files
        elif files != expected_files:
            raise ValueError(f"Package contents differ across Blender builders in {archive}")


if __name__ == "__main__":
    verify(sys.argv[1], Path(sys.argv[2]))
