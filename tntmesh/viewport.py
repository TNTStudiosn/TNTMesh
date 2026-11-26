# SPDX-License-Identifier: GPL-3.0-or-later
from math import cos, sin, tau

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector

from .geometry.mesh import bounds
from .geometry.planar import axis_frame
from .geometry.polygon import extended_path
from .geometry.region import RegionCut, boundary_edges, edge_map, region_faces, smooth_boundary
from .geometry.symmetry import reflected_plane
from .geometry.volume import bezier_path, outline
from .model import MeshError, millimeters_per_unit
from .operators import active_mesh
from .printer_props import selected_printer
from .printing import fit
from .settings import TNTMESH_PG_settings

_handles = []
_preview_bounds: dict[tuple[int, int, tuple], tuple[Vector, Vector]] = {}
_region_preview: dict[tuple[int, int, RegionCut], tuple[list[Vector], list[Vector]]] = {}


@persistent
def invalidate_bounds(*_args: object) -> None:
    _preview_bounds.clear()
    _region_preview.clear()


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


class TNTMESH_GGT_cut_offset(bpy.types.GizmoGroup):
    bl_idname = "TNTMESH_GGT_cut_offset"
    bl_label = "Move Cut Plane"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"3D", "PERSISTENT"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        from .draw_cut import drawing_active

        settings = context.scene.tntmesh_settings
        return (context.mode == "OBJECT" and settings.mode == "EASY"
                and settings.cut_kind in {"PLANAR", "SYMMETRY"}
                and settings.show_plane and settings.show_cut_handle
                and active_mesh(context) is not None and not drawing_active())

    def setup(self, context: bpy.types.Context) -> None:
        gizmo = self.gizmos.new("GIZMO_GT_arrow_3d")
        gizmo.color = (0.0, 0.86, 0.92)
        gizmo.alpha = .9
        gizmo.color_highlight = (0.42, 1.0, 1.0)
        gizmo.alpha_highlight = 1.0
        gizmo.use_draw_modal = True
        gizmo.scale_basis = .74
        gizmo.line_width = 2
        self.handle = gizmo
        self._binding = None

    def draw_prepare(self, context: bpy.types.Context) -> None:
        settings = context.scene.tntmesh_settings
        unit = millimeters_per_unit(context.scene)
        frame = axis_frame(settings.axis, tuple(settings.rotation))
        gizmo = self.handle
        obj = active_mesh(context)
        extents = project_bounds(obj, context.evaluated_depsgraph_get(), frame) if obj is not None else None
        gizmo.hide = extents is None
        if extents is None:
            return
        lower, upper = extents
        matrix = frame.to_4x4()
        matrix.translation = frame @ ((lower + upper) / 2)
        gizmo.matrix_basis = matrix
        binding = settings.as_pointer(), unit, settings.offset
        if not gizmo.is_modal and self._binding != binding:
            gizmo.target_set_prop("offset", settings, "offset_view")
            self._binding = binding


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
    if settings.cut_kind == "PATH":
        center = (lower + upper) / 2 + Vector((*settings.profile_shift, settings.offset)) / unit
        points = [(point.position[0] / unit, point.position[1] / unit) for point in settings.contour]
        try:
            path, _ = extended_path(points, tuple((lower - center).xy), tuple((upper - center).xy),
                                    settings.path_smoothing)
        except MeshError:
            return []
        near, far = center.z - settings.contour_depth / unit / 2, center.z + settings.contour_depth / unit / 2
        return [([(center.x + x, center.y + y, level) for x, y in path], False) for level in (near, far)]
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
    if settings.cut_kind in {"OBJECT", "BASE"}:
        return
    if settings.cut_kind == "REGION":
        draw_region(context, obj, settings.region_config())
        return
    frame = axis_frame(settings.axis, tuple(settings.rotation))
    extents = project_bounds(obj, context.evaluated_depsgraph_get(), frame)
    if extents is None:
        return
    lower, upper = extents
    unit = millimeters_per_unit(context.scene)
    reflected = None
    if settings.cut_kind == "SYMMETRY":
        limits = project_bounds(obj, context.evaluated_depsgraph_get(), Matrix.Identity(3))
        if limits is not None:
            midpoint = (limits[0] + limits[1]) / 2
            axis = "XYZ".index(settings.symmetry_axis)
            center = midpoint[axis] + settings.symmetry_center / unit
            position = (lower.z + upper.z) / 2 + settings.offset / unit
            _, _, reflected = reflected_plane(
                frame, position, midpoint, settings.symmetry_axis, center,
                settings.symmetry_secondary / unit, tuple(settings.symmetry_rotation),
            )
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    previous_blend = gpu.state.blend_get()
    previous_depth = gpu.state.depth_test_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    try:
        for points, fill in cutter_paths(settings, lower, upper, unit):
            vertices = [frame @ Vector(point) for point in points]
            overlays = [(vertices, (0.0, 1.0, 1.0))]
            if reflected is not None:
                overlays.append(([reflected @ point for point in vertices], (0.68, 0.48, 1.0)))
            for coordinates, color in overlays:
                shader.bind()
                if fill:
                    shader.uniform_float("color", (*color, 0.16))
                    batch_for_shader(shader, "TRI_FAN", {"pos": coordinates}).draw(shader)
                    coordinates = [*coordinates, coordinates[0]]
                shader.uniform_float("color", (*color, 0.9))
                batch_for_shader(shader, "LINE_STRIP", {"pos": coordinates}).draw(shader)
        if settings.cut_kind == "PLANAR" and settings.connector in {"ROUND", "HEX", "MAGNET"} and settings.connector_points:
            from .draw_cut import model_pivot

            origin = model_pivot(obj.evaluated_get(context.evaluated_depsgraph_get()))
            center = frame.transposed() @ origin
            height = (lower.z + upper.z) / 2 + settings.offset / unit
            if settings.connector == "MAGNET":
                outline = settings.magnet_config(1).profile()
            else:
                profile = settings.standard_connector(settings.connector, 1)
                radius = profile.socket_radius
                outline = [(radius * cos(tau * i / profile.sides), radius * sin(tau * i / profile.sides))
                           for i in range(profile.sides)]
            gpu.state.depth_test_set("NONE")
            shader.bind()
            shader.uniform_float("color", (.78, .55, 1.0, 1.0))
            for point in settings.connector_points:
                x, y = point.position
                ring = [frame @ Vector((center.x + (x + a) / unit, center.y + (y + b) / unit, height))
                        for a, b in outline]
                batch_for_shader(shader, "LINE_STRIP", {"pos": [*ring, ring[0]]}).draw(shader)
    finally:
        gpu.state.depth_test_set(previous_depth)
        gpu.state.blend_set(previous_blend)


def draw_region(context: bpy.types.Context, obj: bpy.types.Object, config: RegionCut) -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    depsgraph = context.evaluated_depsgraph_get()
    key = (depsgraph.as_pointer(), obj.as_pointer(), config)
    if key not in _region_preview:
        _region_preview.clear()
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.data
        world = evaluated.matrix_world
        normal_matrix = world.to_3x3().inverted_safe().transposed()
        offset = .01 / millimeters_per_unit(context.scene)
        try:
            selected = region_faces(mesh, obj, config)
        except MeshError:
            selected = set()
        if selected:
            mesh.calc_loop_triangles()
        positions = []
        for triangle in mesh.loop_triangles if selected else ():
            if triangle.polygon_index in selected:
                lift = (normal_matrix @ mesh.polygons[triangle.polygon_index].normal).normalized()
                positions.extend(world @ mesh.vertices[index].co + lift * offset
                                 for index in triangle.vertices)
        contour = []
        if selected and config.smoothing:
            edges = boundary_edges(selected, edge_map(mesh))
            vertices = [world @ vertex.co for vertex in mesh.vertices]
            moved = smooth_boundary(mesh, vertices, edges, config.smoothing)
            contour = [moved.get(index, vertices[index]) for edge in edges for index in edge]
        _region_preview[key] = positions, contour
    positions, contour = _region_preview[key]
    if not positions:
        return
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    previous_blend = gpu.state.blend_get()
    previous_depth = gpu.state.depth_test_get()
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("LESS_EQUAL")
    try:
        shader.bind()
        shader.uniform_float("color", (0.0, 1.0, 1.0, 0.38))
        batch_for_shader(shader, "TRIS", {"pos": positions}).draw(shader)
        if contour:
            gpu.state.depth_test_set("NONE")
            shader.uniform_float("color", (0.72, 0.54, 1.0, 1.0))
            batch_for_shader(shader, "LINES", {"pos": contour}).draw(shader)
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
