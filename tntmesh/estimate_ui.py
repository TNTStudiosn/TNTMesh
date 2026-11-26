# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty

from . import assembly
from .estimate import Estimate, Material, PieceEstimate, estimate
from .localization import tr
from .model import MeshError, millimeters_per_unit
from .operators import active_mesh, report_failure
from .printer_props import TECHNOLOGIES, selected_printer


class TNTMESH_PG_estimate(bpy.types.PropertyGroup):
    scope: EnumProperty(name="Measure", items=[
        ("ACTIVE", "Active Mesh", "Estimate the active mesh"),
        ("SELECTED", "Selected Meshes", "Estimate all selected meshes in the view layer"),
        ("ASSEMBLY", "Assembly", "Estimate all pieces in the current assembly"),
    ])
    technology: EnumProperty(name="Technology", items=TECHNOLOGIES)
    density: FloatProperty(name="Density (g/cm³)", default=1.2, min=.01, precision=3)
    price: FloatProperty(name="Price per kg", min=0, precision=2)
    currency: StringProperty(name="Currency", default="USD", maxlen=6)
    wall_mm: FloatProperty(name="Wall thickness (mm)", default=.8, min=0, precision=2)
    infill: FloatProperty(name="Infill (%)", default=20, min=0, max=100, subtype="PERCENTAGE")
    extra: FloatProperty(name="Extra material (%)", min=0, max=500, soft_max=100, subtype="PERCENTAGE")
    check_cavities: BoolProperty(
        name="Check cavity savings", description="Compare closed cavities against filled outer shells",
        default=True,
    )

    def material(self) -> Material:
        return Material(self.technology, self.density, self.price, self.currency.strip().upper(),
                        self.wall_mm, self.infill / 100, self.extra / 100, self.check_cavities)


def targets(context: bpy.types.Context) -> list[bpy.types.Object]:
    scope = context.scene.tntmesh_estimate.scope
    if scope == "ASSEMBLY":
        return assembly.members(context)
    if scope == "SELECTED":
        return sorted((obj for obj in context.selected_objects if obj.type == "MESH"),
                      key=lambda obj: obj.name.casefold())
    obj = active_mesh(context)
    return [obj] if obj is not None else []


@dataclass(frozen=True)
class Preview:
    fingerprint: tuple
    affected: frozenset[int]
    result: Estimate


_preview: Preview | None = None


def fingerprint(context: bpy.types.Context, objects: list[bpy.types.Object]) -> tuple:
    scene = context.scene
    settings = scene.tntmesh_estimate
    return (scene.as_pointer(), settings.material(), settings.scope, millimeters_per_unit(scene), tuple(
        (obj.as_pointer(), obj.data.as_pointer(), obj.name, tuple(tuple(row) for row in obj.matrix_world))
        for obj in objects
    ))


@persistent
def clear(*_args: object) -> None:
    global _preview
    _preview = None


@persistent
def invalidate(_scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph) -> None:
    if _preview is not None and any(
        update.id.original.as_pointer() in _preview.affected
        and (update.is_updated_geometry or update.is_updated_transform)
        for update in depsgraph.updates
    ):
        clear()


def current(context: bpy.types.Context) -> Estimate | None:
    if _preview is not None and _preview.fingerprint == fingerprint(context, targets(context)):
        return _preview.result
    return None


class TNTMESH_OT_use_estimate_profile(bpy.types.Operator):
    bl_idname = "tntmesh.use_estimate_profile"
    bl_label = "Use Printer Material"
    bl_description = "Copy the selected printer's technology, density, price and wall thickness"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return selected_printer(context.scene) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        settings = context.scene.tntmesh_estimate
        printer = selected_printer(context.scene)
        settings.technology = printer.technology
        settings.density = printer.density_g_cm3
        settings.price = printer.price_per_kg
        settings.wall_mm = printer.min_wall_mm
        return {"FINISHED"}


class TNTMESH_OT_estimate_material(bpy.types.Operator):
    bl_idname = "tntmesh.estimate_material"
    bl_label = "Calculate Estimate"
    bl_description = "Calculate volume, weight and material cost for the chosen meshes"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(targets(context))

    def execute(self, context: bpy.types.Context) -> set[str]:
        global _preview
        clear()
        objects = targets(context)
        context.window_manager.progress_begin(0, 1)
        try:
            report = estimate(context, objects, context.scene.tntmesh_estimate.material())
            context.view_layer.update()
            pointers = frozenset(item.as_pointer() for obj in objects for item in (obj, obj.data))
            _preview = Preview(fingerprint(context, objects), pointers, report)
            context.window_manager.progress_update(1)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            context.window_manager.progress_end()
        self.report({"INFO"}, tr("Estimated material for {count} mesh(es).").format(count=len(report.entries)))
        return {"FINISHED"}


def draw_values(layout: bpy.types.UILayout, piece: PieceEstimate, material: Material) -> None:
    volume_unit = "mL" if material.technology == "RESIN" else "cm³"
    fields = [
        ("Model volume", f"{piece.model_ml:.2f} cm³"),
        ("Print material", f"{piece.printed_ml:.2f} {volume_unit}"),
    ]
    if material.extra:
        fields.append(("Additional material", f"{piece.extra_ml:.2f} {volume_unit}"))
    fields.extend((("Estimated weight", f"{piece.grams:.2f} g"),
                   ("Material cost", f"{piece.cost:.2f} {material.currency}")))
    if material.technology == "RESIN" and material.check_cavities:
        if piece.saved_ml is not None:
            fields.append(("Closed cavity savings", f"{piece.saved_ml:.2f} mL"))
        else:
            layout.label(text="Cavity savings unavailable for this geometry.", icon="INFO")
    for label, value in fields:
        row = layout.split(factor=.62)
        row.label(text=label)
        row.label(text=value, translate=False)


class TNTMESH_PT_estimate(bpy.types.Panel):
    bl_label = "Material & Cost"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.tntmesh_estimate
        if selected_printer(context.scene) is not None:
            layout.operator("tntmesh.use_estimate_profile", icon="PRESET")
        layout.prop(settings, "scope", text="")
        layout.row(align=True).prop(settings, "technology", expand=True)
        for name in ("density", "price", "currency"):
            layout.prop(settings, name)
        if settings.technology == "FDM":
            row = layout.column(align=True)
            row.prop(settings, "wall_mm")
            row.prop(settings, "infill")
        else:
            layout.prop(settings, "check_cavities")
        layout.prop(settings, "extra")
        layout.operator("tntmesh.estimate_material", icon="DRIVER_DISTANCE")
        if not targets(context):
            layout.label(text="Choose at least one mesh for the estimate.", icon="INFO")
        report = current(context)
        if report is None:
            return
        material = settings.material()
        box = layout.box()
        box.label(text="Total Estimate", icon="INFO")
        draw_values(box, report.total, material)
        if len(report.entries) > 1:
            header, detail = layout.panel("tntmesh_estimate_pieces", default_closed=True)
            header.label(text="Per Piece")
            if detail:
                for piece in report.entries:
                    box = detail.box()
                    box.label(text=piece.name, translate=False, icon="MESH_DATA")
                    draw_values(box, piece, material)
        layout.label(text="Verify in your slicer.", icon="INFO")


def register() -> None:
    bpy.app.handlers.depsgraph_update_post.append(invalidate)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
        handlers.append(clear)


def unregister() -> None:
    for handlers, callback in (
        (bpy.app.handlers.depsgraph_update_post, invalidate),
        (bpy.app.handlers.undo_post, clear), (bpy.app.handlers.redo_post, clear), (bpy.app.handlers.load_post, clear),
    ):
        if callback in handlers:
            handlers.remove(callback)
    clear()


CLASSES = (TNTMESH_PG_estimate, TNTMESH_OT_use_estimate_profile, TNTMESH_OT_estimate_material, TNTMESH_PT_estimate)
