# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite

import bpy
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from mathutils import Matrix, Vector

from .geometry.diagnostics import Diagnostics, Marker, scan
from .geometry.mesh import bounds, evaluated_mm
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .operators import MeshOperator, active_mesh, report_failure

LABELS = {
    "EMPTY": "No faces", "INVALID": "Invalid coordinates", "OPEN": "Open edges",
    "NON_MANIFOLD": "Non-manifold geometry", "WINDING": "Inconsistent winding",
    "ZERO_EDGE": "Zero-length edges", "DEGENERATE": "Degenerate triangles",
    "DUP_VERT": "Near-duplicate vertices", "DUP_FACE": "Duplicate faces",
    "VOLUME": "Nonpositive enclosed volume", "SHELLS": "Disconnected surface shells",
    "FRAGMENT": "Small closed shells", "INTERSECTION": "Faces with intersections",
    "CAVITY": "Closed cavities", "INTERNAL": "Miswound internal shells",
    "INVERTED": "Inverted shells",
    "COPLANAR": "Overlapping coplanar faces", "THIN_WALL": "Thin wall faces",
    "SUCTION": "Possible suction regions",
}
INFORMATIONAL = {"SHELLS", "CAVITY"}
FINDINGS = [("ALL", "All Findings", "")] + [
    (key, label, "") for key, label in LABELS.items()
]


@dataclass
class WallOverlay:
    vertices: np.ndarray
    colors: np.ndarray
    limits: tuple[float, float] | None
    batch: object = None


def wall_overlay(mesh: bpy.types.Mesh, report: Diagnostics, origin: Vector, unit: float) -> WallOverlay | None:
    if report.wall_map_mm is None:
        return None
    values = np.frombuffer(report.wall_map_mm, dtype=np.float32)
    known = values >= 0
    measured = values[known]
    limits = (float(measured.min()), float(measured.max())) if measured.size else None
    low = report.wall_limit_mm or (limits[0] if limits else 0)
    high = low * 2 if report.wall_limit_mm else (limits[1] if limits else 0)
    palette = ((.77, .08, .25), (1.0, .28, .23), (1.0, .68, .17), (.08, .77, .88))
    colors = np.tile(np.asarray((.38, .42, .48, 1), dtype=np.float32), (len(values), 1))
    if measured.size:
        mid = low if report.wall_limit_mm else (low + high) / 2
        ramp = (0, mid * .8, mid, max(high, mid + .00001))
        for channel, color_stops in enumerate(zip(*palette, strict=True)):
            colors[known, channel] = np.interp(measured, ramp, color_stops)
    coordinates = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", coordinates)
    coordinates = coordinates.reshape((-1, 3))
    coordinates /= unit
    coordinates += tuple(origin)
    triangle_indices = np.empty(len(values) * 3, dtype=np.int32)
    mesh.loop_triangles.foreach_get("vertices", triangle_indices)
    return WallOverlay(coordinates[triangle_indices], np.repeat(colors, 3, axis=0), limits)


@dataclass
class Preview:
    scene: int
    object: int
    mesh: int
    matrix: Matrix
    unit: float
    result: Diagnostics
    marks: dict[str, list[Marker]]
    overlay: WallOverlay | None = None
    show_wall_map: bool = False
    kind: str = "ALL"
    resin_input: tuple[tuple[float, float, float], float] | None = None


_preview: Preview | None = None
_handle = None


def redraw(window_manager: bpy.types.WindowManager) -> None:
    for window in window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


@persistent
def clear(*_args: object) -> None:
    global _preview
    _preview = None


@persistent
def invalidate(_scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
    if _preview is not None and any(
        update.id.original.as_pointer() in {_preview.object, _preview.mesh}
        and (update.is_updated_geometry or update.is_updated_transform)
        for update in depsgraph.updates
    ):
        clear()


def resin_input(scene: bpy.types.Scene) -> tuple[tuple[float, float, float], float]:
    settings = scene.tntmesh_resin
    return tuple(settings.print_axis), settings.suction_step_mm


def current(context: bpy.types.Context) -> Preview | None:
    obj = active_mesh(context)
    if (_preview is not None and obj is not None and context.scene.as_pointer() == _preview.scene
            and obj.as_pointer() == _preview.object and obj.data.as_pointer() == _preview.mesh
            and obj.matrix_world == _preview.matrix
            and millimeters_per_unit(context.scene) == _preview.unit
            and (_preview.resin_input is None or _preview.resin_input == resin_input(context.scene))):
        return _preview
    return None


def capture(
    context: bpy.types.Context, analyze: Callable[[bpy.types.Mesh], Diagnostics],
    orientation: tuple[tuple[float, float, float], float] | None = None,
) -> Preview:
    global _preview
    clear()
    obj, scene = active_mesh(context), context.scene
    unit = millimeters_per_unit(scene)
    wm = context.window_manager
    wm.progress_begin(0, 100)
    try:
        with GeometryTransaction() as transaction:
            mesh, origin = evaluated_mm(context, obj, transaction, unit)
            wm.progress_update(10)
            report = analyze(mesh)
            markers = {item.kind: [(origin + a / unit, origin + b / unit) for a, b in item.marks]
                       for item in report.findings if item.marks}
            overlay = wall_overlay(mesh, report, origin, unit)
        context.view_layer.update()
        _preview = Preview(
            scene.as_pointer(), obj.as_pointer(), obj.data.as_pointer(), obj.matrix_world.copy(),
            unit, report, markers, overlay, overlay is not None, resin_input=orientation,
        )
        wm.progress_update(100)
        return _preview
    finally:
        wm.progress_end()
        redraw(wm)


class TNTMESH_OT_diagnose(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.diagnose"
    bl_label = "Scan Mesh"
    bl_description = "Find mesh issues and highlight their locations in the viewport"

    weld_mm: FloatProperty(
        name="Nearby vertex (mm)", min=0, default=.001, precision=4,
        description="Flag vertices within this distance. Zero skips the proximity check",
    )
    fragment_mm3: FloatProperty(
        name="Small shell (mm³)", min=0, default=.05, precision=4,
    )
    intersections: BoolProperty(name="Check intersections", default=True)
    wall_mm: FloatProperty(
        name="Minimum wall (mm)", min=0, default=0, precision=3,
        description="Flag walls thinner than this limit. Zero skips the thickness check",
    )
    wall_map: BoolProperty(name="Wall Thickness Map", description="Color the surface by sampled wall thickness")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self, width=330)

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.use_property_split = True
        for name in ("weld_mm", "fragment_mm3", "wall_mm", "wall_map", "intersections"):
            self.layout.prop(self, name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            report = capture(context, lambda mesh: scan(
                mesh, self.weld_mm, self.fragment_mm3, intersections=self.intersections, wall_mm=self.wall_mm,
                wall_map=self.wall_map,
            )).result
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        issues = sum(item.kind not in INFORMATIONAL for item in report.findings)
        if issues:
            self.report({"WARNING"}, tr("Mesh scan found {count} issue categories.").format(
                count=issues,
            ))
        elif report.findings:
            self.report({"INFO"}, tr("Review the shells and cavities in Mesh Diagnostics."))
        else:
            self.report({"INFO"}, tr("No issues found in the enabled checks."))
        return {"FINISHED"}


class TNTMESH_OT_check_resin(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.check_resin"
    bl_label = "Check Resin Traps"
    bl_description = "Find closed cavities and estimate suction as layers build along the print direction"

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = resin_input(context.scene)
        axis, step = source
        if not all(map(isfinite, axis)) or Vector(axis).length < 1e-8:
            return report_failure(self, MeshError("Enter a nonzero print direction."))
        try:
            report = capture(context, lambda mesh: scan(
                mesh, 0, 0, intersections=True, print_direction=Vector(axis), suction_step_mm=step,
                suction_progress=lambda ratio: context.window_manager.progress_update(20 + 75 * ratio),
            ), orientation=source).result
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        closed = next((item.count for item in report.findings if item.kind == "CAVITY"), 0)
        if report.suction is None:
            self.report({"WARNING"}, tr("Suction analysis needs a closed solid with consistent faces."))
        elif closed or report.suction.count or report.suction.uncertain_rows:
            self.report({"WARNING"}, tr("Review resin trap results in Resin Preparation."))
        else:
            self.report({"INFO"}, tr("No resin traps found at this sampling step."))
        return {"FINISHED"}


class TNTMESH_OT_diagnostic_view(bpy.types.Operator):
    bl_idname = "tntmesh.diagnostic_view"
    bl_label = "View Mesh Finding"

    kind: EnumProperty(items=[*FINDINGS, ("MAP", "Wall Thickness Map", ""), ("CLEAR", "Clear Findings", "")])
    focus: BoolProperty()

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return current(context) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        preview = current(context)
        if self.kind == "CLEAR":
            clear()
        elif self.kind == "MAP" and preview.overlay is not None:
            preview.show_wall_map = not preview.show_wall_map
        elif self.kind == "ALL":
            preview.kind = "ALL"
        elif self.kind in preview.marks:
            preview.kind = self.kind
            if self.focus and context.area is not None and context.area.type == "VIEW_3D":
                low, high = bounds(point for segment in preview.marks[self.kind] for point in segment)
                view = context.space_data.region_3d
                view.view_location = (low + high) / 2
                unit = millimeters_per_unit(context.scene)
                view.view_distance = max(2.5 * (high - low).length, 2.0 / unit)
        redraw(context.window_manager)
        return {"FINISHED"}


def controls(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    preview = current(context)
    if preview is None:
        layout.operator("tntmesh.diagnose", icon="VIEWZOOM")
        return
    box = layout.box()
    box.label(text="Mesh Findings", icon="INFO")
    if preview.result.volume_mm3 is not None:
        box.label(text=f"{preview.result.volume_mm3:.2f} mm³", translate=False)
    if not preview.result.findings:
        box.label(text="No issues found in the enabled checks.", icon="CHECKMARK")
    for item in preview.result.findings:
        row = box.row(align=True)
        text = f"{tr(LABELS[item.kind])} · {item.count}"
        if item.kind in preview.marks:
            op = row.operator("tntmesh.diagnostic_view", text=text, translate=False,
                              depress=preview.kind == item.kind)
            op.kind = item.kind
            zoom = row.operator("tntmesh.diagnostic_view", text="", icon="VIEWZOOM")
            zoom.kind = item.kind
            zoom.focus = True
        else:
            row.label(text=text, translate=False)
    if not preview.result.checked_intersections:
        box.label(text="Intersection check skipped", icon="INFO")
    if preview.overlay is not None:
        box.operator("tntmesh.diagnostic_view", text="Wall Thickness Map", icon="SHADING_RENDERED",
                     depress=preview.show_wall_map).kind = "MAP"
        if preview.show_wall_map:
            if preview.overlay.limits is None:
                box.label(text="No reliable wall samples.", icon="INFO")
            else:
                thin, thick = preview.overlay.limits
                legend = tr("Samples · {thin:.2f}–{thick:.2f} mm").format(thin=thin, thick=thick)
                box.label(text=legend, translate=False)
                box.label(text="Thin in red · thick in cyan")
                box.label(text="Unmeasured in gray")
    if preview.result.wall_limit_mm:
        if not preview.result.checked_walls:
            box.label(text="Wall check needs a closed solid.", icon="INFO")
        elif preview.result.thinnest_wall_mm is not None:
            text = tr("Thinnest sample · {size:.3f} mm").format(size=preview.result.thinnest_wall_mm)
            box.label(text=text, translate=False)
        else:
            text = tr("No samples below {size:.3f} mm").format(size=preview.result.wall_limit_mm)
            box.label(text=text, translate=False)
    if preview.kind != "ALL":
        box.operator("tntmesh.diagnostic_view", text="All Findings").kind = "ALL"
    row = box.row(align=True)
    row.operator("tntmesh.diagnose", text="Scan Again", icon="FILE_REFRESH")
    row.operator("tntmesh.diagnostic_view", text="Clear Findings", icon="X").kind = "CLEAR"


def draw() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    preview = current(bpy.context)
    if preview is None or bpy.context.mode != "OBJECT":
        return
    overlay = preview.overlay
    if preview.show_wall_map and overlay is not None:
        shader = gpu.shader.from_builtin("SMOOTH_COLOR")
        if overlay.batch is None:
            overlay.batch = batch_for_shader(shader, "TRIS", {"pos": overlay.vertices, "color": overlay.colors})
        depth = gpu.state.depth_test_get()
        try:
            gpu.state.depth_test_set("LESS_EQUAL")
            # Bias the overlay in clip space so coplanar faces keep their color at any zoom.
            with gpu.matrix.push_pop_projection():
                projection = gpu.matrix.get_projection_matrix()
                projection[2] = projection[2] - projection[3] * .00001
                gpu.matrix.load_projection_matrix(projection)
                overlay.batch.draw(shader)
        finally:
            gpu.state.depth_test_set(depth)
        if preview.kind == "ALL":
            return
    if not preview.marks:
        return
    marker_sets = preview.marks.values() if preview.kind == "ALL" else (preview.marks[preview.kind],)
    markers = [marker for group in marker_sets for marker in group]
    endpoints = [point for a, b in markers if a != b for point in (a, b)]
    centers = [(a + b) / 2 for a, b in markers]
    shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    depth = gpu.state.depth_test_get()
    # Use the shader uniform instead of changing the global point size.
    gpu.state.depth_test_set("NONE")
    try:
        if endpoints:
            shader.bind()
            shader.uniform_float("viewportSize", gpu.state.viewport_get()[2:])
            shader.uniform_float("lineWidth", 2.5)
            shader.uniform_float("color", (1.0, 0.48, 0.92, 1.0))
            batch_for_shader(shader, "LINES", {"pos": endpoints}).draw(shader)
        points = gpu.shader.from_builtin("POINT_UNIFORM_COLOR")
        points.bind()
        points.uniform_float("size", 6.0)
        points.uniform_float("color", (1.0, 0.48, 0.92, 1.0))
        batch_for_shader(points, "POINTS", {"pos": centers}).draw(points)
    finally:
        gpu.state.depth_test_set(depth)


def register() -> None:
    global _handle
    if not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", "POST_VIEW")
    bpy.app.handlers.depsgraph_update_post.append(invalidate)
    for handlers in (bpy.app.handlers.load_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        handlers.append(clear)


def unregister() -> None:
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
    for handlers, callback in (
        (bpy.app.handlers.depsgraph_update_post, invalidate), (bpy.app.handlers.load_post, clear),
        (bpy.app.handlers.undo_post, clear), (bpy.app.handlers.redo_post, clear),
    ):
        if callback in handlers:
            handlers.remove(callback)
    clear()


CLASSES = (TNTMESH_OT_diagnose, TNTMESH_OT_check_resin, TNTMESH_OT_diagnostic_view)
