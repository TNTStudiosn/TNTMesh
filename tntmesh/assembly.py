# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import isfinite

import bmesh
import bpy
from bpy.props import FloatProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector

from .geometry.boolean import ExactBoolean
from .geometry.mesh import bounds, evaluated_mm, inspect
from .model import (
    ASSEMBLY_DIRECTION,
    PROJECT_ID,
    ROLE,
    GeometryTransaction,
    MeshError,
    millimeters_per_unit,
)

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


@dataclass(frozen=True)
class InsertionHit:
    obstacle: bpy.types.Object
    distance_mm: float
    volume_mm3: float


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


def candidate_pair(
    first_lower: Vector, first_upper: Vector, second: Body,
) -> bool:
    return all(
        min(first_upper[axis], second.upper[axis]) -
        max(first_lower[axis], second.lower[axis]) > CONTACT_EPSILON
        for axis in range(3)
    )


def measure_intersection(
    engine: ExactBoolean, first: bpy.types.Mesh, second: bpy.types.Mesh,
) -> float:
    intersection = engine.run(first, second, "INTERSECT")
    try:
        return intersection_volume(intersection)
    finally:
        engine.transaction.remove_mesh(intersection)


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
                if not candidate_pair(first.lower, first.upper, second):
                    continue
                volume = measure_intersection(engine, first.mesh, second.mesh)
                if volume > VOLUME_NOISE:
                    results.append((first.obj, second.obj, volume))
    return results


def insertion_hit(
    context: bpy.types.Context, moving: bpy.types.Object, obstacles: list[bpy.types.Object],
    direction: Vector, distance_mm: float, steps: int,
) -> InsertionHit | None:
    if (not all(map(isfinite, (*direction, distance_mm))) or direction.length_squared == 0
            or distance_mm <= 0 or steps < 1):
        raise MeshError("Choose an insertion direction, travel distance and step count.")
    axis = direction.normalized()
    unit = millimeters_per_unit(context.scene)
    reference = moving.matrix_world.translation.copy()
    wm = context.window_manager
    wm.progress_begin(0, steps + 1)
    try:
        with GeometryTransaction() as transaction:
            moving_body = create_body(context, transaction, moving, reference, unit)
            bodies = [create_body(context, transaction, obj, reference, unit)
                      for obj in obstacles if obj != moving]
            reach = axis * distance_mm
            swept = bounds((moving_body.lower, moving_body.upper,
                            moving_body.lower + reach, moving_body.upper + reach))
            nearby = [body for body in bodies if candidate_pair(*swept, body)]
            if not nearby:
                return None
            probe = transaction.own_mesh(moving_body.mesh.copy())
            engine = ExactBoolean(context, transaction)
            for index in range(steps + 1):
                distance = distance_mm * (steps - index) / steps
                offset = axis * distance
                candidates = [body for body in nearby if candidate_pair(
                    moving_body.lower + offset, moving_body.upper + offset, body,
                )]
                if candidates:
                    for original, vertex in zip(moving_body.mesh.vertices, probe.vertices, strict=True):
                        vertex.co = original.co + offset
                    probe.update()
                    for body in candidates:
                        volume = measure_intersection(engine, probe, body.mesh)
                        if volume > VOLUME_NOISE:
                            return InsertionHit(body.obj, distance, volume)
                wm.progress_update(index + 1)
    finally:
        wm.progress_end()
        context.view_layer.update()
    return None
