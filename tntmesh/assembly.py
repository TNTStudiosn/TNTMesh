# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

import bmesh
import bpy
from bpy.props import FloatProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector

from .geometry.boolean import ExactBoolean
from .geometry.mesh import bounds, evaluated_mm, inspect
from .model import ASSEMBLY_DIRECTION, PROJECT_ID, ROLE, GeometryTransaction, millimeters_per_unit

CONTACT_EPSILON = 0.001
VOLUME_NOISE = 0.00001


class TNTMESH_PG_assembly(bpy.types.PropertyGroup):
    project: StringProperty()
    index: IntProperty(min=0)
    distance: FloatProperty(
        name="Explosion (mm)", description="Move preview geometry away from the assembly",
        default=0, min=0, soft_max=100, max=10000, precision=2,
    )


def project_id(context: bpy.types.Context) -> str:
    selected = context.active_object
    return context.scene.tntmesh_assembly.project or (
        selected.get(PROJECT_ID, "") if selected is not None and selected.get(ROLE) == "part" else ""
    )


def belongs(obj: bpy.types.Object, project: str) -> bool:
    return bool(project and obj is not None and obj.type == "MESH" and obj.get(ROLE) == "part"
                and obj.get(PROJECT_ID) == project and not obj.get("tntmesh_calibration"))


def members(context: bpy.types.Context) -> list[bpy.types.Object]:
    project = project_id(context)
    return sorted((obj for obj in context.view_layer.objects if belongs(obj, project)),
                  key=lambda obj: obj.name.casefold())


def current_member(context: bpy.types.Context) -> bpy.types.Object | None:
    scene = context.scene
    project = project_id(context)
    index = scene.tntmesh_assembly.index
    if index < len(scene.objects):
        obj = scene.objects[index]
        if belongs(obj, project) and obj.name in context.view_layer.objects:
            return obj
    if belongs(context.active_object, project):
        return context.active_object
    return next(iter(members(context)), None)


def world_box(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> tuple[Vector, Vector]:
    evaluated = obj.evaluated_get(depsgraph)
    return bounds(evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box)


def explosion_offsets(
    objects: list[bpy.types.Object], depsgraph: bpy.types.Depsgraph, distance: float,
) -> list[tuple[bpy.types.Object, Vector, Vector]]:
    if not objects:
        return []
    boxes = [world_box(obj, depsgraph) for obj in objects]
    lower, upper = bounds(corner for box in boxes for corner in box)
    center = (lower + upper) / 2
    result = []
    for obj, (low, high) in zip(objects, boxes, strict=True):
        pivot = (low + high) / 2
        hint = obj.get(ASSEMBLY_DIRECTION)
        if hint is not None and len(hint) == 3:
            direction = Vector(hint).normalized()
        else:
            direction = (pivot - center).normalized()
        result.append((obj, pivot, direction * distance))
    return result


@dataclass(frozen=True)
class Body:
    obj: bpy.types.Object
    mesh: bpy.types.Mesh
    lower: Vector
    upper: Vector


def create_body(
    context: bpy.types.Context, transaction: GeometryTransaction, obj: bpy.types.Object,
    reference: Vector, unit: float,
) -> Body:
    mesh, origin = evaluated_mm(context, obj, transaction, unit)
    mesh.transform(Matrix.Translation((origin - reference) * unit))
    mesh.update()
    inspect(mesh)
    lower, upper = bounds(vertex.co for vertex in mesh.vertices)
    return Body(obj, mesh, lower, upper)


def intersection_volume(mesh: bpy.types.Mesh) -> float:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return abs(bm.calc_volume(signed=True)) if bm.faces else 0.0
    finally:
        bm.free()


def overlaps(
    context: bpy.types.Context, objects: list[bpy.types.Object],
) -> list[tuple[bpy.types.Object, bpy.types.Object, float]]:
    if len(objects) < 2:
        return []
    results = []
    unit = millimeters_per_unit(context.scene)
    reference = objects[0].matrix_world.translation.copy()
    with GeometryTransaction() as transaction:
        bodies = sorted(
            (create_body(context, transaction, obj, reference, unit) for obj in objects),
            key=lambda body: body.lower.x,
        )
        engine = ExactBoolean(context, transaction)
        for i, first in enumerate(bodies):
            for second in bodies[i + 1:]:
                if second.lower.x >= first.upper.x - CONTACT_EPSILON:
                    break
                if any(min(first.upper[axis], second.upper[axis]) -
                       max(first.lower[axis], second.lower[axis]) <= CONTACT_EPSILON
                       for axis in range(3)):
                    continue
                intersection = engine.run(first.mesh, second.mesh, "INTERSECT")
                volume = intersection_volume(intersection)
                transaction.remove_mesh(intersection)
                if volume > VOLUME_NOISE:
                    results.append((first.obj, second.obj, volume))
    return results
