# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector

from . import draft, exporters, stl
from .geometry.grid import fit_grid
from .geometry.mesh import bounds, evaluated_mm, inspect
from .geometry.repair import repair_copy
from .geometry.volume import apply_cut
from .localization import tr
from .model import (
    PART_ID,
    PROJECT_ID,
    ROLE,
    GeometryTransaction,
    MeshError,
    identify_part,
    millimeters_per_unit,
    owned_collection,
)
from .printer_props import selected_printer

LOG = logging.getLogger(__name__)


def active_mesh(context: bpy.types.Context) -> bpy.types.Object | None:
    obj = context.active_object
    if obj is not None and obj.type == "MESH" and not obj.hide_get():
        return obj
    return None


def select_results(context: bpy.types.Context, objects: list[bpy.types.Object]) -> None:
    for obj in context.selected_objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]


def managed_parts(context: bpy.types.Context, scope: str) -> list[bpy.types.Object]:
    objects = context.selected_objects if scope == "SELECTED" else context.view_layer.objects
    return sorted(
        (obj for obj in objects if obj is not None and obj.type == "MESH" and obj.get(ROLE) == "part"),
        key=lambda obj: obj.name.casefold(),
    )


def publish_parts(
    context: bpy.types.Context, transaction: GeometryTransaction, source: bpy.types.Object,
    meshes: Sequence[bpy.types.Mesh], origin: Vector, unit: float, *, loose_pins: bool = False,
) -> list[bpy.types.Object]:
    project_id = source.get(PROJECT_ID) or uuid4().hex
    collection = owned_collection(context.scene, "part")
    parts = []
    for index, mesh in enumerate(meshes, 1):
        mesh.transform(Matrix.Scale(1.0 / unit, 4))
        mesh.update()
        label = tr("Pin {number}").format(number=index - 2) if loose_pins and index > 2 else f"{index:02d}"
        obj = transaction.object(collection, f"{source.name} · {label}", mesh)
        obj.location = origin
        identify_part(obj, project_id)
        obj["tntmesh_parent_part_id"] = source.get(PART_ID, "")
        parts.append(obj)
    for obj in parts:
        transaction.publish(obj)
    return parts


def select_new_parts(
    context: bpy.types.Context, source: bpy.types.Object, parts: list[bpy.types.Object],
) -> None:
    context.view_layer.update()
    select_results(context, parts)
    draft.track_followups(context.scene, source, parts)
    if source.get(ROLE) == "part":
        source[ROLE] = "superseded"
    settings = context.scene.tntmesh_settings
    if settings.hide_source:
        source.hide_set(True)
    settings.show_plane = False


def report_failure(operator: bpy.types.Operator, error: Exception) -> set[str]:
    if isinstance(error, MeshError):
        message = tr(str(error))
    else:
        LOG.exception("TNTMesh operation failed")
        message = tr("The operation failed. Details are available in Blender's console.")
    operator.report({"WARNING"}, message)
    return {"CANCELLED"}


class MeshOperator:
    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and active_mesh(context) is not None


class TNTMESH_OT_import_stl(bpy.types.Operator, ImportHelper):
    bl_idname = "tntmesh.import_stl"
    bl_label = "Import STL"
    bl_description = "Import an STL using explicit length units"
    bl_options = {"REGISTER", "UNDO"}
    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})
    units: EnumProperty(
        name="STL units",
        items=[
            ("MM", "Millimeters", "Treat a unit in the file as one millimeter"),
            ("CM", "Centimeters", "Treat a unit in the file as one centimeter"),
            ("IN", "Inches", "Treat a unit in the file as one inch"),
        ],
        default="MM",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT"

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            obj = stl.import_model(context, Path(self.filepath),
                                   {"MM": 1.0, "CM": 10.0, "IN": 25.4}[self.units])
            collection = owned_collection(context.scene, "source")
            collection.objects.link(obj)
            for previous in list(obj.users_collection):
                if previous != collection:
                    previous.objects.unlink(obj)
            obj[ROLE] = "source"
            obj[PROJECT_ID] = uuid4().hex
            select_results(context, [obj])
            context.scene.tntmesh_settings.show_plane = True
        except (MeshError, OSError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        return {"FINISHED"}


class TNTMESH_OT_resize(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.resize"
    bl_label = "Create scaled copy"
    bl_description = "Resize a new copy to the target dimension and keep the input model"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_settings
        unit = millimeters_per_unit(context.scene)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                lower, upper = bounds(vertex.co for vertex in mesh.vertices)
                dimension = (upper - lower)["XYZ".index(settings.scale_axis)]
                if dimension <= 0:
                    raise MeshError("The selected axis has no measurable size.")
                scale = settings.target_size / dimension / unit
                mesh.transform(Matrix.Scale(scale, 4))
                mesh.update()
                collection = owned_collection(context.scene, "source")
                copy = transaction.object(collection, f"{source.name} · Scaled", mesh)
                copy.location = origin
                copy[ROLE] = "source"
                copy[PROJECT_ID] = uuid4().hex
                transaction.publish(copy)
            context.view_layer.update()
            select_results(context, [copy])
            settings.show_plane = True
            if settings.hide_source and source.get(ROLE) != "part":
                source.hide_set(True)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        return {"FINISHED"}


class TNTMESH_OT_split(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.split"
    bl_label = "Split Model"
    bl_description = "Split the active model into two pieces and keep the input mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_settings
        unit = millimeters_per_unit(context.scene)
        wm = context.window_manager
        wm.progress_begin(0, 3)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                wm.progress_update(1)
                meshes = apply_cut(context, transaction, mesh, settings.config(), origin, unit, source)
                wm.progress_update(2)
                parts = publish_parts(
                    context, transaction, source, meshes, origin, unit, loose_pins=len(meshes) > 2
                )
            select_new_parts(context, source, parts)
            wm.progress_update(3)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report(
            {"INFO"}, tr("Created {count} pieces. The input mesh was kept.").format(count=len(parts))
        )
        return {"FINISHED"}


class TNTMESH_OT_fit_grid(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.fit_grid"
    bl_label = "Split to Fit"
    bl_description = "Use straight cuts to fit every piece within the printer's useful dimensions"
    bl_options = {"UNDO"}

    max_pieces: IntProperty(name="Piece limit", default=64, min=2, max=4096)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return MeshOperator.poll(context) and selected_printer(context.scene) is not None

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.label(text="Split with straight cuts and no connectors.", icon="INFO")
        self.layout.prop(self, "max_pieces")

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        profile = selected_printer(context.scene).data()
        unit = millimeters_per_unit(context.scene)
        wm = context.window_manager
        wm.progress_begin(0, 3)
        try:
            profile.validate()
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                wm.progress_update(1)
                meshes = fit_grid(context, transaction, mesh, profile.limits, self.max_pieces)
                wm.progress_update(2)
                if len(meshes) == 1:
                    self.report({"INFO"}, tr("The model already fits in this orientation."))
                    return {"CANCELLED"}
                parts = publish_parts(context, transaction, source, meshes, origin, unit)
            select_new_parts(context, source, parts)
            wm.progress_update(3)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report({"INFO"}, tr("Created {count} pieces that fit the profile.").format(count=len(parts)))
        return {"FINISHED"}


class TNTMESH_OT_validate(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.validate"
    bl_label = "Check Mesh"
    bl_description = "Check closure, face orientation and enclosed volume"

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            with GeometryTransaction() as transaction:
                mesh, _ = evaluated_mm(
                    context, active_mesh(context), transaction, millimeters_per_unit(context.scene)
                )
                result = inspect(mesh)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        self.report(
            {"INFO"},
            tr("Closed mesh · {volume:.2f} mm³ · {shells} shell(s)").format(
                volume=result.volume_mm3, shells=result.shells
            ),
        )
        return {"FINISHED"}


class TNTMESH_OT_repair(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.repair"
    bl_label = "Create Repaired Copy"
    bl_description = "Weld close vertices and optionally fill simple holes on a new copy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_settings
        unit = millimeters_per_unit(context.scene)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                repair_copy(mesh, settings.repair_weld,
                            settings.repair_hole_edges if settings.repair_holes else 0)
                mesh.transform(Matrix.Scale(1.0 / unit, 4))
                mesh.update()
                collection = owned_collection(context.scene, "source")
                name = tr("{name} · Repaired").format(name=source.name)
                repaired = transaction.object(collection, name, mesh)
                repaired.location = origin
                repaired[ROLE] = "source"
                repaired[PROJECT_ID] = uuid4().hex
                transaction.publish(repaired)
            context.view_layer.update()
            select_results(context, [repaired])
            if settings.hide_source and source.get(ROLE) != "part":
                source.hide_set(True)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        self.report({"INFO"}, tr("Created a closed repaired copy. The input mesh was kept."))
        return {"FINISHED"}


class TNTMESH_OT_export_stl(bpy.types.Operator):
    bl_idname = "tntmesh.export_stl"
    bl_label = "Export Pieces"
    bl_description = "Export generated pieces in STL, OBJ, FBX or 3MF"

    directory: StringProperty(subtype="DIR_PATH")
    file_format: EnumProperty(
        name="Format",
        items=[(format_id, format_id, "") for format_id in ("STL", "OBJ", "FBX", "3MF")],
        default="STL",
    )
    grouped_3mf: BoolProperty(
        name="One 3MF for all pieces", description="Keep multiple separate objects in one 3MF",
    )
    scope: EnumProperty(
        name="Pieces",
        items=[
            ("SELECTED", "Selected", "Export selected generated pieces"),
            ("ALL", "All", "Export all current TNTMesh pieces in this view layer"),
        ],
        default="SELECTED",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(managed_parts(context, "ALL"))

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if not managed_parts(context, "SELECTED"):
            self.scope = "ALL"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.prop(self, "file_format")
        self.layout.prop(self, "scope")
        if self.file_format == "3MF":
            self.layout.prop(self, "grouped_3mf")

    def execute(self, context: bpy.types.Context) -> set[str]:
        pieces = managed_parts(context, self.scope)
        if not pieces:
            return report_failure(self, MeshError("Select generated pieces to export."))
        path = Path(self.directory)
        if not self.directory or not path.is_dir():
            return report_failure(self, MeshError("Choose an existing destination folder."))
        try:
            outputs = exporters.export_parts(
                context, pieces, path, self.file_format, grouped=self.grouped_3mf
            )
        except (MeshError, OSError, RuntimeError, ValueError, OverflowError) as error:
            return report_failure(self, error)
        self.report(
            {"INFO"}, tr("Exported {count} {format} file(s).").format(
                count=len(outputs), format=self.file_format
            ),
        )
        return {"FINISHED"}


CLASSES = (
    TNTMESH_OT_import_stl, TNTMESH_OT_resize, TNTMESH_OT_split,
    TNTMESH_OT_fit_grid, TNTMESH_OT_validate, TNTMESH_OT_repair, TNTMESH_OT_export_stl,
)
