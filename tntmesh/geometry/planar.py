# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import isfinite

import bpy
from mathutils import Euler, Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean, half_box
from .connector import Connector, add_connector
from .custom_connector import CustomConnector, add_custom_connector
from .mesh import bounds, inspect


@dataclass(frozen=True)
class PlanarCut:
    axis: str = "Z"
    offset: float = 0.0
    kerf: float = 0.0
    connector: Connector | CustomConnector | None = None
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class PlaneSplit:
    minus: bpy.types.Mesh
    plus: bpy.types.Mesh
    position: float
    epsilon: float


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
        )
    if config.connector is not None:
        return add_connector(engine, minus, plus, frame, cut.position, config.kerf,
                             config.connector, cut.epsilon).meshes
    return minus, plus
