# SPDX-License-Identifier: GPL-3.0-or-later
import logging
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    StringProperty,
)
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector

from . import draft, exporters, stl
from .geometry.grid import fit_grid
from .geometry.material_split import split_materials
from .geometry.mesh import bounds, evaluated_mm, inspect
from .geometry.planar import PlanarCut, axis_frame
from .geometry.repair import repair_copy
from .geometry.volume import apply_cut, structural_parts
from .localization import tr
from .model import (
    ASSEMBLY_DIRECTION,
    MATERIAL_SLOT,
    PART_ID,
    PART_KIND,
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
    meshes: Sequence[bpy.types.Mesh], origin: Vector, unit: float, *, bodies: int | None = None,
    direction: Vector | None = None,
    labels: Sequence[str] | None = None,
) -> list[bpy.types.Object]:
    project_id = source.get(PROJECT_ID) or uuid4().hex
    collection = owned_collection(context.scene, "part")
    parts = []
    for index, mesh in enumerate(meshes, 1):
        mesh.transform(Matrix.Scale(1.0 / unit, 4))
        mesh.update()
        label = (tr("Pin {number}").format(number=index - bodies)
                 if bodies is not None and index > bodies else f"{index:02d}")
        if labels is not None:
            label = labels[index - 1]
        obj = transaction.object(collection, f"{source.name} · {label}", mesh)
        obj.location = origin
        identify_part(obj, project_id)
        obj[PART_KIND] = "pin" if bodies is not None and index > bodies else "body"
        obj["tntmesh_parent_part_id"] = source.get(PART_ID, "")
        if direction is not None and index in (1, 2):
            inherited = Vector(source.get(ASSEMBLY_DIRECTION, (0, 0, 0)))
            obj[ASSEMBLY_DIRECTION] = tuple(inherited + (direction if index == 2 else -direction))
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
                config = settings.config(source)
                meshes = apply_cut(context, transaction, mesh, config, origin, unit, source)
                wm.progress_update(2)
                parts = publish_parts(
                    context, transaction, source, meshes, origin, unit,
                    bodies=structural_parts(settings.cut_kind),
                    direction=axis_frame(config.axis, config.rotation).col[2]
                    if isinstance(config, PlanarCut) else None,
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


class TNTMESH_OT_split_materials(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.split_materials"
    bl_label = "Separate by Material"
    bl_description = "Extract a closed piece per material slot and keep a solid remainder"
    bl_options = {"UNDO"}
    keep_slot: IntProperty(name="Retained material slot", min=1, default=1)
    depth: FloatProperty(name="Depth (mm)", default=2, min=.01, precision=3)
    with_connectors: BoolProperty(
        name="Connect to the main body",
        description="Fit each extracted piece to the retained material using the region connector settings",
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (MeshOperator.poll(context) and context.scene.tntmesh_settings.mode == "EASY"
                and len(context.active_object.material_slots) >= 2)

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        self.depth = context.scene.tntmesh_settings.region_depth
        self.with_connectors = context.scene.tntmesh_settings.region_connector != "NONE"
        return context.window_manager.invoke_props_dialog(self, width=330)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "keep_slot")
        slots = context.active_object.material_slots
        if self.keep_slot <= len(slots):
            name = slots[self.keep_slot - 1].name or tr("Empty material slot")
            layout.label(text=name, icon="MATERIAL", translate=False)
        layout.prop(self, "depth")
        if context.scene.tntmesh_settings.region_connector != "NONE":
            layout.prop(self, "with_connectors")

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_settings
        unit = millimeters_per_unit(context.scene)
        wm = context.window_manager
        wm.progress_begin(0, 3)
        try:
            connector = settings.region_config().connector if self.with_connectors else None
            if self.with_connectors and connector is None:
                raise MeshError("Choose a region connector before separating by material.")
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                wm.progress_update(1)
                cuts = split_materials(
                    context, transaction, mesh, source, self.keep_slot, self.depth,
                    smoothing=settings.region_smoothing, connector=connector,
                )
                wm.progress_update(2)
                labels = []
                for cut in cuts:
                    label = cut.name or tr("Slot {number}").format(number=cut.slot)
                    if cut.pin:
                        label += " · " + tr("Pin {number}").format(number=cut.pin)
                    labels.append(label)
                parts = publish_parts(
                    context, transaction, source, [cut.mesh for cut in cuts], origin, unit, labels=labels,
                )
                for obj, cut in zip(parts, cuts, strict=True):
                    obj[MATERIAL_SLOT] = cut.slot
                    obj[PART_KIND] = "pin" if cut.pin else "body"
                    material = mesh.materials[cut.slot - 1]
                    if material is not None:
                        obj.color = material.diffuse_color
            select_new_parts(context, source, parts)
            wm.progress_update(3)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report({"INFO"}, tr("Created {count} material pieces.").format(count=len(parts)))
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
    bl_description = "Apply the selected mesh repairs to a new copy"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_settings
        unit = millimeters_per_unit(context.scene)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                repair_copy(
                    mesh, settings.repair_weld, settings.repair_hole_edges if settings.repair_holes else 0,
                    correct_orientation=settings.repair_orientation,
                )
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
    bl_description = "Export generated pieces in STL, OBJ, FBX, PLY or 3MF"

    directory: StringProperty(subtype="DIR_PATH")
    file_format: EnumProperty(
        name="Format",
        items=[(format_id, format_id, "") for format_id in ("STL", "OBJ", "FBX", "PLY", "3MF")],
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
            ("CONNECTORS", "Loose Connectors", "Export only current loose connectors in this view layer"),
        ],
        default="SELECTED",
    )
    include_pins: BoolProperty(name="Include Loose Connectors", default=True)
    as_zip: BoolProperty(name="Save as ZIP")
    create_subfolder: BoolProperty(
        name="Use a Subfolder", description="Create a folder in the destination or inside the ZIP",
    )
    name_prefix: StringProperty(name="Prefix", description="Start export names with this prefix", maxlen=64)
    numbered: BoolProperty(name="Number Files", default=True)
    placement: EnumProperty(
        name="Placement",
        items=[
            ("ASSEMBLY", "Assembly Positions", "Keep the position and orientation of each piece"),
            ("BED", "Build Plate", "Rotate each exported piece and lower it to Z = 0"),
        ],
        default="ASSEMBLY",
    )
    print_rotation: FloatVectorProperty(name="Print Rotation", subtype="EULER", size=3)
    part_spacing: FloatProperty(name="Spacing (mm)", default=3, min=0, soft_max=30, precision=2)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(managed_parts(context, "ALL"))

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if not managed_parts(context, "SELECTED"):
            self.scope = "ALL"
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        files = layout.column(align=True)
        files.prop(self, "file_format")
        files.prop(self, "scope")
        if self.scope != "CONNECTORS":
            files.prop(self, "include_pins")
        if self.file_format == "3MF":
            files.prop(self, "grouped_3mf")

        layout.separator()
        placement = layout.column(align=True)
        placement.label(text=tr("Placement"), translate=False)
        placement.prop(self, "placement", text="")
        if self.placement == "BED":
            placement.prop(self, "print_rotation")
            if self.file_format == "3MF" and self.grouped_3mf:
                placement.prop(self, "part_spacing")

        layout.separator()
        output = layout.column(align=True)
        output.prop(self, "name_prefix")
        if self.file_format != "3MF" or not self.grouped_3mf:
            output.prop(self, "numbered")
        output.prop(self, "as_zip")
        output.prop(self, "create_subfolder")

    def execute(self, context: bpy.types.Context) -> set[str]:
        pieces = managed_parts(context, self.scope)
        if self.scope == "CONNECTORS" or not self.include_pins:
            connectors_only = self.scope == "CONNECTORS"
            pieces = [obj for obj in pieces if exporters.is_loose_connector(obj) == connectors_only]
        if not pieces:
            if self.scope == "CONNECTORS":
                return report_failure(self, MeshError("There are no loose connectors to export."))
            return report_failure(self, MeshError("Select generated pieces to export."))
        path = Path(self.directory)
        if not self.directory or not path.is_dir():
            return report_failure(self, MeshError("Choose an existing destination folder."))
        try:
            on_bed = self.placement == "BED"
            grouped = self.grouped_3mf and self.file_format == "3MF"
            printer = selected_printer(context.scene) if on_bed and grouped else None
            options = exporters.ExportOptions(
                as_zip=self.as_zip, subfolder=self.create_subfolder, prefix=self.name_prefix,
                numbered=self.numbered, on_bed=on_bed, rotation=tuple(self.print_rotation),
                spacing_mm=self.part_spacing,
                printer=printer.data() if printer else None,
            )
            outputs = exporters.export_parts(
                context, pieces, path, self.file_format, grouped=grouped, options=options,
            )
        except (MeshError, OSError, RuntimeError, ValueError, OverflowError) as error:
            return report_failure(self, error)
        self.report(
            {"INFO"}, tr("Exported {count} {format} file(s).").format(
                count=len(outputs), format="ZIP" if self.as_zip else self.file_format
            ),
        )
        return {"FINISHED"}


CLASSES = (
    TNTMESH_OT_import_stl, TNTMESH_OT_resize, TNTMESH_OT_split,
    TNTMESH_OT_fit_grid, TNTMESH_OT_split_materials, TNTMESH_OT_validate,
    TNTMESH_OT_repair, TNTMESH_OT_export_stl,
)
