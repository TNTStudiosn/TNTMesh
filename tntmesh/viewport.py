# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector

from .geometry.mesh import bounds
from .geometry.planar import axis_frame
from .model import millimeters_per_unit
from .operators import active_mesh

_handle = None
_preview_bounds: dict[tuple[int, int, str], tuple[Vector, Vector]] = {}


@persistent
def invalidate_bounds(*_args: object) -> None:
    _preview_bounds.clear()


def project_bounds(
    obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph, axis: str, frame: Matrix
) -> tuple[Vector, Vector] | None:
    key = (depsgraph.as_pointer(), obj.as_pointer(), axis)
    if key in _preview_bounds:
        return _preview_bounds[key]
    evaluated = obj.evaluated_get(depsgraph)
    if not evaluated.data.vertices:
        return None
    transform = frame.transposed().to_4x4() @ evaluated.matrix_world
    result = bounds(transform @ vertex.co for vertex in evaluated.data.vertices)
    _preview_bounds[key] = result
    return result


def draw_plane() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    context = bpy.context
    settings = context.scene.tntmesh_settings
    obj = active_mesh(context)
    if context.mode != "OBJECT" or settings.mode != "EASY" or not settings.show_plane or obj is None:
        return
    frame = axis_frame(settings.axis)
    extents = project_bounds(obj, context.evaluated_depsgraph_get(), settings.axis, frame)
    if extents is None:
        return
    lower, upper = extents
    pad = (upper - lower).length * 0.06
    unit = millimeters_per_unit(context.scene)
    z = (lower.z + upper.z) * 0.5 + settings.offset / unit
    separation = settings.kerf / unit / 2
    heights = (z,) if separation == 0.0 else (z - separation, z + separation)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    previous_blend = gpu.state.blend_get()
    previous_depth = gpu.state.depth_test_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    try:
        for height in heights:
            vertices = [
                frame @ Vector((x, y, height))
                for x, y in ((lower.x - pad, lower.y - pad), (upper.x + pad, lower.y - pad),
                             (upper.x + pad, upper.y + pad), (lower.x - pad, upper.y + pad))
            ]
            shader.bind()
            shader.uniform_float("color", (0.0, 1.0, 1.0, 0.16))
            batch_for_shader(shader, "TRI_FAN", {"pos": vertices}).draw(shader)
            shader.uniform_float("color", (0.0, 1.0, 1.0, 0.9))
            batch_for_shader(shader, "LINE_STRIP", {"pos": vertices + vertices[:1]}).draw(shader)
    finally:
        gpu.state.depth_test_set(previous_depth)
        gpu.state.blend_set(previous_blend)


def register() -> None:
    global _handle
    if not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(draw_plane, (), "WINDOW", "POST_VIEW")
        bpy.app.handlers.load_post.append(invalidate_bounds)
        bpy.app.handlers.depsgraph_update_post.append(invalidate_bounds)


def unregister() -> None:
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
        bpy.app.handlers.depsgraph_update_post.remove(invalidate_bounds)
        bpy.app.handlers.load_post.remove(invalidate_bounds)
    invalidate_bounds()
