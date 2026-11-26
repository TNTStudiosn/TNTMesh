# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import cos, hypot, isfinite, tau

import bpy
from mathutils import Matrix, Vector

from ..model import MeshError, millimeters_per_unit
from .boolean import ExactBoolean, half_box
from .connector import safe_centers
from .connector_profiles import regular_profile
from .mesh import bounds, inspect


@dataclass(frozen=True)
class CustomConnector:
    pin: bpy.types.Object | None
    socket: bpy.types.Object | None
    wall: float


@dataclass(frozen=True)
class CustomPlacement:
    meshes: tuple[bpy.types.Mesh, bpy.types.Mesh]
    center: Vector


def template(engine: ExactBoolean, obj: bpy.types.Object, reflected: bool) -> bpy.types.Mesh:
    context = engine.context
    if obj.type != "MESH" or obj.name not in context.view_layer.objects:
        raise MeshError("Connector templates must be meshes in this view layer.")
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    linear = evaluated.matrix_world.to_3x3()
    if reflected:
        linear = Matrix.Diagonal(Vector((-1, 1, 1))) @ linear
    determinant = linear.determinant()
    if not isfinite(determinant) or determinant == 0:
        raise MeshError("The object transform is singular.")
    mesh = engine.transaction.own_mesh(
        bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    )
    # Template origins coincide at the connector center. Ignore scene translation.
    mesh.transform(Matrix.Scale(millimeters_per_unit(context.scene), 4) @ linear.to_4x4())
    if determinant < 0:
        mesh.flip_normals()
    mesh.update()
    if inspect(mesh).shells != 1:
        raise MeshError("Each connector template must be one closed shell.")
    return mesh


def add_custom_connector(
    engine: ExactBoolean,
    minus: bpy.types.Mesh,
    plus: bpy.types.Mesh,
    frame: Matrix,
    position: float,
    kerf: float,
    config: CustomConnector,
    epsilon: float,
    *,
    reflected: bool = False,
    requested: Vector | None = None,
) -> CustomPlacement:
    if config.pin is None or config.socket is None or config.pin == config.socket:
        raise MeshError("Choose separate pin and socket templates.")
    if kerf != 0:
        raise MeshError("Custom templates require a cut with zero kerf.")
    if not isfinite(config.wall) or config.wall <= 0.0:
        raise MeshError("Check the connector dimensions and clearances.")
    pin = template(engine, config.pin, reflected)
    socket = template(engine, config.socket, reflected)
    pin_lower, pin_upper = bounds(vertex.co for vertex in pin.vertices)
    socket_lower, socket_upper = bounds(vertex.co for vertex in socket.vertices)
    if (pin_lower.z >= -epsilon or pin_upper.z <= epsilon or socket_lower.z >= -epsilon
            or socket_upper.z <= epsilon):
        raise MeshError("Both templates must cross the mating plane at their origin.")

    extent = 2.0 * max(pin_lower.length, pin_upper.length, socket_lower.length, socket_upper.length)
    clip = half_box(engine.transaction, Matrix.Identity(3), extent, 0, 1)
    tip = engine.run(pin, clip, "INTERSECT")
    recess = engine.run(socket, clip, "INTERSECT")
    tip_volume = inspect(tip).volume_mm3
    recess_volume = inspect(recess).volume_mm3
    if engine.run(tip, socket, "DIFFERENCE").polygons:
        raise MeshError("The custom pin protrudes outside its socket template.")

    radius = max(hypot(vertex.co.x, vertex.co.y) for mesh in (pin, socket)
                 for vertex in mesh.vertices)
    wall = config.wall
    center, = safe_centers(
        engine, minus, plus, frame, (position, position),
        (-pin_lower.z + wall, socket_upper.z + wall), regular_profile((radius + wall) / cos(tau / 128), 64),
        epsilon, min(epsilon, -pin_lower.z / 10, wall / 10), 1,
        requested=(requested,) if requested is not None else None,
        requested_error="The mirrored connector does not fit at its reflected position.",
    )
    placement = frame.to_4x4() @ Matrix.Translation(Vector((center.x, center.y, position)))
    for mesh in (pin, socket):
        mesh.transform(placement)
        mesh.update()
    male = engine.run(minus, pin, "UNION")
    female = engine.run(plus, socket, "DIFFERENCE")
    for before, after, expected in ((minus, male, tip_volume), (plus, female, -recess_volume)):
        first, second = inspect(before), inspect(after)
        if (first.shells != second.shells
                or abs(second.volume_mm3 - first.volume_mm3 - expected) > abs(expected) * .01):
            raise MeshError("The connector could not be joined or the socket could not be cut.")
    return CustomPlacement((male, female), center)
