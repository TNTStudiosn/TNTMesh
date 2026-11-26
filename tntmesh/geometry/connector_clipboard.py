# SPDX-License-Identifier: GPL-3.0-or-later
import json
from dataclasses import asdict
from math import isfinite

from ..model import MeshError
from .connector import Connector
from .polygon import Point2


def encode(design: Connector, positions: tuple[Point2, ...], positive: bool) -> str:
    return json.dumps({
        "tntmesh_connector": 1, "settings": asdict(design), "positions": positions, "pin_positive": positive,
    }, separators=(",", ":"))


def decode(text: str) -> tuple[Connector, tuple[Point2, ...], bool]:
    error = MeshError("The clipboard does not contain a valid TNTMesh connector setup.")
    if not text or len(text) > 65536:
        raise error
    try:
        data = json.loads(text)
        if type(data["tntmesh_connector"]) is not int or data["tntmesh_connector"] != 1:
            raise ValueError
        design = Connector(**data["settings"])
        positive = data["pin_positive"]
        raw = data["positions"]
        if (type(design.count) is not int or not 1 <= design.count <= 64
                or type(design.loose) is not bool or type(positive) is not bool
                or type(raw) is not list or (raw and len(raw) != design.count)):
            raise ValueError
        positions = []
        for point in raw:
            if (type(point) is not list or len(point) != 2
                    or any(type(value) not in (int, float) or not isfinite(value) or abs(value) > 1e6
                           for value in point)):
                raise ValueError
            positions.append(tuple(point))
        values = (design.diameter, design.insertion, design.lateral, design.axial, design.wall)
        if any(type(value) not in (int, float) or not isfinite(value) or abs(value) > 1e6 for value in values):
            raise ValueError
        if min(design.diameter, design.insertion, design.wall) < .01:
            raise ValueError
        design.validate()
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, MeshError) as cause:
        raise error from cause
    return design, tuple(positions), positive
