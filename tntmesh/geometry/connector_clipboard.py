# SPDX-License-Identifier: GPL-3.0-or-later
import json
from dataclasses import asdict
from math import isfinite

from ..model import MeshError
from .connector import Connector
from .dovetail import Dovetail
from .polygon import Point2

PROFILE_FIELDS = ("width", "height", "angle", "taper")


def encode(design: Connector | Dovetail, positions: tuple[Point2, ...], positive: bool) -> str:
    settings = asdict(design)
    if isinstance(design, Dovetail):
        version = 2
    else:
        settings.pop("mirror_profile")
        version = 1 if design.shape == "ROUND" or (design.shape == "HEX" and not design.angle) else 3
        if version == 1:
            for key in PROFILE_FIELDS:
                settings.pop(key)
    return json.dumps({
        "tntmesh_connector": version, "settings": settings,
        "positions": positions, "pin_positive": positive,
    }, separators=(",", ":"))


def decode(text: str) -> tuple[Connector | Dovetail, tuple[Point2, ...], bool]:
    error = MeshError("The clipboard does not contain a valid TNTMesh connector setup.")
    if not text or len(text) > 65536:
        raise error
    try:
        data = json.loads(text)
        version = data["tntmesh_connector"]
        if type(version) is not int or version not in (1, 2, 3):
            raise ValueError
        settings = data["settings"]
        if not isinstance(settings, dict) or "mirror_profile" in settings:
            raise ValueError
        design = (Dovetail if version == 2 else Connector)(**settings)
        if version == 1 and (design.shape not in {"ROUND", "HEX"} or any(key in settings for key in PROFILE_FIELDS)):
            raise ValueError
        positive = data["pin_positive"]
        raw = data["positions"]
        if (type(design.count) is not int or not 1 <= design.count <= 64
                or (isinstance(design, Connector) and type(design.loose) is not bool) or type(positive) is not bool
                or type(raw) is not list or (raw and len(raw) != design.count)):
            raise ValueError
        positions = []
        for point in raw:
            if (type(point) is not list or len(point) != 2
                    or any(type(value) not in (int, float) or not isfinite(value) or abs(value) > 1e6
                           for value in point)):
                raise ValueError
            positions.append(tuple(point))
        dimensions = ((design.diameter, design.width, design.height, design.insertion, design.wall)
                      if isinstance(design, Connector)
                      else (design.neck, design.head, design.height, design.length, design.wall))
        values = (*dimensions, design.lateral, design.axial, design.angle,
                  *((design.taper,) if isinstance(design, Connector) else ()))
        if any(type(value) not in (int, float) or not isfinite(value) or abs(value) > 1e6 for value in values):
            raise ValueError
        if min(dimensions) < .01:
            raise ValueError
        design.validate()
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, MeshError) as cause:
        raise error from cause
    return design, tuple(positions), positive
