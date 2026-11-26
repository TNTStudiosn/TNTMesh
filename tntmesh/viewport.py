# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector

from .geometry.mesh import bounds
from .geometry.planar import axis_frame
from .geometry.volume import bezier_path, outline
from .model import MeshError, millimeters_per_unit
from .operators import active_mesh
from .printer_props import selected_printer
from .printing import fit
from .settings import TNTMESH_PG_settings

_handles = []
_preview_bounds: dict[tuple[int, int, tuple], tuple[Vector, Vector]] = {}


@persistent
def invalidate_bounds(*_args: object) -> None:
    _preview_bounds.clear()


def project_bounds(
    obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph, frame: Matrix
) -> tuple[Vector, Vector] | None:
    key = (depsgraph.as_pointer(), obj.as_pointer(), tuple(tuple(row) for row in frame))
    if key in _preview_bounds:
        return _preview_bounds[key]
    evaluated = obj.evaluated_get(depsgraph)
    if not evaluated.data.vertices:
        return None
    transform = frame.transposed().to_4x4() @ evaluated.matrix_world
    result = bounds(transform @ vertex.co for vertex in evaluated.data.vertices)
    if len(_preview_bounds) >= 12:
        _preview_bounds.clear()
    _preview_bounds[key] = result
    return result


def cutter_paths(
    settings: TNTMESH_PG_settings, lower: Vector, upper: Vector, unit: float,
) -> list[tuple[list[tuple[float, float, float]], bool]]:
    if settings.cut_kind == "BEZIER":
        controls = tuple(value / unit for value in settings.curve_controls)
        path = list(bezier_path(lower, upper, settings.offset / unit,
                                controls, settings.curve_samples))
        left = [(x, lower.y, z) for x, z in path]
        right = [(x, upper.y, z) for x, z in path]
        return [(left + right[::-1] + left[:1], False)]
    if settings.cut_kind in {"RECTANGLE", "ELLIPSE", "POLYGON"}:
        center = (lower + upper) / 2
        center += Vector((*settings.profile_shift, settings.offset)) / unit
        if settings.cut_kind == "POLYGON":
            ring = [(point.position[0] / unit, point.position[1] / unit) for point in settings.contour]
            if len(ring) < 3:
                return []
            depth = settings.contour_depth / unit
        else:
            width, height, depth = (value / unit for value in settings.profile_size)
            ring = outline(settings.cut_kind, width, height)
        low = [(center.x + x, center.y + y, center.z - depth / 2) for x, y in ring]
        high = [(center.x + x, center.y + y, center.z + depth / 2) for x, y in ring]
        paths = [(low + low[:1], False), (high + high[:1], False)]
        paths.extend(([low[i], high[i]], False) for i in range(0, len(low), max(1, len(low) // 4)))
        return paths
    pad = (upper - lower).length * 0.06
    z = (lower.z + upper.z) * 0.5 + settings.offset / unit
    separation = settings.kerf / unit / 2
    heights = (z,) if separation == 0.0 else (z - separation, z + separation)
    return [
        ([(lower.x - pad, lower.y - pad, level), (upper.x + pad, lower.y - pad, level),
          (upper.x + pad, upper.y + pad, level), (lower.x - pad, upper.y + pad, level)], True)
        for level in heights
    ]


def draw_plane() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    context = bpy.context
    settings = context.scene.tntmesh_settings
    obj = active_mesh(context)
    if context.mode != "OBJECT" or settings.mode != "EASY" or not settings.show_plane or obj is None:
        return
    if settings.cut_kind == "OBJECT":
        return
    frame = axis_frame(settings.axis, tuple(settings.rotation))
    extents = project_bounds(obj, context.evaluated_depsgraph_get(), frame)
    if extents is None:
        return
    lower, upper = extents
    unit = millimeters_per_unit(context.scene)
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    previous_blend = gpu.state.blend_get()
    previous_depth = gpu.state.depth_test_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    try:
        for points, fill in cutter_paths(settings, lower, upper, unit):
            vertices = [frame @ Vector(point) for point in points]
            shader.bind()
            if fill:
                shader.uniform_float("color", (0.0, 1.0, 1.0, 0.16))
                batch_for_shader(shader, "TRI_FAN", {"pos": vertices}).draw(shader)
                vertices.append(vertices[0])
            shader.uniform_float("color", (0.0, 1.0, 1.0, 0.9))
            batch_for_shader(shader, "LINE_STRIP", {"pos": vertices}).draw(shader)
    finally:
        gpu.state.depth_test_set(previous_depth)
        gpu.state.blend_set(previous_blend)


def register() -> None:
    if not bpy.app.background:
        for draw in (draw_plane, draw_print_volume):
            _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", "POST_VIEW"))
        bpy.app.handlers.load_post.append(invalidate_bounds)
        bpy.app.handlers.depsgraph_update_post.append(invalidate_bounds)


def unregister() -> None:
    while _handles:
        bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), "WINDOW")
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post):
        if invalidate_bounds in handlers:
            handlers.remove(invalidate_bounds)
    invalidate_bounds()


def draw_print_volume() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    context = bpy.context
    scene = context.scene
    if context.mode != "OBJECT" or not scene.tntmesh_settings.show_build_volume:
        return
    selected = selected_printer(scene)
    obj = active_mesh(context)
    if selected is None or obj is None:
        return
    extents = project_bounds(obj, context.evaluated_depsgraph_get(), Matrix.Identity(3))
    if extents is None:
        return
    lower, upper = extents
    unit = millimeters_per_unit(scene)
    profile = selected.data()
    try:
        result = fit(tuple((upper - lower) * unit), profile)
    except MeshError:
        return
    center = (lower + upper) / 2
    x, y, height = (span / unit for span in profile.limits)
    outline = (
        (center.x - x / 2, center.y - y / 2), (center.x + x / 2, center.y - y / 2),
        (center.x + x / 2, center.y + y / 2), (center.x - x / 2, center.y + y / 2),
    )
    vertices = [(a, b, z) for z in (lower.z, lower.z + height) for a, b in outline]
    lines = [(i, (i + 1) % 4) for i in range(4)]
    lines += [(a + 4, b + 4) for a, b in lines] + [(i, i + 4) for i in range(4)]
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    blend = gpu.state.blend_get()
    depth = gpu.state.depth_test_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    try:
        color = (1.0, 0.52, 0.30) if result.exceeded else (0.0, 1.0, 1.0)
        shader.bind()
        shader.uniform_float("color", (*color, 0.9))
        batch_for_shader(shader, "LINES", {"pos": vertices}, indices=lines).draw(shader)
        shader.uniform_float("color", (*color, 0.10))
        batch_for_shader(shader, "TRI_FAN", {"pos": vertices[:4]}).draw(shader)
    finally:
        gpu.state.depth_test_set(depth)
        gpu.state.blend_set(blend)
