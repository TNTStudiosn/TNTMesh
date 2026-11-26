# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from contextlib import contextmanager
from math import cos, sin

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty
from mathutils import Matrix

from . import draft
from .geometry.boolean import ExactBoolean
from .geometry.connector import Connector
from .geometry.connector_auto import suggest
from .geometry.connector_clipboard import decode, encode
from .geometry.connector_pattern import contour_points, pattern_points
from .geometry.dovetail import Dovetail
from .geometry.magnet import Magnet
from .geometry.mesh import evaluated_mm
from .geometry.planar import (
    PlaneSplit,
    axis_frame,
    dovetail_positions,
    split_plane,
    validate_positions,
)
from .geometry.polygon import Point2
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .operators import active_mesh, report_failure
from .settings import TNTMESH_PG_settings

MAX_EDITABLE_POINTS = 64


def linear_settings(context: bpy.types.Context) -> TNTMESH_PG_settings | None:
    settings = context.scene.tntmesh_settings
    if settings.mode == "DRAFT":
        plan = draft.active_plan(context.scene)
        cut = draft.active_cut(plan) if plan is not None else None
        if cut is None:
            return None
        settings = cut.settings
    return settings if settings.cut_kind == "PLANAR" and settings.connector != "CUSTOM" else None


def plane_available(context: bpy.types.Context, settings: TNTMESH_PG_settings | None) -> bool:
    if context.mode != "OBJECT" or settings is None:
        return False
    if context.scene.tntmesh_settings.mode == "DRAFT":
        plan = draft.active_plan(context.scene)
        return plan is not None and plan.source is not None
    return active_mesh(context) is not None


def connector_design(settings: TNTMESH_PG_settings, count: int) -> Connector | Dovetail | Magnet:
    if settings.connector == "MAGNET":
        return settings.magnet_config(count)
    if settings.connector == "DOVETAIL":
        return settings.dovetail_config(count)
    return settings.standard_connector(settings.connector, count)


@contextmanager
def preview_split(
    context: bpy.types.Context, settings: TNTMESH_PG_settings,
) -> Iterator[tuple[ExactBoolean, PlaneSplit, Matrix]]:
    scene = context.scene
    unit = millimeters_per_unit(scene)
    try:
        with GeometryTransaction() as transaction:
            if scene.tntmesh_settings.mode == "DRAFT":
                plan = draft.active_plan(scene)
                mesh = draft.target_mesh(context, transaction, plan, plan.cut_index, unit)
            else:
                mesh, _ = evaluated_mm(context, active_mesh(context), transaction, unit)
            frame = axis_frame(settings.axis, tuple(settings.rotation))
            plane = split_plane(context, transaction, mesh, frame, settings.kerf, offset=settings.offset)
            yield ExactBoolean(context, transaction), plane, frame
    finally:
        context.view_layer.update()


def set_positions(settings: TNTMESH_PG_settings, positions: tuple[Point2, ...]) -> None:
    if positions:
        settings.connector_count = len(positions)
    settings.connector_points.clear()
    for position in positions:
        settings.connector_points.add().position = position
    settings.connector_point_index = 0
    settings.show_plane = True


def set_valid_positions(
    context: bpy.types.Context, settings: TNTMESH_PG_settings, positions: tuple[Point2, ...],
) -> None:
    if len(positions) > MAX_EDITABLE_POINTS:
        raise MeshError("Use at most 64 explicit connector positions.")
    design = connector_design(settings, len(positions))
    check_positions(context, settings, design, positions, settings.pin_positive)
    set_positions(settings, positions)


def check_positions(
    context: bpy.types.Context, settings: TNTMESH_PG_settings, design: Connector | Dovetail | Magnet,
    positions: tuple[Point2, ...], positive: bool,
) -> None:
    with preview_split(context, settings) as (engine, cut, frame):
        flip = positive and (isinstance(design, Dovetail) or (isinstance(design, Connector) and not design.loose))
        validate_positions(engine, cut, frame, settings.kerf, design, positions, flip)


class TNTMESH_OT_suggest_connectors(bpy.types.Operator):
    bl_idname = "tntmesh.suggest_connectors"
    bl_label = "Suggest Connectors"
    bl_description = "Find connector dimensions and positions using the current cut and tolerances"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        settings = linear_settings(context)
        return plane_available(context, settings) and settings.connector != "MAGNET"

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = linear_settings(context)
        wm = context.window_manager
        wm.progress_begin(0, 2)
        try:
            with preview_split(context, settings) as (engine, plane, frame):
                wm.progress_update(1)
                if settings.connector == "DOVETAIL":
                    design = settings.dovetail_config(settings.connector_count)
                    positive = settings.pin_positive
                    positions = dovetail_positions(engine, plane, frame, settings.kerf, design, (), positive)
                else:
                    baseline = settings.standard_connector("ROUND", 1)
                    baseline.validate()
                    result = suggest(engine, plane, frame, settings.kerf, baseline)
                    design, positions, positive = result.connector, result.positions, result.pin_positive
            apply_setup(settings, design, positions, positive)
            wm.progress_update(2)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
        self.report({"INFO"}, tr("Suggested {count} connector(s). Review the cut settings.").format(
            count=design.count,
        ))
        return {"FINISHED"}


class TNTMESH_OT_connector_point(bpy.types.Operator):
    bl_idname = "tntmesh.connector_point"
    bl_label = "Edit Connector Position"
    bl_options = {"UNDO", "INTERNAL"}

    action: EnumProperty(items=[
        ("ADD", "Add Connector Position", ""),
        ("REMOVE", "Remove Connector Position", ""),
        ("CLEAR", "Use Automatic Positions", ""),
    ])

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        settings = linear_settings(context)
        return context.mode == "OBJECT" and settings is not None and settings.connector != "NONE"

    @classmethod
    def description(cls, context: bpy.types.Context, properties: bpy.types.OperatorProperties) -> str:
        return tr(cls.bl_rna.properties["action"].enum_items[properties.action].name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = linear_settings(context)
        points = settings.connector_points
        if self.action == "ADD":
            if len(points) >= MAX_EDITABLE_POINTS:
                return report_failure(self, MeshError("Use at most 64 explicit connector positions."))
            selected = min(settings.connector_point_index, len(points) - 1)
            x, y = points[selected].position if points else (0, 0)
            if points:
                design = connector_design(settings, 1)
                if isinstance(design, Dovetail):
                    gap = 2 * design.envelope + 1
                    x, y = x + cos(design.angle) * gap, y + sin(design.angle) * gap
                else:
                    x += 2 * design.envelope + 1
            points.add().position = (x, y)
            settings.connector_point_index = len(points) - 1
        elif self.action == "REMOVE":
            index = settings.connector_point_index
            if index >= len(points):
                return {"CANCELLED"}
            points.remove(index)
            settings.connector_point_index = max(0, min(index, len(points) - 1))
        else:
            points.clear()
            settings.connector_point_index = 0
        return {"FINISHED"}


class TNTMESH_UL_connector_points(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "position", text="", emboss=False)


def apply_setup(
    settings: TNTMESH_PG_settings, design: Connector | Dovetail, positions: tuple[Point2, ...], positive: bool,
) -> None:
    if isinstance(design, Dovetail):
        settings.connector = "DOVETAIL"
        for name in ("neck", "head", "height", "length", "angle"):
            setattr(settings, f"dovetail_{name}", getattr(design, name))
        settings.loose_pins = False
    else:
        settings.connector = design.shape
        settings.diameter, settings.insertion, settings.loose_pins = design.diameter, design.insertion, design.loose
    for name in ("wall", "lateral", "axial"):
        setattr(settings, name, getattr(design, name))
    settings.connector_count = design.count
    settings.pin_positive = positive
    set_positions(settings, positions)


class TNTMESH_OT_connector_transfer(bpy.types.Operator):
    bl_idname = "tntmesh.connector_transfer"
    bl_label = "Transfer Connector Setup"
    bl_options = {"UNDO", "INTERNAL"}

    action: EnumProperty(items=[
        ("COPY", "Copy Connector Setup", ""),
        ("PASTE", "Paste Connector Setup", ""),
        ("MIRROR_X", "Mirror Positions on X", ""),
        ("MIRROR_Y", "Mirror Positions on Y", ""),
    ])

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return plane_available(context, linear_settings(context))

    @classmethod
    def description(cls, context: bpy.types.Context, properties: bpy.types.OperatorProperties) -> str:
        return tr(cls.bl_rna.properties["action"].enum_items[properties.action].name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = linear_settings(context)
        current = tuple(tuple(point.position) for point in settings.connector_points)
        if self.action == "COPY":
            if settings.connector not in {"ROUND", "HEX", "DOVETAIL"}:
                return {"CANCELLED"}
            design = connector_design(settings, len(current) or settings.connector_count)
            context.window_manager.clipboard = encode(design, current, settings.pin_positive)
            self.report({"INFO"}, tr("Copied connector setup."))
            return {"FINISHED"}
        try:
            if self.action == "PASTE":
                if settings.connector == "MAGNET":
                    return {"CANCELLED"}
                design, positions, positive = decode(context.window_manager.clipboard)
                check_positions(context, settings, design, positions, positive)
                apply_setup(settings, design, positions, positive)
                self.report({"INFO"}, tr("Applied connector setup."))
            else:
                if not current:
                    return {"CANCELLED"}
                mirror = (-1, 1) if self.action == "MIRROR_X" else (1, -1)
                positions = tuple(dict.fromkeys((*current, *((x * mirror[0], y * mirror[1]) for x, y in current))))
                set_valid_positions(context, settings, positions)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        return {"FINISHED"}


class TNTMESH_OT_connector_pattern(bpy.types.Operator):
    bl_idname = "tntmesh.connector_pattern"
    bl_label = "Connector Pattern"
    bl_description = "Fit regularly spaced connectors on the current cut"
    bl_options = {"UNDO"}

    pattern: EnumProperty(name="Pattern", items=[
        ("LINE", "Line", "Lay out evenly spaced positions in a line"),
        ("CIRCLE", "Circle", "Lay out evenly spaced positions on a circle"),
        ("GRID", "Grid", "Lay out evenly spaced positions in rows"),
        ("CONTOUR", "Contour", "Lay out positions around the outer cut contour"),
    ])
    count: IntProperty(name="Connector count", default=3, min=1, max=32)
    spacing: FloatProperty(name="Spacing (mm)", default=8, min=.01, precision=2)
    setback: FloatProperty(name="Edge setback (mm)", default=5, min=.01, precision=2)
    angle: FloatProperty(name="Pattern rotation", subtype="ANGLE", unit="ROTATION")

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        settings = linear_settings(context)
        return plane_available(context, settings) and settings.connector != "NONE"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        settings = linear_settings(context)
        self.count = max(3, len(settings.connector_points) or settings.connector_count)
        self.spacing = 2 * connector_design(settings, 1).envelope * 1.25
        self.setback = self.spacing / 2
        return context.window_manager.invoke_props_dialog(self, width=320)

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.use_property_split = True
        for name in ("pattern", "count", "setback" if self.pattern == "CONTOUR" else "spacing", "angle"):
            self.layout.prop(self, name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = linear_settings(context)
        old = settings.connector_points
        center = (sum(point.position[0] for point in old) / len(old),
                  sum(point.position[1] for point in old) / len(old)) if old else (0, 0)
        try:
            if self.pattern == "CONTOUR":
                design = connector_design(settings, self.count)
                with preview_split(context, settings) as (engine, cut, frame):
                    positions = contour_points(cut, frame, settings.kerf, self.count, self.setback, self.angle)
                    validate_positions(
                        engine, cut, frame, settings.kerf, design, positions,
                        settings.pin_positive and (isinstance(design, Dovetail)
                                                   or (isinstance(design, Connector) and not design.loose)),
                    )
                set_positions(settings, positions)
            else:
                positions = pattern_points(self.pattern, self.count, self.spacing, self.angle, center)
                set_valid_positions(context, settings, positions)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        self.report({"INFO"}, tr("Placed {count} connector(s).").format(count=self.count))
        return {"FINISHED"}


def positions(layout: bpy.types.UILayout, settings: TNTMESH_PG_settings) -> None:
    points = settings.connector_points
    if settings.connector == "DOVETAIL" or (settings.connector != "MAGNET" and not settings.loose_pins):
        layout.prop(settings, "pin_positive")
    layout.operator("tntmesh.connector_pattern", icon="MOD_ARRAY")
    if not points:
        layout.operator("tntmesh.connector_point", text="Set Positions", icon="ADD").action = "ADD"
        return
    layout.label(text="Connector Positions (mm)")
    row = layout.row()
    row.template_list("TNTMESH_UL_connector_points", "", settings, "connector_points", settings,
                      "connector_point_index", rows=2)
    buttons = row.column(align=True)
    buttons.operator("tntmesh.connector_point", text="", icon="ADD").action = "ADD"
    buttons.operator("tntmesh.connector_point", text="", icon="REMOVE").action = "REMOVE"
    mirror = layout.row(align=True)
    mirror.operator("tntmesh.connector_transfer", text="Mirror X").action = "MIRROR_X"
    mirror.operator("tntmesh.connector_transfer", text="Mirror Y").action = "MIRROR_Y"
    layout.operator("tntmesh.connector_point", text="Use Automatic Positions", icon="LOOP_BACK").action = "CLEAR"


CLASSES = (TNTMESH_OT_suggest_connectors, TNTMESH_OT_connector_point, TNTMESH_OT_connector_pattern,
           TNTMESH_OT_connector_transfer, TNTMESH_UL_connector_points)
