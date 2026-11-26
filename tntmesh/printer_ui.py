# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import replace
from pathlib import Path

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix

from .localization import tr
from .model import MeshError, millimeters_per_unit
from .operators import active_mesh, report_failure
from .printer_props import TNTMESH_PG_printer, selected_printer
from .printing import PRESETS, PrinterProfile, fit, from_json, to_json
from .viewport import project_bounds


def add_profile(scene: bpy.types.Scene, profile: PrinterProfile) -> None:
    profile.validate()
    scene.tntmesh_printers.add().set_data(profile)
    scene.tntmesh_printer_index = len(scene.tntmesh_printers) - 1


class TNTMESH_OT_printer_add(bpy.types.Operator):
    bl_idname = "tntmesh.printer_add"
    bl_label = "Add Printer"
    bl_description = "Add an editable profile from a factory preset or start from scratch"
    bl_options = {"UNDO"}

    preset: EnumProperty(items=[
        ("CUSTOM", "Custom Printer", ""),
        *((key, profile.name, "") for key, profile in PRESETS.items()),
    ])

    def execute(self, context: bpy.types.Context) -> set[str]:
        custom = PrinterProfile("", tr("Custom Printer"), "FDM", (220, 220, 250))
        add_profile(context.scene, PRESETS.get(self.preset, custom))
        return {"FINISHED"}


class PrinterOperator:
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return selected_printer(context.scene) is not None


class TNTMESH_OT_printer_edit(bpy.types.Operator, PrinterOperator):
    bl_idname = "tntmesh.printer_edit"
    bl_label = "Manage Printer"
    bl_options = {"UNDO", "INTERNAL"}

    action: EnumProperty(items=[
        ("DUPLICATE", "Duplicate Printer", ""),
        ("REMOVE", "Remove Printer", ""),
        ("USE_TOLERANCE", "Use Profile Tolerances", ""),
    ])

    @classmethod
    def description(cls, context, properties) -> str:
        return tr(cls.bl_rna.properties["action"].enum_items[properties.action].name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        try:
            if self.action == "REMOVE":
                scene.tntmesh_printers.remove(scene.tntmesh_printer_index)
                scene.tntmesh_printer_index = max(
                    0, min(scene.tntmesh_printer_index, len(scene.tntmesh_printers) - 1)
                )
            else:
                profile = selected_printer(scene).data()
                profile.validate()
                if self.action == "DUPLICATE":
                    name = tr("{name} · Copy").format(name=profile.model[:115])
                    add_profile(scene, replace(profile, model=name))
                else:
                    settings = scene.tntmesh_settings
                    settings.lateral = profile.lateral_mm
                    settings.axial = profile.axial_mm
                    settings.wall = profile.min_wall_mm
        except (MeshError, ValueError) as error:
            return report_failure(self, error)
        return {"FINISHED"}


class TNTMESH_OT_printer_import(bpy.types.Operator, ImportHelper):
    bl_idname = "tntmesh.printer_import"
    bl_label = "Import Printer Profile"
    bl_options = {"UNDO"}
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            add_profile(context.scene, from_json(Path(self.filepath)))
        except (MeshError, OSError, ValueError) as error:
            return report_failure(self, error)
        return {"FINISHED"}


class TNTMESH_OT_printer_export(bpy.types.Operator, PrinterOperator, ExportHelper):
    bl_idname = "tntmesh.printer_export"
    bl_label = "Export Printer Profile"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})
    check_existing: bpy.props.BoolProperty(default=False, options={"HIDDEN"})

    def execute(self, context: bpy.types.Context) -> set[str]:
        payload = selected_printer(context.scene).data()
        path = Path(self.filepath)
        created = False
        try:
            document = to_json(payload)
            with path.open("x", encoding="utf-8") as stream:
                created = True
                stream.write(document)
        except FileExistsError:
            return report_failure(self, MeshError("Choose a new file name for the printer profile."))
        except (MeshError, OSError, ValueError) as error:
            if created:
                path.unlink(missing_ok=True)
            return report_failure(self, error)
        return {"FINISHED"}


class TNTMESH_UL_printers(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        name = f"{item.manufacturer} {item.model}".strip() or tr("Custom Printer")
        layout.label(text=name, translate=False, icon="FILE_3D")


def draw_fit(
    layout: bpy.types.UILayout, context: bpy.types.Context, profile: TNTMESH_PG_printer,
) -> None:
    obj = active_mesh(context)
    if obj is None:
        return
    extents = project_bounds(obj, context.evaluated_depsgraph_get(), Matrix.Identity(3))
    if extents is None:
        return
    lower, upper = extents
    size = tuple((upper - lower) * millimeters_per_unit(context.scene))
    try:
        result = fit(size, profile.data())
    except MeshError as error:
        layout.label(text=tr(str(error)), translate=False, icon="ERROR")
        return
    label = layout.box()
    label.label(text=" × ".join(f"{value:.1f}" for value in size) + " mm", translate=False)
    if result.exceeded:
        label.label(text=tr("Exceeds {axes}").format(axes=", ".join(result.exceeded)),
                    translate=False, icon="ERROR")
        if result.alternative:
            label.label(text=tr("Try axis order {axes}").format(axes=result.alternative),
                        translate=False, icon="DRIVER_ROTATIONAL_DIFFERENCE")
        layout.operator("tntmesh.fit_grid", icon="MOD_BOOLEAN")
    else:
        label.label(text="Fits within the print volume", icon="CHECKMARK")
    layout.prop(context.scene.tntmesh_settings, "show_build_volume")


class TNTMESH_PT_print(bpy.types.Panel):
    bl_label = "Printer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        scene = context.scene
        layout = self.layout
        layout.operator_menu_enum("tntmesh.printer_add", "preset", icon="ADD")
        row = layout.row(align=True)
        row.operator("tntmesh.printer_import", text="Import", icon="IMPORT")
        row.operator("tntmesh.printer_export", text="Export", icon="EXPORT")
        profile = selected_printer(scene)
        if profile is None:
            return
        if len(scene.tntmesh_printers) > 1:
            layout.template_list(
                "TNTMESH_UL_printers", "", scene, "tntmesh_printers",
                scene, "tntmesh_printer_index", rows=3,
            )
        layout.label(text=profile.data().name, translate=False, icon="FILE_3D")
        draw_fit(layout, context, profile)
        header, body = layout.panel("tntmesh_printer_edit", default_closed=True)
        header.label(text="Profile settings")
        if body:
            for field in ("manufacturer", "model", "technology", "build_mm", "margin_mm", "material",
                          "lateral_mm", "axial_mm", "min_wall_mm", "compensation_pct",
                          "density_g_cm3", "price_per_kg"):
                body.prop(profile, field)
            body.operator("tntmesh.printer_edit", text="Use Profile Tolerances").action = (
                "USE_TOLERANCE"
            )
            row = body.row(align=True)
            row.operator("tntmesh.printer_edit", text="", icon="DUPLICATE").action = "DUPLICATE"
            row.operator("tntmesh.printer_edit", text="", icon="X").action = "REMOVE"


CLASSES = (TNTMESH_OT_printer_add, TNTMESH_OT_printer_edit, TNTMESH_OT_printer_import,
           TNTMESH_OT_printer_export, TNTMESH_UL_printers, TNTMESH_PT_print)
