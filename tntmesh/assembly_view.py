# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.app.handlers import persistent
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Vector

from . import assembly
from .localization import tr
from .model import millimeters_per_unit

PALETTE = ((0.0, 0.92, 0.94), (0.64, 0.43, 0.98), (0.25, 0.62, 1.0), (0.28, 0.9, 0.67))
DETAIL_LIMIT = 150_000
LIGHT = Vector((0.35, -0.45, 1)).normalized()
BOX_EDGES = [(i, i ^ (1 << axis)) for i in range(8) for axis in range(3) if not i & (1 << axis)]
_handles = []
_batches = {}


@persistent
def invalidate(_scene=None, depsgraph=None, *_args):
    if depsgraph is None or any(update.is_updated_geometry or update.is_updated_transform
                               for update in depsgraph.updates):
        _batches.clear()


def enabled(context: bpy.types.Context) -> bool:
    state = context.scene.tntmesh_assembly
    return context.mode == "OBJECT" and (state.distance > 0 or state.hinge_fraction > 0 or bool(state.hinge_blocker))


def offsets(
    context: bpy.types.Context, rotate: bool = False,
) -> list[tuple[bpy.types.Object, Vector, Vector]]:
    scene = context.scene
    return assembly.explosion_offsets(
        assembly.members(context), context.evaluated_depsgraph_get(),
        0 if rotate else scene.tntmesh_assembly.distance / millimeters_per_unit(scene),
    )


def box_vertices(low: Vector, high: Vector) -> list[tuple[float, float, float]]:
    return [tuple(high[axis] if corner & (1 << axis) else low[axis] for axis in range(3))
            for corner in range(8)]


def batch(obj, depsgraph, color, shader, wire):
    from gpu_extras.batch import batch_for_shader

    key = depsgraph.as_pointer(), obj.as_pointer(), color
    if key in _batches:
        return _batches[key]
    if len(_batches) >= 64:
        _batches.clear()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.data
    world = evaluated.matrix_world
    simple = len(mesh.polygons) > DETAIL_LIMIT
    if simple:
        vertices = box_vertices(*assembly.world_box(obj, depsgraph))
        geometry = batch_for_shader(wire, "LINES", {"pos": vertices}, indices=BOX_EDGES)
    else:
        mesh.calc_loop_triangles()
        world_vertices = [world @ vertex.co for vertex in mesh.vertices]
        normal_matrix = world.to_3x3().inverted_safe().transposed()
        positions, colors = [], []
        for tri in mesh.loop_triangles:
            normal = (normal_matrix @ tri.normal).normalized()
            shade = 0.43 + 0.57 * max(0.0, normal.dot(LIGHT))
            tint = (*(channel * shade for channel in color), 0.82)
            positions.extend(world_vertices[index] for index in tri.vertices)
            colors.extend((tint, tint, tint))
        geometry = (
            batch_for_shader(shader, "TRIS", {"pos": positions, "color": colors})
            if positions else None
        )
    _batches[key] = geometry, simple
    return geometry, simple


def draw() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    context = bpy.context
    if not enabled(context):
        return
    state = context.scene.tntmesh_assembly
    fraction = state.hinge_fraction
    motion = assembly.hinge_motion(context) if fraction or state.hinge_blocker else None
    if motion is None and not state.distance:
        return
    placements = offsets(context, motion is not None)
    if len(placements) < 2:
        return
    depsgraph = context.evaluated_depsgraph_get()
    shader = gpu.shader.from_builtin("SMOOTH_COLOR")
    wire = gpu.shader.from_builtin("UNIFORM_COLOR")
    blend = gpu.state.blend_get()
    depth = gpu.state.depth_test_get()
    depth_mask = gpu.state.depth_mask_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    gpu.state.depth_mask_set(True)
    try:
        for index, (obj, pivot, offset) in enumerate(placements):
            if motion is not None and motion.moving != obj:
                continue
            color = tuple(obj.color[:3])
            if color == (1, 1, 1):
                color = PALETTE[index % len(PALETTE)]
            geometry, simple = batch(obj, depsgraph, color, shader, wire)
            if geometry is None:
                continue
            with gpu.matrix.push_pop():
                gpu.matrix.translate(offset)
                if motion is not None and motion.moving == obj:
                    gpu.matrix.multiply_matrix(motion.matrix(fraction))
                use_shader = wire if simple else shader
                use_shader.bind()
                if simple:
                    wire.uniform_float("color", (*color, 0.9))
                geometry.draw(use_shader)
            if offset.length_squared:
                wire.bind()
                wire.uniform_float("color", (*color, 0.65))
                batch_for_shader(wire, "LINES", {"pos": [pivot, pivot + offset]}).draw(wire)
        if motion is not None and state.hinge_blocker:
            obstacle = next((obj for obj, _, _ in placements if obj.name == state.hinge_blocker), None)
            if obstacle is not None:
                gpu.state.depth_test_set("NONE")
                wire.bind()
                wire.uniform_float("color", (1.0, .32, .24, 1))
                vertices = box_vertices(*assembly.world_box(obstacle, depsgraph))
                batch_for_shader(wire, "LINES", {"pos": vertices}, indices=BOX_EDGES).draw(wire)
    finally:
        gpu.state.depth_mask_set(depth_mask)
        gpu.state.depth_test_set(depth)
        gpu.state.blend_set(blend)


def draw_labels() -> None:
    import blf

    context = bpy.context
    if not enabled(context):
        return
    state = context.scene.tntmesh_assembly
    fraction = state.hinge_fraction
    motion = assembly.hinge_motion(context) if fraction or state.hinge_blocker else None
    if motion is None and not state.distance:
        return
    placements = offsets(context, motion is not None)
    if len(placements) < 2:
        return
    font = 0
    blf.size(font, 13 * context.preferences.system.ui_scale)
    depsgraph = context.evaluated_depsgraph_get()
    for obj, pivot, offset in placements:
        blocked = motion is not None and obj.name == state.hinge_blocker
        if motion is not None:
            if obj == motion.moving:
                pivot = motion.matrix(fraction) @ pivot
            elif not blocked:
                continue
        point = location_3d_to_region_2d(context.region, context.region_data, pivot + offset)
        if point is not None and 0 <= point.x < context.region.width and 0 <= point.y < context.region.height:
            label = obj.name
            if len(obj.evaluated_get(depsgraph).data.polygons) > DETAIL_LIMIT:
                label = tr("{name} · bounds").format(name=label)
            blf.color(font, *((1.0, .53, .47, 1) if blocked else (.93, .97, 1, 1)))
            blf.position(font, point.x + 7, point.y + 8, 0)
            blf.draw(font, label)


def register() -> None:
    if not bpy.app.background:
        for callback, stage in ((draw, "POST_VIEW"), (draw_labels, "POST_PIXEL")):
            _handles.append(bpy.types.SpaceView3D.draw_handler_add(callback, (), "WINDOW", stage))
        bpy.app.handlers.depsgraph_update_post.append(invalidate)
        bpy.app.handlers.load_post.append(invalidate)


def unregister() -> None:
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), "WINDOW")
    for events in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post):
        if invalidate in events:
            events.remove(invalidate)
    invalidate()
