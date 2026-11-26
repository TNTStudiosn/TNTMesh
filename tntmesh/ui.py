# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import draft
from .operators import active_mesh, managed_parts
from .settings import TNTMESH_PG_settings


def cut_properties(layout: bpy.types.UILayout, settings: TNTMESH_PG_settings) -> None:
    layout.label(text="Cut type")
    layout.prop(settings, "cut_kind", text="")
    if settings.cut_kind == "OBJECT":
        layout.prop(settings, "cutter")
        return
    layout.row(align=True).prop(settings, "axis", expand=True)
    if settings.axis == "FREE":
        layout.column(align=True).prop(settings, "rotation")
    layout.prop(settings, "offset")
    if settings.cut_kind == "PLANAR":
        layout.label(text="Connector")
        layout.prop(settings, "connector", text="")
    elif settings.cut_kind == "BEZIER":
        layout.prop(settings, "curve_controls")
    else:
        layout.prop(settings, "profile_size")


def cut_details(layout: bpy.types.UILayout, settings: TNTMESH_PG_settings) -> None:
    if settings.cut_kind == "BEZIER":
        layout.prop(settings, "curve_samples")
        return
    if settings.cut_kind in {"RECTANGLE", "ELLIPSE"}:
        layout.prop(settings, "profile_shift")
        return
    if settings.cut_kind != "PLANAR":
        return
    layout.prop(settings, "kerf")
    if settings.connector != "NONE":
        for prop in ("connector_count", "loose_pins", "diameter", "insertion", "lateral", "axial", "wall"):
            layout.prop(settings, prop)


class TNTMESH_UL_draft_plans(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "name", text="", emboss=False, icon="FILE_BLEND")


class TNTMESH_UL_draft_cuts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.prop(item, "name", text="", emboss=False)


class TNTMESH_MT_draft_targets(bpy.types.Menu):
    bl_label = "Input Piece"

    def draw(self, context: bpy.types.Context) -> None:
        plan = draft.active_plan(context.scene)
        if plan is None:
            return
        for key in draft.free_targets(plan, plan.cut_index):
            op = self.layout.operator(
                "tntmesh.draft_target", text=draft.target_label(plan, key), translate=False,
            )
            op.target = key


def draw_draft(layout: bpy.types.UILayout, context: bpy.types.Context) -> None:
    scene = context.scene
    layout.operator("tntmesh.draft_create", icon="FILE_NEW")
    plan = draft.active_plan(scene)
    if plan is None:
        layout.label(text="Select a mesh and create a draft.", icon="INFO")
        return

    header, body = layout.panel("tntmesh_draft_plans", default_closed=True)
    header.label(text=plan.name, translate=False, icon="FILE_BLEND")
    if body:
        body.template_list(
            "TNTMESH_UL_draft_plans", "", scene, "tntmesh_drafts", scene, "tntmesh_draft_index",
            rows=2,
        )
        if plan.source is not None:
            body.label(text=plan.source.name, translate=False, icon="MESH_DATA")
    if plan.source is None:
        layout.label(text="The draft source is missing from this view layer.", icon="ERROR")

    layout.template_list("TNTMESH_UL_draft_cuts", "", plan, "cuts", plan, "cut_index", rows=3)
    layout.operator("tntmesh.draft_action", text="Add Cut", icon="ADD").action = "ADD"
    operation = draft.active_cut(plan)
    if operation is not None:
        row = layout.row(align=True)
        for kind, icon in (
            ("UP", "TRIA_UP"), ("DOWN", "TRIA_DOWN"),
            ("DUPLICATE", "DUPLICATE"), ("REMOVE", "X"),
        ):
            sub = row.row(align=True)
            sub.enabled = not (kind == "UP" and plan.cut_index == 0 or
                               kind == "DOWN" and plan.cut_index == len(plan.cuts) - 1)
            sub.operator("tntmesh.draft_action", text="", icon=icon).action = kind
        layout.label(text="Input Piece", icon="MESH_DATA")
        layout.menu(
            "TNTMESH_MT_draft_targets", text=draft.target_label(plan, operation.target),
            translate=False,
        )
        if operation.enabled and operation.target not in draft.free_targets(plan, plan.cut_index):
            layout.label(text="Choose an available input piece.", icon="ERROR")
        cut_properties(layout.box(), operation.settings)
        if operation.settings.cut_kind != "OBJECT":
            header, body = layout.panel("tntmesh_draft_cut_settings", default_closed=True)
            header.label(text="Cut settings")
            if body:
                cut_details(body, operation.settings)
    action = layout.row()
    action.scale_y = 1.45
    action.operator("tntmesh.draft_build", icon="CHECKMARK")


class TNTMESH_PT_main(bpy.types.Panel):
    bl_label = "TNTMesh"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.tntmesh_settings
        obj = active_mesh(context)
        if context.mode != "OBJECT":
            layout.label(text="Switch to Object Mode to use TNTMesh.", icon="INFO")
            return

        layout.operator("tntmesh.import_stl", icon="IMPORT")
        layout.row(align=True).prop(settings, "mode", expand=True)
        if settings.mode == "DRAFT":
            draw_draft(layout, context)
        elif obj is None:
            layout.label(text="Select a mesh or import an STL.", icon="INFO")
        else:
            layout.label(text=obj.name, icon="MESH_DATA", translate=False)
            header, body = layout.panel("tntmesh_scale", default_closed=True)
            header.label(text="Scale", icon="FULLSCREEN_ENTER")
            if body:
                body.row(align=True).prop(settings, "scale_axis", expand=True)
                body.prop(settings, "target_size")
                if context.scene.unit_settings.system == "NONE":
                    body.label(text="Without scene units, 1 BU = 1 mm.", icon="INFO")
                body.operator("tntmesh.resize")

            header, body = layout.panel("tntmesh_repair", default_closed=True)
            header.label(text="Repair", icon="TOOL_SETTINGS")
            if body:
                body.prop(settings, "repair_weld")
                body.prop(settings, "repair_holes")
                if settings.repair_holes:
                    body.prop(settings, "repair_hole_edges")
                body.operator("tntmesh.repair")

            layout.separator()
            cut = layout.box()
            cut.label(text="Split", icon="MOD_BOOLEAN")
            cut_properties(cut, settings)
            if settings.cut_kind == "PLANAR":
                cut.operator("tntmesh.draw_plane", icon="IPO_LINEAR")
            if settings.cut_kind != "OBJECT":
                cut.prop(settings, "show_plane", text=(
                    "Show plane" if settings.cut_kind == "PLANAR" else "Show cutter"
                ))

            header, body = layout.panel("tntmesh_cut_settings", default_closed=True)
            header.label(text="Cut settings")
            if body:
                body.prop(settings, "hide_source")
                cut_details(body, settings)

            action = layout.row()
            action.scale_y = 1.45
            action.operator("tntmesh.split", icon="CHECKMARK")
            layout.operator("tntmesh.validate", icon="VIEWZOOM")

        if managed_parts(context, "ALL"):
            layout.separator()
            layout.operator("tntmesh.export_stl", icon="EXPORT")


CLASSES = (TNTMESH_UL_draft_plans, TNTMESH_UL_draft_cuts, TNTMESH_MT_draft_targets, TNTMESH_PT_main)
