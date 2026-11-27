# SPDX-License-Identifier: GPL-3.0-or-later
import json
from dataclasses import asdict
from math import isfinite

from ..model import MeshError
from .connector import Connector
from .dovetail import Dovetail
from .polygon import Point2
from .press_fit import PressFit
from .rod import Rod
from .screw import Screw
from .snap_fit import SnapFit

PROFILE_FIELDS = ("width", "height", "angle", "taper")


def encode(
    design: Connector | Dovetail | PressFit | Rod | Screw | SnapFit, positions: tuple[Point2, ...], positive: bool,
) -> str:
    settings = asdict(design)
    if isinstance(design, Dovetail):
        version = 2
    elif isinstance(design, SnapFit):
        settings.pop("reverse_flex")
        version = 4
    elif isinstance(design, PressFit):
        version = 5
    elif isinstance(design, Rod):
        version = 6
    elif isinstance(design, Screw):
        version = 7
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


def decode(text: str) -> tuple[Connector | Dovetail | PressFit | Rod | Screw | SnapFit, tuple[Point2, ...], bool]:
    error = MeshError("The clipboard does not contain a valid TNTMesh connector setup.")
    if not text or len(text) > 65536:
        raise error
    try:
        data = json.loads(text)
        version = data["tntmesh_connector"]
        if type(version) is not int or version not in (1, 2, 3, 4, 5, 6, 7):
            raise ValueError
        settings = data["settings"]
        if not isinstance(settings, dict) or {"mirror_profile", "reverse_flex"} & settings.keys():
            raise ValueError
        design = {1: Connector, 2: Dovetail, 3: Connector, 4: SnapFit, 5: PressFit, 6: Rod, 7: Screw}[version](**settings)
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
        if isinstance(design, SnapFit):
            if not isinstance(design.material, str) or len(design.material) > 128:
                raise ValueError
            dimensions = design.width, design.thickness, design.reach, design.hook, design.wall
            extra = design.ramp_angle, design.strain_limit
        elif isinstance(design, PressFit):
            if not isinstance(design.material, str) or len(design.material) > 128:
                raise ValueError
            dimensions = design.diameter, design.reach, design.interference, design.slot, design.wall
            extra = (design.strain_limit,)
        elif isinstance(design, Connector):
            dimensions = design.diameter, design.width, design.height, design.insertion, design.wall
            extra = (design.taper,)
        elif isinstance(design, Rod):
            dimensions = design.size, design.depth_minus, design.depth_plus, design.wall
            extra = ()
        elif isinstance(design, Screw):
            dimensions = (design.diameter, design.length, design.pitch, design.head_width, design.head_height,
                          design.nut_width, design.nut_height, design.wall)
            extra = ()
        else:
            dimensions = design.neck, design.head, design.height, design.length, design.wall
            extra = ()
        values = (*dimensions, design.lateral, design.axial, design.angle, *extra)
        if any(type(value) not in (int, float) or not isfinite(value) or abs(value) > 1e6 for value in values):
            raise ValueError
        if min(dimensions) < .01:
            raise ValueError
        if isinstance(design, (PressFit, SnapFit)):
            if not 0 <= design.strain_limit <= 100:
                raise ValueError
            design.validate_dimensions()
        else:
            design.validate()
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, MeshError) as cause:
        raise error from cause
    return design, tuple(positions), positive
