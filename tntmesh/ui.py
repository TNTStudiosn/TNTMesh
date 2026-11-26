# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import draft
from .base_ui import draw_contacts
from .connector_ui import positions
from .diagnostics_ui import controls as diagnostics_controls
from .localization import tr
from .operators import active_mesh, managed_parts
from .settings import TNTMESH_PG_settings


def cut_properties(
    layout: bpy.types.UILayout, settings: TNTMESH_PG_settings, source: bpy.types.Object | None,
) -> None:
    layout.label(text="Cut type")
    layout.prop(settings, "cut_kind", text="")
    if settings.cut_kind == "OBJECT":
        layout.prop(settings, "cutter")
        return
    if settings.cut_kind == "BASE":
        layout.prop(settings, "base_band")
        layout.prop(settings, "base_pins")
        if settings.base_pins:
            layout.prop(settings, "base_shape")
        return
    if settings.cut_kind == "REGION":
        layout.prop(settings, "region_method", text="")
        method = settings.region_method
        if method == "MATERIAL":
            layout.prop(settings, "region_slot")
            if source is not None and settings.region_slot <= len(source.material_slots):
                name = source.material_slots[settings.region_slot - 1].name
                layout.label(text=name or tr("Empty material slot"),
                             translate=False, icon="MATERIAL")
        elif method == "SELECTION":
            layout.label(text="Uses saved face selection.", icon="FACESEL")
        else:
            if source is None or source.type != "MESH":
                layout.prop(settings, "region_attribute")
            elif method == "VERTEX_GROUP":
                layout.prop_search(settings, "region_attribute", source, "vertex_groups")
            elif method == "COLOR":
                layout.prop_search(settings, "region_attribute", source.data, "color_attributes")
            else:
                layout.prop_search(settings, "region_attribute", source.data, "attributes")
        if method == "COLOR":
            layout.prop(settings, "region_color")
        layout.prop(settings, "region_depth")
        layout.label(text="Connector")
        layout.prop(settings, "region_connector", text="")
        return
    layout.row(align=True).prop(settings, "axis", expand=True)
    if settings.axis == "FREE":
        layout.column(align=True).prop(settings, "rotation")
    layout.prop(settings, "offset")
    if settings.cut_kind in {"PLANAR", "SYMMETRY"}:
        if settings.cut_kind == "SYMMETRY":
            layout.label(text="Symmetry axis")
            layout.row(align=True).prop(settings, "symmetry_axis", expand=True)
            layout.prop(settings, "symmetry_center")
        layout.label(text="Connector")
        layout.prop(settings, "connector", text="")
        if settings.cut_kind == "PLANAR" and settings.connector != "CUSTOM":
            layout.operator("tntmesh.suggest_connectors", icon="CONSTRAINT")
        if settings.connector == "CUSTOM":
            layout.prop(settings, "pin_template")
            layout.prop(settings, "socket_template")
    elif settings.cut_kind == "BEZIER":
        layout.prop(settings, "curve_controls")
    elif settings.cut_kind in {"POLYGON", "PATH"}:
        layout.prop(settings, "contour_depth")
    else:
        layout.prop(settings, "profile_size")


def cut_details(
    layout: bpy.types.UILayout, settings: TNTMESH_PG_settings, source: bpy.types.Object | None,
) -> None:
    if settings.cut_kind == "BASE":
        for prop in ("base_area", "base_margin", "base_adjustment"):
            layout.prop(settings, prop)
        if settings.base_pins:
            for prop in ("diameter", "insertion", "lateral", "axial", "wall", "loose_pins"):
                layout.prop(settings, prop)
        if settings.base_contact_source == source:
            draw_contacts(layout, settings)
        return
    if settings.cut_kind == "REGION":
        layout.prop(settings, "region_grow")
        layout.prop(settings, "region_smoothing")
        if settings.region_method == "COLOR":
            layout.prop(settings, "region_tolerance")
        elif settings.region_method == "VERTEX_GROUP":
            layout.prop(settings, "region_weight")
        if settings.region_connector != "NONE":
            connector_details(layout, settings)
        return
    if settings.cut_kind == "BEZIER":
        layout.prop(settings, "curve_samples")
        return
    if settings.cut_kind in {"RECTANGLE", "ELLIPSE", "POLYGON", "PATH"}:
        layout.prop(settings, "profile_shift")
        if settings.cut_kind == "PATH":
            layout.prop(settings, "path_smoothing")
        if settings.cut_kind in {"POLYGON", "PATH"} and settings.contour:
            layout.template_list(
                "TNTMESH_UL_contour", "", settings, "contour", settings, "contour_index", rows=3,
            )
        return
    if settings.cut_kind not in {"PLANAR", "SYMMETRY"}:
        return
    if settings.cut_kind == "SYMMETRY":
        layout.prop(settings, "symmetry_secondary")
        layout.column(align=True).prop(settings, "symmetry_rotation")
    layout.prop(settings, "kerf")
    if settings.connector == "CUSTOM":
        layout.prop(settings, "wall")
    elif settings.connector != "NONE":
        connector_details(layout, settings)
        if settings.cut_kind == "PLANAR":
            positions(layout, settings)


def connector_details(layout: bpy.types.UILayout, settings: TNTMESH_PG_settings) -> None:
    if settings.cut_kind != "PLANAR" or not settings.connector_points:
        layout.prop(settings, "connector_count")
    for prop in ("loose_pins", "diameter", "insertion", "lateral", "axial", "wall"):
        layout.prop(settings, prop)


class TNTMESH_UL_draft_plans(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "name", text="", emboss=False, icon="FILE_BLEND")


class TNTMESH_UL_contour(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0):
        row = layout.row(align=True)
        row.prop(item, "position", text="")
        row.operator("tntmesh.remove_cut_point", text="", icon="X").point_index = index


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
        cut_properties(layout.box(), operation.settings, plan.source)
        if operation.settings.cut_kind != "OBJECT":
            header, body = layout.panel("tntmesh_draft_cut_settings", default_closed=True)
            header.label(text="Cut settings")
            if body:
                cut_details(body, operation.settings, plan.source)
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
                body.prop(settings, "repair_orientation")
                body.operator("tntmesh.repair")

            layout.separator()
            cut = layout.box()
            cut.label(text="Split", icon="MOD_BOOLEAN")
            cut_properties(cut, settings, obj)
            if settings.cut_kind == "BASE":
                cut.operator("tntmesh.find_base_contacts", icon="VIEWZOOM")
            if settings.cut_kind in {"PLANAR", "POLYGON", "PATH", "SYMMETRY"}:
                draw_label = {"POLYGON": "Draw Contour", "PATH": "Draw Path"}.get(
                    settings.cut_kind, "Draw Cut Line",
                )
                cut.prop(settings, "draw_snap")
                cut.operator("tntmesh.draw_plane", icon="IPO_LINEAR", text=draw_label)
                if settings.cut_kind in {"PLANAR", "SYMMETRY"}:
                    cut.operator("tntmesh.draw_plane", icon="FACESEL", text="Align to Face").align_face = True
            if settings.cut_kind != "OBJECT":
                preview_label = {
                    "PLANAR": "Show plane", "REGION": "Highlight region", "SYMMETRY": "Show both planes",
                    "BASE": "Highlight contacts",
                }.get(settings.cut_kind, "Show cutter")
                cut.prop(settings, "show_plane", text=preview_label)

            header, body = layout.panel("tntmesh_cut_settings", default_closed=True)
            header.label(text="Cut settings")
            if body:
                body.prop(settings, "hide_source")
                if settings.cut_kind in {"PLANAR", "SYMMETRY"}:
                    body.prop(settings, "show_cut_handle")
                cut_details(body, settings, obj)

            action = layout.row()
            action.scale_y = 1.45
            label = {"REGION": "Extract Region", "BASE": "Separate Base"}.get(settings.cut_kind, "Split Model")
            action.operator("tntmesh.split", icon="CHECKMARK", text=label)
            if settings.cut_kind == "REGION" and settings.region_method == "MATERIAL":
                layout.operator("tntmesh.split_materials", icon="MATERIAL")
            layout.operator("tntmesh.validate", icon="VIEWZOOM")

        if obj is not None:
            header, body = layout.panel("tntmesh_diagnostics", default_closed=True)
            header.label(text="Mesh Diagnostics", icon="INFO")
            if body:
                diagnostics_controls(body, context)

        if managed_parts(context, "ALL"):
            layout.separator()
            layout.operator("tntmesh.export_stl", icon="EXPORT")


CLASSES = (
    TNTMESH_UL_draft_plans, TNTMESH_UL_contour, TNTMESH_UL_draft_cuts,
    TNTMESH_MT_draft_targets, TNTMESH_PT_main,
)
