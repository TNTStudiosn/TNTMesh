# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from mathutils import Matrix

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
}
FINDINGS = [("ALL", "All Findings", "")] + [
    (key, label, "") for key, label in LABELS.items()
]


@dataclass
class Preview:
    scene: int
    object: int
    mesh: int
    matrix: Matrix
    unit: float
    result: Diagnostics
    marks: dict[str, list[Marker]]
    kind: str = "ALL"


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


def current(context: bpy.types.Context) -> Preview | None:
    obj = active_mesh(context)
    if (_preview is not None and obj is not None and context.scene.as_pointer() == _preview.scene
            and obj.as_pointer() == _preview.object and obj.data.as_pointer() == _preview.mesh
            and obj.matrix_world == _preview.matrix
            and millimeters_per_unit(context.scene) == _preview.unit):
        return _preview
    return None


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

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self, width=330)

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.use_property_split = True
        for name in ("weld_mm", "fragment_mm3", "intersections"):
            self.layout.prop(self, name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        global _preview
        clear()
        obj = active_mesh(context)
        scene = context.scene
        unit = millimeters_per_unit(scene)
        wm = context.window_manager
        wm.progress_begin(0, 2)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, obj, transaction, unit)
                wm.progress_update(1)
                report = scan(mesh, self.weld_mm, self.fragment_mm3, intersections=self.intersections)
                markers = {item.kind: [(origin + a / unit, origin + b / unit) for a, b in item.marks]
                           for item in report.findings if item.marks}
            context.view_layer.update()
            _preview = Preview(
                scene.as_pointer(), obj.as_pointer(), obj.data.as_pointer(), obj.matrix_world.copy(),
                unit, report, markers,
            )
            wm.progress_update(2)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            redraw(wm)
        if report.findings:
            self.report({"WARNING"}, tr("Mesh scan found {count} issue categories.").format(
                count=len(report.findings),
            ))
        else:
            self.report({"INFO"}, tr("No issues found in the enabled checks."))
        return {"FINISHED"}


class TNTMESH_OT_diagnostic_view(bpy.types.Operator):
    bl_idname = "tntmesh.diagnostic_view"
    bl_label = "View Mesh Finding"

    kind: EnumProperty(items=[*FINDINGS, ("CLEAR", "Clear Findings", "")])
    focus: BoolProperty()

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return current(context) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        preview = current(context)
        if self.kind == "CLEAR":
            clear()
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
    if preview.kind != "ALL":
        box.operator("tntmesh.diagnostic_view", text="All Findings").kind = "ALL"
    row = box.row(align=True)
    row.operator("tntmesh.diagnose", text="Scan Again", icon="FILE_REFRESH")
    row.operator("tntmesh.diagnostic_view", text="Clear Findings", icon="X").kind = "CLEAR"


def draw() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    preview = current(bpy.context)
    if preview is None or not preview.marks or bpy.context.mode != "OBJECT":
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


CLASSES = (TNTMESH_OT_diagnose, TNTMESH_OT_diagnostic_view)
