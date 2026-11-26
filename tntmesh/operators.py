# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from pathlib import Path
from uuid import uuid4

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix

from . import stl
from .geometry.mesh import bounds, evaluated_mm, inspect
from .geometry.planar import split
from .localization import tr
from .model import (
    DRAFT_ID,
    PART_ID,
    PROJECT_ID,
    ROLE,
    GeometryTransaction,
    MeshError,
    identify_part,
    millimeters_per_unit,
    owned_collection,
)

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
        project_id = source.get(PROJECT_ID) or uuid4().hex
        parts = []
        wm = context.window_manager
        wm.progress_begin(0, 3)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                wm.progress_update(1)
                meshes = split(context, transaction, mesh, settings.config())
                wm.progress_update(2)
                collection = owned_collection(context.scene, "part")
                for index, result in enumerate(meshes, 1):
                    result.transform(Matrix.Scale(1.0 / unit, 4))
                    result.update()
                    obj = transaction.object(collection, f"{source.name} · {index:02d}", result)
                    obj.location = origin
                    identify_part(obj, project_id)
                    obj["tntmesh_parent_part_id"] = source.get(PART_ID, "")
                    if source.get(DRAFT_ID):
                        obj[DRAFT_ID] = source[DRAFT_ID]
                    parts.append(obj)
                for obj in parts:
                    transaction.publish(obj)
            context.view_layer.update()
            select_results(context, parts)
            if source.get(ROLE) == "part":
                source[ROLE] = "superseded"
            if settings.hide_source:
                source.hide_set(True)
            settings.show_plane = False
            wm.progress_update(3)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report({"INFO"}, tr("Created two pieces. The input mesh was kept."))
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


class TNTMESH_OT_export_stl(bpy.types.Operator):
    bl_idname = "tntmesh.export_stl"
    bl_label = "Export STL Pieces"
    bl_description = "Write one validated, millimeter-based STL per generated piece"

    directory: StringProperty(subtype="DIR_PATH")
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

    def execute(self, context: bpy.types.Context) -> set[str]:
        pieces = managed_parts(context, self.scope)
        if not pieces:
            return report_failure(self, MeshError("Select generated pieces to export."))
        path = Path(self.directory)
        if not self.directory or not path.is_dir():
            return report_failure(self, MeshError("Choose an existing destination folder."))
        try:
            outputs = stl.export_parts(context, pieces, path)
        except (MeshError, OSError, RuntimeError, ValueError, OverflowError) as error:
            return report_failure(self, error)
        self.report({"INFO"}, tr("Exported {count} STL file(s).").format(count=len(outputs)))
        return {"FINISHED"}


CLASSES = (
    TNTMESH_OT_import_stl, TNTMESH_OT_resize, TNTMESH_OT_split,
    TNTMESH_OT_validate, TNTMESH_OT_export_stl,
)
