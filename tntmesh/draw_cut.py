# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import IntProperty
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d
from mathutils import Euler, Vector

from . import draft
from .geometry.planar import axis_frame
from .geometry.polygon import Point2, closed_outline, path_outline
from .localization import tr
from .model import MeshError, millimeters_per_unit
from .operators import MeshOperator, active_mesh, report_failure
from .settings import TNTMESH_PG_settings
from .viewport import project_bounds

_sessions: list["TNTMESH_OT_draw_plane"] = []


def model_pivot(obj: bpy.types.Object) -> Vector:
    center = sum(map(Vector, obj.bound_box), Vector((0, 0, 0))) / 8
    return obj.matrix_world @ center


def stable_euler(rotation: Euler) -> Euler:
    return Euler(tuple(0.0 if abs(angle) < 1e-6 else angle for angle in rotation), "XYZ")


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
    pivot = model_pivot(evaluated)
    point_a = region_2d_to_location_3d(region, view, start, pivot)
    point_b = region_2d_to_location_3d(region, view, end, pivot)
    view_ray = region_2d_to_vector_3d(region, view, start)
    normal = (point_b - point_a).cross(view_ray)
    if normal.length_squared == 0.0:
        raise MeshError("Move the second point farther from the first.")
    rotation = stable_euler(normal.to_track_quat("Z", "Y").to_euler("XYZ"))
    frame = axis_frame("FREE", tuple(rotation))
    extents = project_bounds(obj, depsgraph, frame)
    if extents is None:
        raise MeshError("The mesh is empty or has invalid coordinates.")
    lower, upper = extents
    distance = frame.col[2].dot(point_a) - (lower.z + upper.z) / 2
    return rotation, distance * millimeters_per_unit(context.scene)


def fit_contour(
    context: bpy.types.Context, obj: bpy.types.Object, region: bpy.types.Region,
    view: bpy.types.RegionView3D, points: list[Vector],
    *, open_path: bool = False,
) -> tuple[Euler, list[Point2], float]:
    depsgraph = context.evaluated_depsgraph_get()
    pivot = model_pivot(obj.evaluated_get(depsgraph))
    rotation = stable_euler(view.view_rotation.to_euler("XYZ"))
    frame = axis_frame("FREE", tuple(rotation))
    extents = project_bounds(obj, depsgraph, frame)
    if extents is None:
        raise MeshError("The mesh is empty or has invalid coordinates.")
    lower, upper = extents
    center = (lower + upper) / 2
    inverse = frame.transposed()
    unit = millimeters_per_unit(context.scene)
    outline = []
    for point in points:
        world = region_2d_to_location_3d(region, view, point, pivot)
        xy = (inverse @ world - center).xy * unit
        outline.append(tuple(xy))
    if open_path:
        settings = context.scene.tntmesh_settings
        path_outline(outline, tuple((lower - center).xy * unit), tuple((upper - center).xy * unit),
                     settings.path_smoothing)
    else:
        outline = closed_outline(outline)
    return rotation, outline, (upper.z - lower.z) * unit * 1.1


class TNTMESH_OT_draw_plane(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.draw_plane"
    bl_label = "Draw on Model"
    bl_description = "Draw a line or contour in the 3D Viewport"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.area is not None and context.area.type == "VIEW_3D"
                and not context.space_data.region_quadviews and MeshOperator.poll(context)
                and context.scene.tntmesh_settings.mode == "EASY"
                and context.scene.tntmesh_settings.cut_kind in {"PLANAR", "POLYGON", "PATH", "SYMMETRY"})

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if _sessions:
            return {"CANCELLED"}
        self._area = context.area
        self._region = next(region for region in self._area.regions if region.type == "WINDOW")
        self._view = context.space_data.region_3d
        self._source = active_mesh(context)
        self._shape = context.scene.tntmesh_settings.cut_kind
        self._is_stroke = self._shape in {"PATH", "POLYGON"}
        self._points = []
        self._dragging = False
        self._pointer = None
        self._handle = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_line, (), "WINDOW", "POST_PIXEL"
        )
        _sessions.append(self)
        instruction = {
            "POLYGON": "Click points or Shift-drag · Enter to close · Esc to cancel",
            "PATH": "Click points or Shift-drag · Enter to finish · Esc to cancel",
        }.get(self._shape, "Click the first point of the cut · Esc to cancel")
        self._area.header_text_set(tr(instruction))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if self._handle is None:
            return {"CANCELLED"}
        if (context.area != self._area or active_mesh(context) != self._source
                or context.scene.tntmesh_settings.cut_kind != self._shape
                or event.type in {"ESC", "RIGHTMOUSE"} and event.value == "PRESS"):
            self.cleanup()
            return {"CANCELLED"}
        x, y = event.mouse_x - self._region.x, event.mouse_y - self._region.y
        inside = 0 <= x < self._region.width and 0 <= y < self._region.height
        in_panel = any(region.type in {"UI", "TOOLS"} and region.width > 1 and region.height > 1
                       and region.x <= event.mouse_x < region.x + region.width
                       and region.y <= event.mouse_y < region.y + region.height
                       for region in self._area.regions)
        if event.type == "MOUSEMOVE":
            self._pointer = Vector((x, y)) if inside and not in_panel else None
            if self._dragging and self._pointer is not None:
                self._add_contour_point(self._pointer)
            self._area.tag_redraw()
        if self._is_stroke:
            if event.type in {"RET", "NUMPAD_ENTER"} and event.value == "PRESS":
                return self._finish_contour(context)
            if event.type == "BACK_SPACE" and event.value == "PRESS" and self._points:
                self._points.pop()
                self._area.tag_redraw()
                return {"RUNNING_MODAL"}
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                self._dragging = False
                return {"RUNNING_MODAL"}
        if event.type != "LEFTMOUSE" or event.value != "PRESS" or not inside:
            return {"PASS_THROUGH"}
        if in_panel:
            return {"RUNNING_MODAL"}

        click = Vector((x, y))
        if self._is_stroke:
            self._dragging = event.shift
            self._add_contour_point(click)
            self._area.tag_redraw()
            return {"RUNNING_MODAL"}
        if not self._points:
            self._points.append(click)
            self._area.header_text_set(tr("Click the second point of the cut · Esc to cancel"))
            return {"RUNNING_MODAL"}
        try:
            rotation, offset = fit_plane(context, self._source, self._region,
                                         self._view, self._points[0], click)
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

    def _add_contour_point(self, point: Vector) -> None:
        if not self._points or (point - self._points[-1]).length >= 4.0:
            if len(self._points) >= 1024:
                self._dragging = False
                self.report({"WARNING"}, tr("The contour has reached 1024 points."))
                return
            self._points.append(point.copy())

    def _finish_contour(self, context: bpy.types.Context) -> set[str]:
        points = self._points
        if self._shape == "POLYGON" and len(points) > 3 and (points[0] - points[-1]).length < 4.0:
            points = points[:-1]
        try:
            rotation, contour, depth = fit_contour(
                context, self._source, self._region, self._view, points, open_path=self._shape == "PATH",
            )
        except MeshError as error:
            self.report({"WARNING"}, tr(str(error)))
            return {"RUNNING_MODAL"}
        except RuntimeError as error:
            self.cleanup()
            return report_failure(self, error)
        settings = context.scene.tntmesh_settings
        settings.contour.clear()
        for point in contour:
            settings.contour.add().position = point
        settings.contour_index = 0
        settings.rotation = rotation
        settings.profile_shift = (0.0, 0.0)
        settings.offset = 0.0
        settings.contour_depth = max(0.01, depth)
        settings.axis = "FREE"
        settings.show_plane = True
        self.cleanup()
        return {"FINISHED"}

    def _draw_line(self) -> None:
        if not self._points or bpy.context.region != self._region:
            return
        points = self._points[:]
        if self._pointer is not None:
            points.append(self._pointer)
        if len(points) < 2:
            return
        import gpu
        from gpu_extras.batch import batch_for_shader

        shader = gpu.shader.from_builtin("UNIFORM_COLOR")
        shader.bind()
        shader.uniform_float("color", (0.0, 1.0, 1.0, 1.0))
        batch_for_shader(shader, "LINE_STRIP", {"pos": points}).draw(shader)

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


class TNTMESH_OT_remove_cut_point(bpy.types.Operator):
    bl_idname = "tntmesh.remove_cut_point"
    bl_label = "Remove Point"
    bl_options = {"UNDO"}

    point_index: IntProperty(default=-1, min=-1)

    @staticmethod
    def settings(context: bpy.types.Context) -> TNTMESH_PG_settings | None:
        scene = context.scene
        if scene.tntmesh_settings.mode == "DRAFT":
            plan = draft.active_plan(scene)
            cut = draft.active_cut(plan) if plan is not None else None
            return cut.settings if cut is not None else None
        return scene.tntmesh_settings

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        settings = cls.settings(context)
        return (context.mode == "OBJECT" and settings is not None
                and settings.cut_kind in {"POLYGON", "PATH"} and bool(settings.contour))

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = self.settings(context)
        index = settings.contour_index if self.point_index < 0 else self.point_index
        if index >= len(settings.contour):
            return {"CANCELLED"}
        settings.contour.remove(index)
        settings.contour_index = min(index, max(0, len(settings.contour) - 1))
        return {"FINISHED"}


def cancel_sessions() -> None:
    for session in _sessions[:]:
        session.cleanup()
