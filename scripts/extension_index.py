# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from check_release import version_from_tag

REPO = "TNTStudiosn/TNTMesh"
API = f"https://api.github.com/repos/{REPO}/releases"
ASSET_BASE = f"https://github.com/{REPO}/releases/download/"
STAGES = {"alpha": 0, "beta": 1, "rc": 2}


def release_order(version: str) -> tuple[int, int, int, int, int]:
    base, _, stage = version.partition("-")
    major, minor, patch = map(int, base.split("."))
    if stage:
        phase, number = stage.split(".")
        return major, minor, patch, STAGES[phase], int(number)
    return major, minor, patch, len(STAGES), 0


def latest_releases() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TNTMesh-release-index"}
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    selected = {}
    url = f"{API}?per_page=100"
    while url:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            releases = json.load(response)
            links = response.headers.get("Link", "").split(",")
        for release in releases:
            if release["draft"]:
                continue
            try:
                version = version_from_tag(release["tag_name"])
            except ValueError:
                continue
            expected_prerelease = "-" in version
            if release["prerelease"] != expected_prerelease:
                raise ValueError(f"GitHub release channel does not match the tag {version}")
            channel = "experimental" if expected_prerelease else "stable"
            if channel not in selected or release_order(version) > release_order(selected[channel][0]):
                selected[channel] = (version, release)
        url = next((link.split(";")[0].strip().strip("<>") for link in links
                    if 'rel="next"' in link), None)
        if url and not url.startswith(f"{API}?"):
            raise ValueError("Unexpected GitHub pagination URL")
    return selected


def verified_asset(version: str, release: dict, staging: Path) -> tuple[str, int, str]:
    name = f"tntmesh-{version}.zip"
    asset = next((item for item in release["assets"] if item["name"] == name), None)
    expected_url = f"{ASSET_BASE}{release['tag_name']}/{name}"
    if asset is None or asset["browser_download_url"] != expected_url:
        raise ValueError(f"Missing expected release ZIP for {version}")
    asset_size, asset_hash = asset["size"], asset.get("digest")
    if not asset_hash or not asset_hash.startswith("sha256:"):
        raise ValueError(f"Missing GitHub release asset digest for {version}")
    request = Request(expected_url, headers={"User-Agent": "TNTMesh-release-index"})
    with urlopen(request, timeout=60) as response:
        data = response.read(asset_size + 1)
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    if len(data) != asset_size or digest != asset_hash:
        raise ValueError(f"Release asset size or digest mismatch for {version}")
    (staging / name).write_bytes(data)
    return expected_url, asset_size, digest


def build_index(blender: str, target: Path, selected: tuple[str, dict] | None) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        staging = Path(work)
        if selected:
            version, release = selected
            url, size, digest = verified_asset(version, release, staging)
        subprocess.run(
            [blender, "--factory-startup", "--command", "extension", "server-generate",
             "--repo-dir", str(staging)],
            check=True,
        )
        index = json.loads((staging / "index.json").read_text(encoding="utf-8"))
        entries = index["data"]
        if selected:
            if len(entries) != 1:
                raise ValueError("Expected exactly one package in the generated repository")
            entry = entries[0]
            if (entry["id"] != "tntmesh" or entry["version"] != version
                    or entry["archive_size"] != size or entry["archive_hash"] != digest):
                raise ValueError("Blender's index does not match the checked release package")
            entry["archive_url"] = url
        (target / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def main(blender: str, output: Path) -> None:
    releases = latest_releases()
    for channel in ("stable", "experimental"):
        build_index(blender, output / channel, releases.get(channel))


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
