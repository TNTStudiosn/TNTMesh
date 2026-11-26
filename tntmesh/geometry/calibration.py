# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import ceil, isfinite, sqrt

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import Connector, profile_loft, section_volume
from .mesh import inspect, primitive
from .volume import extruded_volume, outline

MAX_SAMPLES = 40
ENGRAVE_DEPTH = 0.45
STROKE = 0.48
PITCH = 2.35
LABEL_HEIGHT = 3.8
DIGITS = {
    "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg",
    "5": "acdfg", "6": "acdefg", "7": "abc", "8": "abcdefg", "9": "abcdfg", ".": ".",
}
SEGMENTS = {
    "a": (0.0, 1.65, 1.18, STROKE), "g": (0.0, 0.0, 1.18, STROKE),
    "d": (0.0, -1.65, 1.18, STROKE), "f": (-0.82, 0.825, STROKE, 1.03),
    "b": (0.82, 0.825, STROKE, 1.03), "e": (-0.82, -0.825, STROKE, 1.03),
    "c": (0.82, -0.825, STROKE, 1.03), ".": (0.0, -1.65, STROKE, STROKE),
}


@dataclass(frozen=True)
class Coupon:
    mesh: bpy.types.Mesh
    clearance: float | None
    position_mm: Vector


def clearance_range(start: float, end: float, *, step: float | None, count: int) -> list[int]:
    if not all(isfinite(value) and 0 <= value <= 10.0 for value in (start, end)):
        raise MeshError("Calibration clearances must be between 0 and 10 mm.")
    first, last = round(start * 1000), round(end * 1000)
    if step is None and count == 1:
        return [first]
    if last < first:
        raise MeshError("The end clearance must be at least the start clearance.")
    if step is not None:
        if not isfinite(step) or not 0.001 <= step <= 10.0:
            raise MeshError("Set a positive clearance increment of at least 0.001 mm.")
        increment = round(step * 1000)
        length = (last - first) // increment + 1
        if length > MAX_SAMPLES:
            raise MeshError("Choose up to 40 calibration samples.")
        return list(range(first, last + 1, increment))
    if not 1 <= count <= MAX_SAMPLES:
        raise MeshError("Choose up to 40 calibration samples.")
    if last - first < count - 1:
        raise MeshError("Increase the clearance range or reduce the sample count.")
    return [first + round((last - first) * index / (count - 1)) for index in range(count)]


def engraving_tool(
    transaction: GeometryTransaction, label: str, y: float, top: float,
) -> tuple[bpy.types.Mesh, float]:
    vertices = []
    faces = []
    area = 0.0
    for index, digit in enumerate(label):
        origin = (index - (len(label) - 1) / 2) * PITCH
        for segment in DIGITS[digit]:
            sx, sy, width, height = SEGMENTS[segment]
            center_x, center_y = origin + sx, y + sy
            ring = outline("RECTANGLE", width, height)
            base = len(vertices)
            for z in (top - ENGRAVE_DEPTH, top + 0.25):
                vertices.extend((center_x + x, center_y + yy, z) for x, yy in ring)
            faces.extend(tuple(base + i for i in face) for face in (
                (3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
                (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
            ))
            area += width * height
    return primitive(transaction, ".TNTMesh calibration label tool", vertices, faces), area * ENGRAVE_DEPTH


def checked_volume(mesh: bpy.types.Mesh, expected: float) -> None:
    result = inspect(mesh)
    if result.shells != 1 or abs(result.volume_mm3 - expected) > max(0.0001, expected * 0.0002):
        raise MeshError("The calibration coupon could not be built as a closed solid.")


def generate(
    context: bpy.types.Context, transaction: GeometryTransaction, connector: Connector,
    clearances: list[int], engraved: bool,
) -> list[Coupon]:
    connector.validate()
    if not clearances or not all(isinstance(value, int) and 0 <= value <= 10000 for value in clearances):
        raise MeshError("Calibration clearances must be between 0 and 10 mm.")
    largest = replace(connector, lateral=max(clearances) / 1000).socket_radius
    depth = connector.insertion + connector.axial
    wall = connector.wall
    frame = Matrix.Identity(3)
    floor = max(wall, 1.4)
    fit_y = LABEL_HEIGHT / 2 + wall + largest if engraved else 0.0
    width = max((largest + wall) * 2, 6 * PITCH + wall * 2 if engraved else 0.0)
    length = fit_y + largest + wall + (LABEL_HEIGHT / 2 + wall if engraved else largest + wall)
    label_y = -length / 2 + wall + LABEL_HEIGHT / 2
    socket_y = length / 2 - wall - largest if engraved else 0.0
    footprint = outline("RECTANGLE", width, length)
    engine = ExactBoolean(context, transaction)
    columns = ceil(sqrt(len(clearances) + 1))
    coupons = []
    for index, clearance in enumerate([None, *clearances]):
        pin = clearance is None
        top = floor if pin else floor + depth
        block = extruded_volume(transaction, frame, Vector((0, 0, top / 2)), footprint, top)
        config = connector if pin else replace(connector, lateral=clearance / 1000)
        # Both mating faces point upward in the build layout. Turn the pin over to test it.
        if pin:
            sections = config.sections(max(top / 2, top - .25), top + config.insertion, top, top)
            change = section_volume(config.sections(0, config.insertion, 0, 0))
        else:
            config = config.reflected("Y")
            negative = config.sections(-.25, depth, 0, 0, config.lateral)
            sections = tuple((top - z, ring) for z, ring in reversed(negative))
            change = -section_volume(config.sections(0, depth, 0, 0, config.lateral))
        feature = profile_loft(transaction, frame, Vector((0, socket_y, 0)), sections)
        mesh = engine.run(block, feature, "UNION" if pin else "DIFFERENCE")
        for tool in (block, feature):
            transaction.remove_mesh(tool)
        expected = width * length * top + change
        checked_volume(mesh, expected)
        if engraved and not pin:
            tool, volume = engraving_tool(transaction, f"{config.lateral:.3f}", label_y, top)
            marked = engine.run(mesh, tool, "DIFFERENCE")
            checked_volume(marked, expected - volume)
            transaction.remove_mesh(tool)
            transaction.remove_mesh(mesh)
            mesh = marked
        row, column = divmod(index, columns)
        location = Vector((column * (width + 2.0), row * (length + 2.0), 0.0))
        coupons.append(Coupon(mesh, None if pin else config.lateral, location))
    return coupons
