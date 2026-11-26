# SPDX-License-Identifier: GPL-3.0-or-later
from uuid import uuid4

import bpy
from bpy.props import EnumProperty, StringProperty

from . import draft
from .localization import tr
from .model import DRAFT_ID, MeshError
from .operators import MeshOperator, active_mesh, report_failure, select_results
from .settings import TNTMESH_PG_settings

GEOMETRY_PROPERTIES = ("axis", "rotation", "offset", "kerf", "connector", "diameter", "insertion",
                       "lateral", "axial", "wall", "connector_count", "loose_pins", "pin_positive",
                       "pin_template", "socket_template",
                       "cut_kind", "cutter", "profile_size",
                       "profile_shift", "curve_controls", "curve_samples", "contour_depth", "path_smoothing",
                       "region_method", "region_depth", "region_slot", "region_attribute",
                       "region_color", "region_tolerance", "region_weight", "region_grow",
                       "region_smoothing", "region_connector",
                       "symmetry_axis", "symmetry_center", "symmetry_secondary", "symmetry_rotation",
                       "base_band", "base_area", "base_margin", "base_adjustment",
                       "base_pins", "base_shape", "base_contact_source")


def copy_settings(source: TNTMESH_PG_settings, destination: TNTMESH_PG_settings) -> None:
    for name in GEOMETRY_PROPERTIES:
        setattr(destination, name, getattr(source, name))
    destination.contour.clear()
    for point in source.contour:
        destination.contour.add().position = point.position
    destination.connector_points.clear()
    for point in source.connector_points:
        destination.connector_points.add().position = point.position
    destination.connector_point_index = 0
    destination.base_contacts.clear()
    for item in source.base_contacts:
        contact = destination.base_contacts.add()
        for name in ("center", "height", "shift", "connector", "diameter"):
            setattr(contact, name, getattr(item, name))


class TNTMESH_OT_draft_create(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.draft_create"
    bl_label = "New Draft"
    bl_description = "Create a non-destructive plan for the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        if source.get(DRAFT_ID):
            return report_failure(self, MeshError("Select the original model for a new draft."))
        scene = context.scene
        plan = scene.tntmesh_drafts.add()
        plan.name = source.name
        plan.uid = uuid4().hex
        plan.source = source
        scene.tntmesh_draft_index = len(scene.tntmesh_drafts) - 1
        return {"FINISHED"}


class TNTMESH_OT_draft_action(bpy.types.Operator):
    bl_idname = "tntmesh.draft_action"
    bl_label = "Edit Draft Cut"
    bl_options = {"UNDO", "INTERNAL"}

    action: EnumProperty(items=[
        ("ADD", "Add Cut", ""),
        ("DUPLICATE", "Duplicate Cut", ""),
        ("REMOVE", "Remove Cut", ""),
        ("UP", "Move Cut Up", ""),
        ("DOWN", "Move Cut Down", ""),
    ])

    @classmethod
    def description(cls, context, properties) -> str:
        return tr(cls.bl_rna.properties["action"].enum_items[properties.action].name)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and draft.active_plan(context.scene) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        plan = draft.active_plan(context.scene)
        selected = draft.active_cut(plan)
        count = len(plan.cuts)
        if self.action == "ADD":
            targets = draft.free_targets(plan, count)
            cut = plan.cuts.add()
            cut.name = tr("Cut {number}").format(number=count + 1)
            cut.uid = uuid4().hex
            cut.target = targets[0] if targets else draft.SOURCE
            copy_settings(context.scene.tntmesh_settings, cut.settings)
            plan.cut_index = count
        elif selected is None:
            return {"CANCELLED"}
        elif self.action == "DUPLICATE":
            cut = plan.cuts.add()
            cut.name = tr("{name} · Copy").format(name=selected.name)
            cut.uid = uuid4().hex
            cut.target = selected.target
            cut.enabled = False
            copy_settings(selected.settings, cut.settings)
            plan.cut_index = count
        elif self.action == "REMOVE":
            plan.cuts.remove(plan.cut_index)
            plan.cut_index = min(plan.cut_index, max(0, count - 2))
        else:
            destination = plan.cut_index + (-1 if self.action == "UP" else 1)
            if not 0 <= destination < count:
                return {"CANCELLED"}
            plan.cuts.move(plan.cut_index, destination)
            plan.cut_index = destination
        return {"FINISHED"}


class TNTMESH_OT_draft_target(bpy.types.Operator):
    bl_idname = "tntmesh.draft_target"
    bl_label = "Choose Input Piece"
    bl_options = {"UNDO", "INTERNAL"}

    target: StringProperty()

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        plan = draft.active_plan(context.scene)
        return context.mode == "OBJECT" and plan is not None and draft.active_cut(plan) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        plan = draft.active_plan(context.scene)
        if self.target not in draft.free_targets(plan, plan.cut_index):
            return report_failure(self, MeshError("Choose an available input piece from an earlier cut."))
        draft.active_cut(plan).target = self.target
        return {"FINISHED"}


class TNTMESH_OT_draft_build(bpy.types.Operator):
    bl_idname = "tntmesh.draft_build"
    bl_label = "Build Draft"
    bl_description = "Apply enabled cuts and replace this draft's previously generated pieces"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        plan = draft.active_plan(context.scene)
        return context.mode == "OBJECT" and plan is not None and any(cut.enabled for cut in plan.cuts)

    def execute(self, context: bpy.types.Context) -> set[str]:
        plan = draft.active_plan(context.scene)
        try:
            results = draft.rebuild(context, plan)
            select_results(context, results)
            if context.scene.tntmesh_settings.hide_source:
                plan.source.hide_set(True)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        self.report({"INFO"}, tr("Built {count} draft pieces.").format(count=len(results)))
        return {"FINISHED"}


CLASSES = (TNTMESH_OT_draft_create, TNTMESH_OT_draft_action,
           TNTMESH_OT_draft_target, TNTMESH_OT_draft_build)
