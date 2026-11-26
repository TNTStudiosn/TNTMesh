# SPDX-License-Identifier: GPL-3.0-or-later
from math import degrees
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from . import draft
from .geometry.magnet import Magnet
from .geometry.mesh import evaluated_mm
from .geometry.planar import split
from .geometry.symmetry import SymmetricCut, split_symmetric
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .operators import active_mesh, report_failure
from .settings import MAGNET_SHAPES, TNTMESH_PG_settings

PRESETS = {
    "DISC_6": ("Ø6 × 3 mm", ("DISC", 6, 6, 3)),
    "DISC_8": ("Ø8 × 4 mm", ("DISC", 8, 8, 4)),
    "BLOCK_6": ("6 × 4 × 2 mm", ("BLOCK", 6, 4, 2)),
    "BLOCK_8": ("8 × 4 × 3 mm", ("BLOCK", 8, 4, 3)),
}


class TNTMESH_PG_magnet_size(bpy.types.PropertyGroup):
    shape: EnumProperty(name="Shape", items=MAGNET_SHAPES)
    width: FloatProperty(name="Magnet width (mm)", default=6, min=.01, precision=2)
    length: FloatProperty(name="Magnet length (mm)", default=4, min=.01, precision=2)
    thickness: FloatProperty(name="Magnet thickness (mm)", default=3, min=.01, precision=2)


def active_settings(context: bpy.types.Context) -> TNTMESH_PG_settings | None:
    scene = context.scene
    settings = scene.tntmesh_settings
    if settings.mode == "DRAFT":
        plan = draft.active_plan(scene)
        cut = draft.active_cut(plan) if plan is not None else None
        if cut is None:
            return None
        settings = cut.settings
    return settings if settings.cut_kind in {"PLANAR", "SYMMETRY"} and settings.connector == "MAGNET" else None


class TNTMESH_OT_magnet_library(bpy.types.Operator):
    bl_idname = "tntmesh.magnet_library"
    bl_label = "Change Magnet Size"
    bl_options = {"UNDO", "INTERNAL"}

    action: EnumProperty(items=[
        ("PRESET", "Use Stock Size", ""), ("SAVE", "Save Magnet Size", ""),
        ("USE", "Use Saved Size", ""), ("REMOVE", "Remove Saved Size", ""),
    ])
    preset: EnumProperty(items=[(key, label, "") for key, (label, _) in PRESETS.items()])

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and active_settings(context) is not None

    @classmethod
    def description(cls, context: bpy.types.Context, properties: bpy.types.OperatorProperties) -> str:
        return tr(cls.bl_rna.properties["action"].enum_items[properties.action].name)

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = active_settings(context)
        scene = context.scene
        library, index = scene.tntmesh_magnet_library, scene.tntmesh_magnet_index
        if self.action == "PRESET":
            _, size = PRESETS[self.preset]
        elif self.action == "SAVE":
            item = library.add()
            item.shape, item.width, item.length, item.thickness = (
                settings.magnet_shape, settings.magnet_width, settings.magnet_length, settings.magnet_thickness,
            )
            item.name = magnet_size(settings.magnet_config(1))
            scene.tntmesh_magnet_index = len(library) - 1
            return {"FINISHED"}
        elif index >= len(library):
            return {"CANCELLED"}
        elif self.action == "REMOVE":
            library.remove(index)
            scene.tntmesh_magnet_index = max(0, min(index, len(library) - 1))
            return {"FINISHED"}
        else:
            item = library[index]
            size = item.shape, item.width, item.length, item.thickness
        settings.magnet_shape, settings.magnet_width, settings.magnet_length, settings.magnet_thickness = size
        return {"FINISHED"}


class TNTMESH_MT_magnet_sizes(bpy.types.Menu):
    bl_label = "Stock Sizes"

    def draw(self, context: bpy.types.Context) -> None:
        for key, (label, _) in PRESETS.items():
            tool = self.layout.operator("tntmesh.magnet_library", text=label, translate=False)
            tool.action = "PRESET"
            tool.preset = key


class TNTMESH_UL_magnet_sizes(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "name", text="", emboss=False)


def magnet_size(design: Magnet) -> str:
    if design.shape == "DISC":
        return f"Ø{design.width:.3g} × {design.thickness:.3g} mm"
    return f"{design.width:.3g} × {design.length:.3g} × {design.thickness:.3g} mm"


def component_report(name: str, design: Magnet, seams: int, kerf: float) -> str:
    shape = tr("Disc") if design.shape == "DISC" else tr("Block")
    summary = [
        tr("TNTMesh · Magnet Components"),
        tr("Model · {name}").format(name=name),
        tr("Magnets required · {count}").format(count=design.count * seams * 2),
        tr("Magnet size · {shape} {size}").format(shape=shape, size=magnet_size(design)),
        tr("Magnet pairs · {count}").format(count=design.count * seams),
        tr("Pocket depth · {size:.2f} mm").format(size=design.depth),
        tr("Side clearance · {size:.2f} mm").format(size=design.lateral),
        tr("Adhesive gap · {size:.2f} mm").format(size=design.adhesive),
        tr("Gap between installed faces · {size:.2f} mm").format(size=kerf + 2 * design.inset),
    ]
    if design.shape == "BLOCK":
        summary.append(tr("Primary cut rotation · {angle:.1f}°").format(angle=degrees(design.angle)))
    return "\n".join(summary) + "\n"


class TNTMESH_OT_export_magnet_report(bpy.types.Operator, ExportHelper):
    bl_idname = "tntmesh.export_magnet_report"
    bl_label = "Export Magnet List"
    bl_description = "Verify the cut and write a list of the required purchased magnets"
    filename_ext = ".txt"
    filter_glob: StringProperty(default="*.txt", options={"HIDDEN"})
    check_existing: BoolProperty(default=True, options={"HIDDEN"})

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        if context.mode != "OBJECT" or active_settings(context) is None:
            return False
        if context.scene.tntmesh_settings.mode == "DRAFT":
            plan = draft.active_plan(context.scene)
            return plan is not None and plan.source is not None
        return active_mesh(context) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        path = Path(self.filepath)
        if path.exists():
            return report_failure(self, MeshError("Choose a new file name for the magnet list."))
        scene = context.scene
        settings = active_settings(context)
        wm = context.window_manager
        wm.progress_begin(0, 2)
        try:
            unit = millimeters_per_unit(scene)
            with GeometryTransaction() as transaction:
                if scene.tntmesh_settings.mode == "DRAFT":
                    plan = draft.active_plan(scene)
                    obj = plan.source
                    mesh = draft.target_mesh(context, transaction, plan, plan.cut_index, unit)
                else:
                    obj = active_mesh(context)
                    mesh, _ = evaluated_mm(context, obj, transaction, unit)
                config = settings.config(obj)
                if isinstance(config, SymmetricCut):
                    split_symmetric(context, transaction, mesh, config)
                    planar, seams = config.primary, 2
                else:
                    split(context, transaction, mesh, config)
                    planar, seams = config, 1
                wm.progress_update(1)
                text = component_report(obj.name, planar.connector, seams, planar.kerf)
            output = path.open("x", encoding="utf-8")
            try:
                with output:
                    output.write(text)
            except OSError:
                path.unlink(missing_ok=True)
                raise
            wm.progress_update(2)
        except FileExistsError:
            return report_failure(self, MeshError("Choose a new file name for the magnet list."))
        except OSError:
            return report_failure(self, MeshError("Could not write the magnet list."))
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report({"INFO"}, tr("Exported a list for {count} magnets.").format(count=planar.connector.count * seams * 2))
        return {"FINISHED"}


def magnet_details(layout: bpy.types.UILayout, settings: TNTMESH_PG_settings, scene: bpy.types.Scene) -> None:
    row = layout.row(align=True)
    row.menu("TNTMESH_MT_magnet_sizes", text="Stock Sizes")
    row.operator("tntmesh.magnet_library", text="", icon="ADD").action = "SAVE"
    library = scene.tntmesh_magnet_library
    if library:
        row = layout.row()
        row.template_list("TNTMESH_UL_magnet_sizes", "", scene, "tntmesh_magnet_library", scene,
                          "tntmesh_magnet_index", rows=2)
        buttons = row.column(align=True)
        buttons.operator("tntmesh.magnet_library", text="", icon="CHECKMARK").action = "USE"
        buttons.operator("tntmesh.magnet_library", text="", icon="REMOVE").action = "REMOVE"
        if scene.tntmesh_magnet_index < len(library):
            selected = library[scene.tntmesh_magnet_index]
            layout.prop(selected, "shape")
            layout.prop(selected, "width", text="Saved diameter (mm)" if selected.shape == "DISC" else "Saved width (mm)")
            if selected.shape == "BLOCK":
                layout.prop(selected, "length", text="Saved length (mm)")
            layout.prop(selected, "thickness", text="Saved thickness (mm)")
    layout.prop(settings, "magnet_shape")
    if settings.magnet_shape == "DISC":
        layout.prop(settings, "magnet_width", text="Diameter (mm)")
    else:
        layout.prop(settings, "magnet_width")
    if settings.magnet_shape == "BLOCK":
        layout.prop(settings, "magnet_length")
        layout.prop(settings, "magnet_angle")
    for name in ("magnet_thickness", "magnet_inset", "magnet_adhesive", "lateral", "wall"):
        layout.prop(settings, name)
    label = tr("Pocket depth · {size:.2f} mm").format(size=settings.magnet_config(1).depth)
    layout.label(text=label, translate=False)
    if settings.cut_kind != "PLANAR" or not settings.connector_points:
        layout.prop(settings, "connector_count")
    layout.operator("tntmesh.export_magnet_report", icon="EXPORT")


CLASSES = (TNTMESH_PG_magnet_size, TNTMESH_OT_magnet_library, TNTMESH_MT_magnet_sizes,
           TNTMESH_UL_magnet_sizes, TNTMESH_OT_export_magnet_report)
