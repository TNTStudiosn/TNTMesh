# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d
from mathutils import Euler, Vector

from .geometry.planar import axis_frame
from .localization import tr
from .model import MeshError, millimeters_per_unit
from .operators import MeshOperator, active_mesh, report_failure
from .viewport import project_bounds

_sessions: list["TNTMESH_OT_draw_plane"] = []


def fit_plane(
    context: bpy.types.Context,
    obj: bpy.types.Object,
    region: bpy.types.Region,
    view: bpy.types.RegionView3D,
    start: Vector,
    end: Vector,
) -> tuple[Euler, float]:
    if (end - start).length < 4.0:
        raise MeshError("Move the second point farther from the first.")
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    pivot = evaluated.matrix_world @ (sum(map(Vector, evaluated.bound_box), Vector((0, 0, 0))) / 8)
    point_a = region_2d_to_location_3d(region, view, start, pivot)
    point_b = region_2d_to_location_3d(region, view, end, pivot)
    view_ray = region_2d_to_vector_3d(region, view, start)
    normal = (point_b - point_a).cross(view_ray)
    if normal.length_squared == 0.0:
        raise MeshError("Move the second point farther from the first.")
    rotation = normal.to_track_quat("Z", "Y").to_euler("XYZ")
    rotation = Euler(tuple(0.0 if abs(angle) < 1e-6 else angle for angle in rotation), "XYZ")
    frame = axis_frame("FREE", tuple(rotation))
    extents = project_bounds(obj, depsgraph, frame)
    if extents is None:
        raise MeshError("The mesh is empty or has invalid coordinates.")
    lower, upper = extents
    distance = frame.col[2].dot(point_a) - (lower.z + upper.z) / 2
    return rotation, distance * millimeters_per_unit(context.scene)


class TNTMESH_OT_draw_plane(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.draw_plane"
    bl_label = "Draw Cut Line"
    bl_description = "Choose two points in the viewport to orient the cut plane"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None and context.area.type == "VIEW_3D"
                and not context.space_data.region_quadviews and MeshOperator.poll(context)
                and context.scene.tntmesh_settings.mode == "EASY"
                and context.scene.tntmesh_settings.cut_kind == "PLANAR")

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if _sessions:
            return {"CANCELLED"}
        self._area = context.area
        self._region = next(region for region in self._area.regions if region.type == "WINDOW")
        self._view = context.space_data.region_3d
        self._source = active_mesh(context)
        self._start = None
        self._pointer = None
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_line, (), "WINDOW", "POST_PIXEL"
        )
        _sessions.append(self)
        self._area.header_text_set(tr("Click the first point of the cut · Esc to cancel"))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if self._handle is None:
            return {"CANCELLED"}
        if (context.area != self._area or active_mesh(context) != self._source
                or event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS"):
            self.cleanup()
            return {"CANCELLED"}
        x, y = event.mouse_x - self._region.x, event.mouse_y - self._region.y
        inside = 0 <= x < self._region.width and 0 <= y < self._region.height
        if event.type == "MOUSEMOVE":
            self._pointer = Vector((x, y)) if inside else None
            self._area.tag_redraw()
        if event.type != "LEFTMOUSE" or event.value != "PRESS" or not inside:
            return {"PASS_THROUGH"}
        if any(region.type in {"UI", "TOOLS"} and region.width > 1 and region.height > 1
               and region.x <= event.mouse_x < region.x + region.width
               and region.y <= event.mouse_y < region.y + region.height
               for region in self._area.regions):
            return {"RUNNING_MODAL"}

        click = Vector((x, y))
        if self._start is None:
            self._start = click
            self._area.header_text_set(tr("Click the second point of the cut · Esc to cancel"))
            return {"RUNNING_MODAL"}
        try:
            rotation, offset = fit_plane(context, self._source, self._region,
                                         self._view, self._start, click)
        except MeshError as error:
            self.report({"WARNING"}, tr(str(error)))
            return {"RUNNING_MODAL"}
        except RuntimeError as error:
            self.cleanup()
            return report_failure(self, error)
        settings = context.scene.tntmesh_settings
        settings.rotation = rotation
        settings.offset = offset
        settings.axis = "FREE"
        settings.show_plane = True
        self.cleanup()
        return {"FINISHED"}

    def _draw_line(self) -> None:
        if self._start is None or self._pointer is None or bpy.context.region != self._region:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader

        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        shader.bind()
        shader.uniform_float("color", (0.0, 1.0, 1.0, 1.0))
        batch_for_shader(shader, "LINES", {"pos": (self._start, self._pointer)}).draw(shader)

    def cleanup(self) -> None:
        if self._handle is None:
            return
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
        self._handle = None
        _sessions.remove(self)
        try:
            self._area.header_text_set(None)
            self._area.tag_redraw()
        except ReferenceError:
            # The user can close the viewport while the modal operator is active.
            pass

    def cancel(self, context: bpy.types.Context) -> None:
        self.cleanup()


def cancel_sessions() -> None:
    for session in _sessions[:]:
        session.cleanup()
