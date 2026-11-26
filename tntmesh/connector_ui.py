# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import EnumProperty

from . import draft
from .geometry.boolean import ExactBoolean
from .geometry.connector_auto import suggest
from .geometry.mesh import evaluated_mm
from .geometry.planar import axis_frame, split_plane
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .operators import active_mesh, report_failure
from .settings import TNTMESH_PG_settings


def linear_settings(context: bpy.types.Context) -> TNTMESH_PG_settings | None:
    settings = context.scene.tntmesh_settings
    if settings.mode == "DRAFT":
        plan = draft.active_plan(context.scene)
        cut = draft.active_cut(plan) if plan is not None else None
        if cut is None:
            return None
        settings = cut.settings
    return settings if settings.cut_kind == "PLANAR" and settings.connector != "CUSTOM" else None


class TNTMESH_OT_suggest_connectors(bpy.types.Operator):
    bl_idname = "tntmesh.suggest_connectors"
    bl_label = "Suggest Connectors"
    bl_description = "Find connector dimensions and positions using the current cut and tolerances"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != "OBJECT" or linear_settings(context) is None:
            return False
        if context.scene.tntmesh_settings.mode == "DRAFT":
            plan = draft.active_plan(context.scene)
            return plan is not None and plan.source is not None
        return active_mesh(context) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        settings = linear_settings(context)
        is_draft = scene.tntmesh_settings.mode == "DRAFT"
        wm = context.window_manager
        wm.progress_begin(0, 2)
        try:
            unit = millimeters_per_unit(scene)
            with GeometryTransaction() as transaction:
                if is_draft:
                    plan = draft.active_plan(scene)
                    mesh = draft.target_mesh(context, transaction, plan, plan.cut_index, unit)
                else:
                    mesh, _ = evaluated_mm(context, active_mesh(context), transaction, unit)
                frame = axis_frame(settings.axis, tuple(settings.rotation))
                plane = split_plane(context, transaction, mesh, frame, settings.kerf, offset=settings.offset)
                wm.progress_update(1)
                baseline = settings.standard_connector("ROUND", 1)
                baseline.validate()
                result = suggest(ExactBoolean(context, transaction), plane, frame, settings.kerf, baseline)
            settings.connector = result.connector.shape
            settings.diameter = result.connector.diameter
            settings.insertion = result.connector.insertion
            settings.pin_positive = result.pin_positive
            settings.connector_count = result.connector.count
            settings.connector_points.clear()
            for position in result.positions:
                settings.connector_points.add().position = position
            settings.connector_point_index = 0
            settings.show_plane = True
            wm.progress_update(2)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report({"INFO"}, tr("Suggested {count} connector(s). Review the cut settings.").format(
            count=result.connector.count,
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
            selected = min(settings.connector_point_index, len(points) - 1)
            x, y = points[selected].position if points else (0, 0)
            if points:
                x += settings.diameter + 2 * (settings.wall + settings.lateral) + 1
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


def positions(layout: bpy.types.UILayout, settings: TNTMESH_PG_settings) -> None:
    points = settings.connector_points
    if not settings.loose_pins:
        layout.prop(settings, "pin_positive")
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
    layout.operator("tntmesh.connector_point", text="Use Automatic Positions", icon="LOOP_BACK").action = "CLEAR"


CLASSES = (TNTMESH_OT_suggest_connectors, TNTMESH_OT_connector_point, TNTMESH_UL_connector_points)
