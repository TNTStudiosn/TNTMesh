# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass
from math import cos, isfinite, sin, tau

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .base import BaseCut, split_base
from .boolean import ExactBoolean
from .custom_connector import CustomConnector
from .mesh import bounds, evaluated_mm, inspect, primitive, weld_collapsed_edges
from .planar import PlanarCut, axis_frame, split
from .polygon import Point2, closed_outline, path_outline
from .region import RegionCut, cutter_for_region
from .region_connector import connect_region
from .symmetry import SymmetricCut, split_symmetric


@dataclass(frozen=True)
class VolumeCut:
    shape: str
    axis: str
    rotation: tuple[float, float, float]
    offset: float
    shift: tuple[float, float]
    size: tuple[float, float, float]
    controls: tuple[float, float]
    resolution: int
    cutter: bpy.types.Object | None
    points: tuple[Point2, ...]
    smoothing: int = 0


Cut = BaseCut | PlanarCut | RegionCut | SymmetricCut | VolumeCut


def structural_parts(kind: str) -> int:
    return 3 if kind == "SYMMETRY" else 2


def bezier_path(
    lower: Vector, upper: Vector, offset: float, controls: tuple[float, float], samples: int
) -> Iterator[tuple[float, float]]:
    depth = (lower.z + upper.z) / 2 + offset
    pad = (upper - lower).length * 0.1
    yield lower.x - pad, depth
    for step in range(samples + 1):
        t = step / samples
        complement = 1.0 - t
        height = 3 * complement * t * (complement * controls[0] + t * controls[1])
        yield lower.x + (upper.x - lower.x) * t, depth + height
    yield upper.x + pad, depth


def outline(shape: str, width: float, height: float) -> list[tuple[float, float]]:
    if shape == "RECTANGLE":
        return [(-width / 2, -height / 2), (width / 2, -height / 2),
                (width / 2, height / 2), (-width / 2, height / 2)]
    return [(width / 2 * cos(i * tau / 64), height / 2 * sin(i * tau / 64)) for i in range(64)]


def extruded_volume(
    transaction: GeometryTransaction, frame: Matrix, center: Vector,
    coords: list[tuple[float, float]], depth: float,
) -> bpy.types.Mesh:
    count = len(coords)
    vertices = [
        frame @ (center + Vector((x, y, z)))
        for z in (-depth / 2, depth / 2)
        for x, y in coords
    ]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    for i in range(count):
        j = (i + 1) % count
        faces.append((i, j, j + count, i + count))
    return primitive(transaction, ".TNTMesh region tool", vertices, faces)


def curve_volume(
    transaction: GeometryTransaction, frame: Matrix, lower: Vector, upper: Vector, config: VolumeCut
) -> bpy.types.Mesh:
    path = list(bezier_path(lower, upper, config.offset, config.controls, config.resolution))
    pad = (upper - lower).length * 0.1
    low_y = lower.y - pad
    high_y = upper.y + pad
    top = max(upper.z, *(height for _, height in path)) + pad
    vertices = [
        frame @ Vector(point)
        for x, height in path
        for point in ((x, low_y, height), (x, high_y, height),
                      (x, high_y, top), (x, low_y, top))
    ]
    faces = [(3, 2, 1, 0), tuple(range(len(vertices) - 4, len(vertices)))]
    for i in range(0, len(vertices) - 4, 4):
        for side in range(4):
            next_side = (side + 1) % 4
            faces.append((i + side, i + next_side, i + next_side + 4, i + side + 4))
    return primitive(transaction, ".TNTMesh curved tool", vertices, faces)


def cutter_mesh(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    config: VolumeCut, origin: Vector, unit: float, source: bpy.types.Object,
) -> bpy.types.Mesh:
    if config.shape == "OBJECT":
        obj = config.cutter
        if obj is None or obj == source or obj.type != "MESH":
            raise MeshError("Choose a separate closed mesh as the cutter.")
        if obj.name not in context.view_layer.objects:
            raise MeshError("The cutter is not in this view layer.")
        cutter, cutter_origin = evaluated_mm(context, obj, transaction, unit)
        cutter.transform(Matrix.Translation((cutter_origin - origin) * unit))
        cutter.update()
        return cutter

    frame = axis_frame(config.axis, config.rotation)
    inverse = frame.transposed()
    lower, upper = bounds(inverse @ vertex.co for vertex in mesh.vertices)
    if not isfinite(config.offset):
        raise MeshError("Check the position and dimensions of the cutter.")
    if config.shape == "BEZIER":
        if not all(map(isfinite, config.controls)) or config.resolution < 4:
            raise MeshError("Check the control heights and curve resolution.")
        return curve_volume(transaction, frame, lower, upper, config)
    if config.shape not in {"RECTANGLE", "ELLIPSE", "POLYGON", "PATH"} or (
        not all(map(isfinite, (*config.size, *config.shift))) or min(config.size) <= 0
    ):
        raise MeshError("Check the position and dimensions of the cutter.")
    center = (lower + upper) / 2 + Vector((*config.shift, config.offset))
    width, height, depth = config.size
    if config.shape == "PATH":
        coords = path_outline(
            config.points, tuple((lower - center).xy), tuple((upper - center).xy), config.smoothing,
        )
    elif config.shape == "POLYGON":
        coords = closed_outline(config.points)
    else:
        coords = outline(config.shape, width, height)
    return extruded_volume(transaction, frame, center, coords, depth)


def apply_cut(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    config: Cut, origin: Vector, unit: float, source: bpy.types.Object,
) -> tuple[bpy.types.Mesh, ...]:
    planar = config.primary if isinstance(config, SymmetricCut) else config
    if isinstance(planar, PlanarCut) and isinstance(planar.connector, CustomConnector):
        if source in (planar.connector.pin, planar.connector.socket):
            raise MeshError("Use connector templates separate from the input model.")
    if isinstance(config, SymmetricCut):
        return split_symmetric(context, transaction, mesh, config)
    if isinstance(config, BaseCut):
        return split_base(context, transaction, mesh, config)
    if isinstance(config, PlanarCut):
        return split(context, transaction, mesh, config)
    original_volume = inspect(mesh).volume_mm3
    if isinstance(config, RegionCut):
        region = cutter_for_region(transaction, mesh, source, config)
        cutter = region.mesh
    else:
        cutter = cutter_mesh(context, transaction, mesh, config, origin, unit, source)
        inspect(cutter)
    engine = ExactBoolean(context, transaction)
    outside = engine.run(mesh, cutter, "DIFFERENCE")
    inside = engine.run(mesh, cutter, "INTERSECT")
    if isinstance(config, RegionCut):
        weld_collapsed_edges(outside)
        weld_collapsed_edges(inside)
    if not outside.polygons or not inside.polygons:
        raise MeshError("The cutter must leave material on both sides of the cut.")
    total = inspect(outside).volume_mm3 + inspect(inside).volume_mm3
    if abs(total - original_volume) > original_volume * .001:
        raise MeshError("The split did not preserve the expected volume.")
    if isinstance(config, RegionCut) and config.connector is not None:
        return connect_region(engine, outside, inside, region, config.connector)
    return outside, inside
