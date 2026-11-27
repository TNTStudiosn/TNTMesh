# SPDX-License-Identifier: GPL-3.0-or-later
import json
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from uuid import uuid4

import bpy

from .geometry.hinge import Hinge
from .geometry.magnet import Magnet
from .geometry.planar import PlanarCut
from .geometry.press_fit import PressFit
from .geometry.snap_fit import SnapFit
from .geometry.symmetry import SymmetricCut
from .localization import tr
from .model import PART_ID, PROJECT_ID, ROLE

GUIDE_PATH = "tntmesh_assembly_path"
PARENT_PART = "tntmesh_parent_part_id"


@dataclass(frozen=True)
class StockMagnet:
    shape: str
    size: tuple[float, ...]
    count: int

    def label(self) -> str:
        dimensions = " × ".join(f"{size:.3g}" for size in self.size)
        if self.shape == "DISC":
            return tr("Disc magnet Ø{size} mm").format(size=dimensions)
        return tr("Block magnet {size} mm").format(size=dimensions)


@dataclass(frozen=True)
class Branch:
    cut: str
    index: int
    count: int
    magnet: StockMagnet | None = None
    connector: str = ""

    @property
    def snap_fit(self) -> bool:
        return self.connector == "SNAP_FIT"


def connection_details(config: object) -> tuple[StockMagnet | None, str]:
    primary = config.primary if isinstance(config, SymmetricCut) else config
    if not isinstance(primary, PlanarCut):
        return None, ""
    if isinstance(primary.connector, Hinge):
        return None, "HINGE"
    if isinstance(primary.connector, PressFit):
        return None, "PRESS_FIT"
    if primary.glue is not None:
        return None, "GLUE"
    if not isinstance(primary.connector, Magnet):
        return None, "SNAP_FIT" if isinstance(primary.connector, SnapFit) else ""
    magnet = primary.connector
    size = (magnet.width, magnet.thickness) if magnet.shape == "DISC" else (
        magnet.width, magnet.length, magnet.thickness
    )
    return StockMagnet(magnet.shape, size, magnet.count * (4 if isinstance(config, SymmetricCut) else 2)), ""


def path(obj: bpy.types.Object) -> tuple[Branch, ...]:
    raw = obj.get(GUIDE_PATH)
    if not isinstance(raw, str):
        return ()
    try:
        entries = []
        for cut, index, count, stock, *connector in json.loads(raw):
            if not isinstance(cut, str) or type(index) is not int or type(count) is not int:
                return ()
            if not cut or not (0 <= index <= count <= 32767) or connector not in (
                [], ["SNAP_FIT"], ["PRESS_FIT"], ["HINGE"], ["GLUE"],
            ):
                return ()
            magnet = None
            if stock is not None:
                shape, size, quantity = stock
                dimensions = {"DISC": 2, "BLOCK": 3}.get(shape)
                if (dimensions is None or len(size) != dimensions or type(quantity) is not int
                        or quantity <= 0 or not all(isfinite(value) and value > 0 for value in size)):
                    return ()
                magnet = StockMagnet(shape, tuple(size), quantity)
            entries.append(Branch(cut, index, count, magnet, connector[0] if connector else ""))
        return tuple(entries)
    except (TypeError, ValueError, OverflowError):
        return ()


def set_path(obj: bpy.types.Object, entries: tuple[Branch, ...]) -> None:
    obj[GUIDE_PATH] = json.dumps([
        (entry.cut, entry.index, entry.count,
         (entry.magnet.shape, entry.magnet.size, entry.magnet.count) if entry.magnet else None,
         *((entry.connector,) if entry.connector else ()))
        for entry in entries
    ], separators=(",", ":"))


def record_cut(
    source: bpy.types.Object, parts: list[bpy.types.Object], body_count: int, config: object = None,
) -> None:
    inherited = path(source)
    cut = uuid4().hex
    magnet, connector = connection_details(config)
    for index, part in enumerate(parts, 1):
        branch = index if index <= body_count else 0
        set_path(part, inherited + (Branch(cut, branch, body_count, magnet, connector),))


def legacy_paths(
    scene: bpy.types.Scene, objects: list[bpy.types.Object], is_connector: Callable[[bpy.types.Object], bool],
) -> dict[str, tuple[Branch, ...]]:
    if not objects:
        return {}
    project = objects[0].get(PROJECT_ID)
    known = {}
    legacy_groups: dict[str, list[bpy.types.Object]] = {}
    for obj in scene.objects:
        if obj.get(PROJECT_ID) != project or obj.get(ROLE) not in {"part", "superseded"}:
            continue
        if part_id := obj.get(PART_ID):
            known[part_id] = obj
        if GUIDE_PATH not in obj and PARENT_PART in obj:
            legacy_groups.setdefault(obj[PARENT_PART], []).append(obj)
    entries = {}
    for parent, siblings in legacy_groups.items():
        bodies = sorted((obj for obj in siblings if not is_connector(obj)), key=lambda obj: obj.name.casefold())
        if len(bodies) < 2:
            continue
        for index, body in enumerate(bodies, 1):
            entries[body.name] = Branch("legacy:" + parent, index, len(bodies))
        for obj in siblings:
            if is_connector(obj):
                entries[obj.name] = Branch("legacy:" + parent, 0, len(bodies))
    for_object = {}
    for obj in objects:
        chain = []
        seen = set()
        current = obj
        while current is not None and current.name not in seen:
            seen.add(current.name)
            if current.name in entries:
                chain.append(entries[current.name])
            current = known.get(current.get(PARENT_PART))
        if chain:
            for_object[obj.name] = tuple(reversed(chain))
    return for_object
