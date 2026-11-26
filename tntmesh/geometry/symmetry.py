# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import isfinite

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import Connector, add_connector
from .mesh import bounds
from .planar import PlanarCut, axis_frame, split_plane


@dataclass(frozen=True)
class SymmetricCut:
    primary: PlanarCut
    axis: str = "X"
    center_offset: float = 0.0
    secondary_offset: float = 0.0


def reflection(axis: str, center: float) -> tuple[Matrix, Vector]:
    index = "XYZ".index(axis)
    mirror = Matrix.Identity(3)
    mirror[index][index] = -1
    translation = Vector((0, 0, 0))
    translation[index] = 2 * center
    return mirror, translation


def split_symmetric(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    config: SymmetricCut,
) -> tuple[bpy.types.Mesh, ...]:
    primary = config.primary
    if primary.connector is not None and not isinstance(primary.connector, Connector):
        raise MeshError("Symmetric cuts support round or hexagonal connectors.")
    if not all(map(isfinite, (config.center_offset, config.secondary_offset))):
        raise MeshError("Check the symmetry center and secondary offset.")
    lower, upper = bounds(vertex.co for vertex in mesh.vertices)
    midpoint = (lower + upper) / 2
    axis = "XYZ".index(config.axis)
    midpoint[axis] += config.center_offset
    mirror, translation = reflection(config.axis, midpoint[axis])
    frame = axis_frame(primary.axis, primary.rotation)
    normal = frame.col[2]
    reflected = Matrix((-(mirror @ frame.col[0]), mirror @ frame.col[1],
                        mirror @ normal)).transposed()
    reflected_normal = reflected.col[2]
    initial = split_plane(
        context, transaction, mesh, frame, primary.kerf, offset=primary.offset,
    )
    position = initial.position
    mirrored_position = reflected_normal.dot(mirror @ (normal * position) + translation)
    mirrored_position += config.secondary_offset

    direction = normal.dot(midpoint) - position
    reflected_direction = reflected_normal.dot(midpoint) - mirrored_position
    gap = primary.kerf / 2
    epsilon = initial.epsilon
    if abs(direction) <= gap + epsilon or direction * reflected_direction <= 0:
        raise MeshError("Move the cut to one side of the symmetry center.")
    middle_index = int(direction > 0)
    outer_index = 1 - middle_index
    first = (initial.minus, initial.plus)
    middle, outer = first[middle_index], first[outer_index]
    inward_side = 1 if middle_index else -1
    if any(inward_side * (reflected_normal.dot(vertex.co) - mirrored_position) < gap - epsilon
           for vertex in outer.vertices):
        raise MeshError("The two cuts cross within the model. Adjust the angle or offset.")
    secondary = split_plane(
        context, transaction, middle, reflected, primary.kerf, position=mirrored_position,
    )
    transaction.remove_mesh(middle)
    second = (secondary.minus, secondary.plus)
    middle, mirrored_outer = second[middle_index], second[outer_index]

    connector = primary.connector
    if connector is None:
        return outer, middle, mirrored_outer

    engine = ExactBoolean(context, transaction)
    sides = (outer, middle) if middle_index else (middle, outer)
    first_set = add_connector(
        engine, *sides, frame, position, primary.kerf, connector, epsilon,
    )
    middle, outer = first_set.meshes[middle_index], first_set.meshes[outer_index]
    requested = []
    inverse = reflected.transposed()
    for center in first_set.centers:
        point = frame @ Vector((center.x, center.y, position))
        point = inverse @ (mirror @ point + translation)
        requested.append(Vector((point.x, point.y, 0)))
    sides = (mirrored_outer, middle) if middle_index else (middle, mirrored_outer)
    second_set = add_connector(
        engine, *sides, reflected, mirrored_position, primary.kerf, connector,
        secondary.epsilon, requested=tuple(requested),
        requested_error="The mirrored connector does not fit at its reflected position.",
    )
    middle, mirrored_outer = second_set.meshes[middle_index], second_set.meshes[outer_index]
    return outer, middle, mirrored_outer, *first_set.meshes[2:], *second_set.meshes[2:]
