# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import isfinite

import bpy
from mathutils import Euler, Matrix, Vector

from ..model import SLIDE_DIRECTION, GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import add_connector
from .custom_connector import CustomConnector, add_custom_connector
from .dovetail import Dovetail, add_dovetails
from .magnet import Magnet, add_magnet_pockets
from .mesh import bounds
from .planar import PlanarCut, axis_frame, split_plane
from .snap_fit import SnapFit, add_snap_fits


@dataclass(frozen=True)
class SymmetricCut:
    primary: PlanarCut
    axis: str = "X"
    center_offset: float = 0.0
    secondary_offset: float = 0.0
    secondary_rotation: tuple[float, float, float] = (0.0, 0.0, 0.0)


def reflection(axis: str, center: float) -> tuple[Matrix, Vector]:
    index = "XYZ".index(axis)
    mirror = Matrix.Identity(3)
    mirror[index][index] = -1
    translation = Vector((0, 0, 0))
    translation[index] = 2 * center
    return mirror, translation


def reflected_plane(
    frame: Matrix, position: float, midpoint: Vector, axis: str, center: float, offset: float,
    rotation: tuple[float, float, float],
) -> tuple[Matrix, float, Matrix]:
    if not all(map(isfinite, (*rotation, center, offset))):
        raise MeshError("Check the symmetry center, shift and rotation.")
    mirror, translation = reflection(axis, center)
    normal = frame.col[2]
    pivot = midpoint + normal * (position - normal.dot(midpoint))
    pivot = mirror @ pivot + translation
    unrotated = Matrix((-(mirror @ frame.col[0]), mirror @ frame.col[1],
                        mirror @ normal)).transposed()
    adjusted = unrotated @ Euler(rotation, "XYZ").to_matrix()
    turn = adjusted @ unrotated.transposed()
    shifted_pivot = pivot + adjusted.col[2] * offset
    transform = (turn @ mirror).to_4x4()
    transform.translation = shifted_pivot + turn @ (translation - pivot)
    return adjusted, adjusted.col[2].dot(shifted_pivot), transform


def split_symmetric(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    config: SymmetricCut,
) -> tuple[bpy.types.Mesh, ...]:
    primary = config.primary
    lower, upper = bounds(vertex.co for vertex in mesh.vertices)
    midpoint = (lower + upper) / 2
    axis = "XYZ".index(config.axis)
    center = midpoint[axis] + config.center_offset
    frame = axis_frame(primary.axis, primary.rotation)
    normal = frame.col[2]
    initial = split_plane(
        context, transaction, mesh, frame, primary.kerf, offset=primary.offset,
    )
    position = initial.position
    reflected, mirrored_position, transform = reflected_plane(
        frame, position, midpoint, config.axis, center, config.secondary_offset, config.secondary_rotation,
    )
    reflected_normal = reflected.col[2]

    midpoint[axis] = center
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
    inverse = reflected.transposed()

    def reflect_center(center: Vector) -> Vector:
        point = frame @ Vector((center.x, center.y, position))
        point = inverse @ (transform @ point)
        return Vector((point.x, point.y, 0))

    sides = (outer, middle) if middle_index else (middle, outer)
    if isinstance(connector, Dovetail):
        first_rails = add_dovetails(engine, *sides, frame, position, primary.kerf, connector, epsilon, None)
        middle, outer = first_rails.meshes[middle_index], first_rails.meshes[outer_index]
        first_slide = Vector(middle[SLIDE_DIRECTION])
        sides = (mirrored_outer, middle) if middle_index else (middle, mirrored_outer)
        second_rails = add_dovetails(
            engine, *sides, reflected, mirrored_position, primary.kerf, replace(connector, angle=-connector.angle),
            secondary.epsilon, tuple(map(reflect_center, first_rails.centers)),
        )
        middle, mirrored_outer = second_rails.meshes[middle_index], second_rails.meshes[outer_index]
        if (Vector(middle[SLIDE_DIRECTION]) - first_slide).length > 1e-5:
            del middle[SLIDE_DIRECTION]
        return outer, middle, mirrored_outer
    if isinstance(connector, Magnet):
        first_magnets = add_magnet_pockets(engine, *sides, frame, position, primary.kerf, connector, epsilon)
        middle, outer = first_magnets.meshes[middle_index], first_magnets.meshes[outer_index]
        sides = (mirrored_outer, middle) if middle_index else (middle, mirrored_outer)
        second_magnets = add_magnet_pockets(
            engine, *sides, reflected, mirrored_position, primary.kerf, replace(connector, angle=-connector.angle),
            secondary.epsilon, requested=tuple(map(reflect_center, first_magnets.centers)),
        )
        return outer, second_magnets.meshes[middle_index], second_magnets.meshes[outer_index]
    if isinstance(connector, CustomConnector):
        first_custom = add_custom_connector(
            engine, *sides, frame, position, primary.kerf, connector, epsilon,
        )
        middle, outer = first_custom.meshes[middle_index], first_custom.meshes[outer_index]
        sides = (mirrored_outer, middle) if middle_index else (middle, mirrored_outer)
        second_custom = add_custom_connector(
            engine, *sides, reflected, mirrored_position, primary.kerf, connector, secondary.epsilon,
            reflected=True, requested=reflect_center(first_custom.center),
        )
        return outer, second_custom.meshes[middle_index], second_custom.meshes[outer_index]

    if isinstance(connector, SnapFit):
        first_snap = add_snap_fits(engine, *sides, frame, position, primary.kerf, connector, epsilon, None)
        middle, outer = first_snap.meshes[middle_index], first_snap.meshes[outer_index]
        sides = (mirrored_outer, middle) if middle_index else (middle, mirrored_outer)
        second_snap = add_snap_fits(
            engine, *sides, reflected, mirrored_position, primary.kerf, connector.reflected("X"),
            secondary.epsilon, tuple(map(reflect_center, first_snap.centers)),
        )
        return outer, second_snap.meshes[middle_index], second_snap.meshes[outer_index]

    first_set = add_connector(engine, *sides, frame, position, primary.kerf, connector, epsilon, glue=primary.glue)
    middle, outer = first_set.meshes[middle_index], first_set.meshes[outer_index]
    sides = (mirrored_outer, middle) if middle_index else (middle, mirrored_outer)
    second_set = add_connector(
        engine, *sides, reflected, mirrored_position, primary.kerf, connector.reflected("X"),
        secondary.epsilon, requested=tuple(map(reflect_center, first_set.centers)),
        requested_error="The mirrored connector does not fit at its reflected position.",
        glue=primary.glue.reflected("X") if primary.glue else None,
    )
    middle, mirrored_outer = second_set.meshes[middle_index], second_set.meshes[outer_index]
    return outer, middle, mirrored_outer, *first_set.meshes[2:], *second_set.meshes[2:]
