# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import isfinite, tau

import bpy
from bpy.props import FloatProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector

from .geometry.boolean import ExactBoolean
from .geometry.mesh import BOOLEAN_VOLUME_NOISE, absolute_volume, bounds, evaluated_mm, inspect
from .geometry.sweep import (
    ROTATION_LIMIT_ERROR,
    RotarySweep,
    box_interval,
    probe_positions,
    rotation_probes,
)
from .geometry.triangle_bounds import hierarchy, triangles_from
from .model import (
    ASSEMBLY_DIRECTION,
    PROJECT_ID,
    ROLE,
    SLIDE_DIRECTION,
    GeometryTransaction,
    MeshError,
    millimeters_per_unit,
)

CONTACT_EPSILON = 0.001
MESH_FLOAT_EPSILON = 2 ** -23
MAX_ROTARY_TESTS = 2048


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


def slide_direction(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> Vector | None:
    slide = obj.data.get(SLIDE_DIRECTION)
    if slide is not None and len(slide) == 3:
        direction = obj.evaluated_get(depsgraph).matrix_world.to_3x3() @ Vector(slide)
        if direction.length_squared > 0:
            return direction.normalized()
    return None


def slide_travel(
    context: bpy.types.Context, moving: bpy.types.Object, pieces: list[bpy.types.Object], axis: Vector,
) -> float:
    depsgraph = context.evaluated_depsgraph_get()
    def projected(obj: bpy.types.Object) -> list[float]:
        evaluated = obj.evaluated_get(depsgraph)
        return [axis.dot(evaluated.matrix_world @ Vector(corner)) for corner in evaluated.bound_box]

    start = min(projected(moving))
    end = max(value for piece in pieces if piece != moving for value in projected(piece))
    return max(0, (end - start) * millimeters_per_unit(context.scene)) + 1


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
        direction = slide_direction(obj, depsgraph)
        if direction is None:
            direction = (Vector(hint) if hint is not None and len(hint) == 3 else pivot - center).normalized()
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
    rotation_radians: float = 0


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
        volume = absolute_volume(intersection)
        if volume <= BOOLEAN_VOLUME_NOISE:
            return 0.0
        scale = max(abs(coordinate) for vertex in intersection.vertices for coordinate in vertex.co)
        # A surface displaced by one mesh-coordinate ULP can report area times
        # that displacement as volume, even where two assembled faces touch.
        roundoff = sum(face.area for face in intersection.polygons) * scale * MESH_FLOAT_EPSILON
        return volume if volume > roundoff else 0.0
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
                if volume > BOOLEAN_VOLUME_NOISE:
                    results.append((first.obj, second.obj, volume))
    return results


def insertion_hit(
    context: bpy.types.Context, moving: bpy.types.Object, obstacles: list[bpy.types.Object],
    direction: Vector, distance_mm: float, steps: int = 1,
    *, rotation_axis: Vector | None = None, rotation_radians: float = 0,
    pivot_world: Vector | None = None, sample_mm: float = .25,
) -> InsertionHit | None:
    if (not all(map(isfinite, (*direction, distance_mm, rotation_radians))) or distance_mm < 0 or steps < 1
            or (distance_mm > 0 and direction.length_squared == 0) or (not distance_mm and not rotation_radians)):
        raise MeshError("Choose a valid insertion direction and travel distance.")
    if rotation_radians and (
        rotation_axis is None or not all(map(isfinite, (*rotation_axis, sample_mm)))
        or rotation_axis.length_squared == 0 or not .05 <= sample_mm <= 10 or abs(rotation_radians) > tau + 1e-6
        or (pivot_world is not None and not all(map(isfinite, pivot_world)))
    ):
        raise MeshError("Set a valid rotation axis, pivot and sampling distance.")
    axis = direction.normalized()
    unit = millimeters_per_unit(context.scene)
    reference = moving.matrix_world.translation.copy()
    wm = context.window_manager
    wm.progress_begin(0, max(1, len(obstacles)))
    try:
        with GeometryTransaction() as transaction:
            moving_body = create_body(context, transaction, moving, reference, unit)
            bodies = [create_body(context, transaction, obj, reference, unit)
                      for obj in obstacles if obj != moving]
            reach = axis * distance_mm
            if rotation_radians:
                pivot = ((moving_body.lower + moving_body.upper) / 2 if pivot_world is None
                         else (pivot_world - reference) * unit)
                sweep = RotarySweep.make(moving_body, pivot, rotation_axis, reach, rotation_radians)
                return rotary_hit(context, transaction, moving_body, bodies, sweep, distance_mm, sample_mm)
            swept = bounds((moving_body.lower, moving_body.upper,
                            moving_body.lower + reach, moving_body.upper + reach))
            nearby = [body for body in bodies if candidate_pair(*swept, body)]
            if not nearby:
                return None
            moving_points = [vertex.co.copy() for vertex in moving_body.mesh.vertices]
            moving_tree = hierarchy(triangles_from(moving_body.mesh, moving_points))
            probe = transaction.own_mesh(moving_body.mesh.copy())
            engine = ExactBoolean(context, transaction)
            found = None
            for index, body in enumerate(nearby, start=1):
                low = found.distance_mm if found is not None else 0
                window = box_interval(moving_tree, body, axis, (low, distance_mm))
                if window is None:
                    wm.progress_update(index)
                    continue
                points = [vertex.co.copy() for vertex in body.mesh.vertices]
                obstacle = hierarchy(triangles_from(body.mesh, points))
                for distance in probe_positions(moving_tree, obstacle, axis, window, steps, distance_mm):
                    offset = axis * distance
                    if not candidate_pair(moving_body.lower + offset, moving_body.upper + offset, body):
                        continue
                    for original, vertex in zip(moving_points, probe.vertices, strict=True):
                        vertex.co = original + offset
                    probe.update()
                    volume = measure_intersection(engine, probe, body.mesh)
                    if volume > BOOLEAN_VOLUME_NOISE:
                        found = InsertionHit(body.obj, distance, volume)
                        break
                wm.progress_update(index)
            return found
    finally:
        wm.progress_end()
        context.view_layer.update()


def rotary_hit(
    context: bpy.types.Context, transaction: GeometryTransaction, moving: Body, obstacles: list[Body],
    sweep: RotarySweep, distance_mm: float, sample_mm: float,
) -> InsertionHit | None:
    points = [vertex.co.copy() for vertex in moving.mesh.vertices]
    probe = transaction.own_mesh(moving.mesh.copy())
    engine = ExactBoolean(context, transaction)
    found = None
    first = 0.0
    tests = 0
    for index, obstacle in enumerate(obstacles, start=1):
        for fraction in rotation_probes(sweep, obstacle, first, sample_mm):
            rotation, offset = sweep.pose(fraction)
            if not candidate_pair(*bounds(rotation @ corner + offset for corner in sweep.corners), obstacle):
                continue
            tests += 1
            if tests > MAX_ROTARY_TESTS:
                raise MeshError(ROTATION_LIMIT_ERROR)
            for original, vertex in zip(points, probe.vertices, strict=True):
                vertex.co = rotation @ original + offset
            probe.update()
            volume = measure_intersection(engine, probe, obstacle.mesh)
            if volume > BOOLEAN_VOLUME_NOISE:
                found = InsertionHit(obstacle.obj, fraction * distance_mm, volume, fraction * sweep.angle)
                first = fraction
                break
        context.window_manager.progress_update(index)
    return found
