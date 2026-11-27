# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import isfinite, pi

import bpy
from mathutils import Euler, Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean, half_box
from .connector import Connector, add_connector, safe_centers
from .custom_connector import CustomConnector, add_custom_connector
from .dovetail import Dovetail, add_dovetails
from .dovetail import layout as dovetail_layout
from .magnet import Magnet, add_magnet_pockets, magnet_centers
from .mesh import bounds, inspect
from .polygon import Point2
from .snap_fit import SnapFit, add_snap_fits, snap_centers


@dataclass(frozen=True)
class PlanarCut:
    axis: str = "Z"
    offset: float = 0.0
    kerf: float = 0.0
    connector: Connector | CustomConnector | Dovetail | Magnet | SnapFit | None = None
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
    connector_positions: tuple[Point2, ...] = ()
    pin_positive: bool = False


@dataclass(frozen=True)
class PlaneSplit:
    minus: bpy.types.Mesh
    plus: bpy.types.Mesh
    position: float
    epsilon: float

    def flipped(self) -> "PlaneSplit":
        return PlaneSplit(self.plus, self.minus, -self.position, self.epsilon)


def invert_frame(frame: Matrix) -> Matrix:
    return frame @ Matrix.Diagonal(Vector((1.0, -1.0, -1.0)))


def connector_frame(
    cut: PlaneSplit, frame: Matrix, positions: tuple[Point2, ...], flip: bool,
) -> tuple[PlaneSplit, Matrix, tuple[Vector, ...] | None]:
    requested = (tuple(Vector((x, -y if flip else y, 0)) for x, y in positions) if positions else None)
    return (cut.flipped(), invert_frame(frame), requested) if flip else (cut, frame, requested)


def dovetail_positions(
    engine: ExactBoolean, cut: PlaneSplit, frame: Matrix, kerf: float, design: Dovetail,
    positions: tuple[Point2, ...], flip: bool,
) -> tuple[Point2, ...]:
    local, work, requested = connector_frame(cut, frame, positions, flip)
    if flip:
        design = replace(design, angle=pi - design.angle)
    rails, seats = dovetail_layout(engine.context, local.minus, local.plus, work, local.position, kerf,
                                   design, local.epsilon, requested)
    to_seam = frame.transposed() @ rails.seam
    return tuple(tuple((to_seam @ seat.center).xy) for seat in seats)


def validate_positions(
    engine: ExactBoolean, cut: PlaneSplit, frame: Matrix, kerf: float,
    design: Connector | Dovetail | Magnet | SnapFit,
    positions: tuple[Point2, ...], flip: bool,
) -> None:
    if isinstance(design, Magnet):
        _, _, requested = connector_frame(cut, frame, positions, False)
        magnet_centers(engine, cut.minus, cut.plus, frame, cut.position, kerf, design, cut.epsilon, requested)
        return
    if isinstance(design, Dovetail):
        dovetail_positions(engine, cut, frame, kerf, design, positions, flip)
        return
    if isinstance(design, SnapFit):
        snap_positions(engine, cut, frame, kerf, design, positions, flip)
        return
    standard_positions(engine, cut, frame, kerf, design, positions, flip)


def snap_positions(
    engine: ExactBoolean, cut: PlaneSplit, frame: Matrix, kerf: float, design: SnapFit,
    positions: tuple[Point2, ...], flip: bool,
) -> tuple[Point2, ...]:
    cut, frame, requested = connector_frame(cut, frame, positions, flip)
    if flip:
        design = design.reflected("Y")
    points = snap_centers(engine, cut.minus, cut.plus, frame, cut.position, kerf, design, cut.epsilon, requested)
    return tuple((point.x, -point.y if flip else point.y) for point in points)


def standard_positions(
    engine: ExactBoolean, cut: PlaneSplit, frame: Matrix, kerf: float, design: Connector,
    positions: tuple[Point2, ...], flip: bool,
) -> tuple[Point2, ...]:
    design.validate()
    cut, frame, requested = connector_frame(cut, frame, positions, flip)
    if flip:
        design = design.reflected("Y")
    points = safe_centers(
        engine, cut.minus, cut.plus, frame, (cut.position - kerf / 2, cut.position + kerf / 2),
        design.depths, design.profile(design.lateral + design.wall), cut.epsilon,
        min(cut.epsilon, design.anchor / 10, design.wall / 10), design.count, requested=requested,
        footprint_spacing=design.uses_footprint,
    )
    return tuple((point.x, -point.y if flip else point.y) for point in points)


def axis_frame(
    axis: str, rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> Matrix:
    if axis == "FREE":
        if not all(map(isfinite, rotation)):
            raise MeshError("Check the rotation of the cut.")
        return Euler(rotation, "XYZ").to_matrix()
    # Right-handed basis, with the local Z axis along the cutting direction.
    z = {"X": Vector((1, 0, 0)), "Y": Vector((0, 1, 0)), "Z": Vector((0, 0, 1))}[axis]
    x = Vector((1, 0, 0)) if axis != "X" else Vector((0, 1, 0))
    return Matrix((x, z.cross(x), z)).transposed()


def split_plane(
    context: bpy.types.Context,
    transaction: GeometryTransaction,
    mesh: bpy.types.Mesh,
    frame: Matrix,
    kerf: float,
    *,
    offset: float = 0.0,
    position: float | None = None,
) -> PlaneSplit:
    if not all(map(isfinite, (offset, kerf))) or kerf < 0 or (
        position is not None and not isfinite(position)
    ):
        raise MeshError("Check the cut offset and separation.")
    source = inspect(mesh)
    inverse = frame.transposed()
    lower, upper = bounds(inverse @ vertex.co for vertex in mesh.vertices)
    extent = max(lower.length, upper.length) * 2.0
    epsilon = max(extent * 2e-7, 1e-6)
    if position is None:
        position = (lower.z + upper.z) / 2.0 + offset
    low, high = position - kerf / 2, position + kerf / 2
    if low <= lower.z + epsilon or high >= upper.z - epsilon:
        raise MeshError("Move the cut inside the model or reduce the separation.")

    engine = ExactBoolean(context, transaction)
    minus = engine.run(mesh, half_box(transaction, frame, extent, low, -1), "INTERSECT")
    plus = engine.run(mesh, half_box(transaction, frame, extent, high, 1), "INTERSECT")
    parts = [inspect(part) for part in (minus, plus)]
    total = sum(part.volume_mm3 for part in parts)
    tolerance = source.volume_mm3 * .001
    if (total > source.volume_mm3 + tolerance
            or (kerf == 0 and abs(total - source.volume_mm3) > tolerance)):
        raise MeshError("The split did not preserve the expected volume.")
    return PlaneSplit(minus, plus, position, epsilon)


def split(
    context: bpy.types.Context,
    transaction: GeometryTransaction,
    mesh: bpy.types.Mesh,
    config: PlanarCut,
) -> tuple[bpy.types.Mesh, ...]:
    frame = axis_frame(config.axis, config.rotation)
    cut = split_plane(context, transaction, mesh, frame, config.kerf, offset=config.offset)
    minus, plus = cut.minus, cut.plus
    engine = ExactBoolean(context, transaction)
    if isinstance(config.connector, CustomConnector):
        return add_custom_connector(
            engine, minus, plus, frame, cut.position, config.kerf, config.connector, cut.epsilon
        ).meshes
    if isinstance(config.connector, Magnet):
        _, _, requested = connector_frame(cut, frame, config.connector_positions, False)
        return add_magnet_pockets(
            engine, minus, plus, frame, cut.position, config.kerf, config.connector, cut.epsilon, requested,
        ).meshes
    if config.connector is not None:
        cut, frame, requested = connector_frame(cut, frame, config.connector_positions, config.pin_positive)
        design = config.connector
        if isinstance(design, Dovetail):
            if config.pin_positive:
                design = replace(design, angle=pi - design.angle)
            result = add_dovetails(engine, cut.minus, cut.plus, frame, cut.position, config.kerf,
                                   design, cut.epsilon, requested)
        elif isinstance(design, SnapFit):
            if config.pin_positive:
                design = design.reflected("Y")
            result = add_snap_fits(engine, cut.minus, cut.plus, frame, cut.position, config.kerf,
                                   design, cut.epsilon, requested)
        else:
            if config.pin_positive:
                design = design.reflected("Y")
            result = add_connector(engine, cut.minus, cut.plus, frame, cut.position, config.kerf,
                                   design, cut.epsilon, requested=requested)
        first, second, *pins = result.meshes
        return (second, first, *pins) if config.pin_positive else (first, second, *pins)
    return minus, plus
