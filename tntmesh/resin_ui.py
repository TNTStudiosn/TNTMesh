# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    PointerProperty,
)
from mathutils import Matrix, Vector

from .draw_snapping import SurfacePicker
from .geometry import resin
from .geometry.mesh import evaluated_mm
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .operators import MeshOperator, active_mesh, publish_parts, report_failure, select_new_parts

RESIN_REFERENCE = "tntmesh_resin_reference"


def mesh_only(_settings, obj: bpy.types.Object) -> bool:
    return obj.type == "MESH"


class TNTMESH_PG_resin(bpy.types.PropertyGroup):
    wall_mm: FloatProperty(name="Wall thickness (mm)", default=2, min=.05, precision=2)
    minimum_mm: FloatProperty(name="Minimum wall (mm)", default=1.2, min=.05, precision=2)
    voxel_mm: FloatProperty(name="Voxel size (mm)", default=.5, min=.05, precision=2)
    protection: PointerProperty(name="Solid region", type=bpy.types.Object, poll=mesh_only,
                                description="Closed mesh volume to leave solid when hollowing")
    reinforcement_mm: FloatProperty(name="Reinforcement (mm)", default=0, min=0, precision=2)
    shape: EnumProperty(name="Drain shape", items=(
        ("ROUND", "Circular", "Cut a circular drain with the specified diameter and depth"),
        ("CUSTOM", "Custom mesh", "Use a closed cutter positioned across the exterior and cavity"),
    ))
    diameter_mm: FloatProperty(name="Diameter (mm)", default=4, min=.1, precision=2)
    depth_mm: FloatProperty(name="Depth (mm)", default=8, min=.1, precision=2)
    use_face_normal: BoolProperty(name="Use surface normal", default=True)
    direction: FloatVectorProperty(name="Inward direction", default=(0, 0, 1), precision=2)
    print_axis: FloatVectorProperty(name="Print direction", default=(0, 0, 1), precision=2)
    make_plug: BoolProperty(name="Generate plug", default=False)
    clearance_mm: FloatProperty(name="Radial clearance (mm)", default=.15, min=.01, precision=2)
    cutter: PointerProperty(name="Drain cutter", type=bpy.types.Object, poll=mesh_only)


def accessory(
    context: bpy.types.Context, transaction: GeometryTransaction, obj: bpy.types.Object | None,
    source: bpy.types.Object, origin: Vector, unit: float,
) -> bpy.types.Mesh | None:
    if obj is None:
        return None
    if obj == source or obj.name not in context.view_layer.objects:
        raise MeshError("Use a separate mesh in this view layer.")
    hidden = obj.hide_get()
    try:
        if hidden:
            obj.hide_set(False)
            context.view_layer.update()
        mesh, offset = evaluated_mm(context, obj, transaction, unit)
    finally:
        if hidden:
            obj.hide_set(True)
    mesh.transform(Matrix.Translation((offset - origin) * unit))
    mesh.update()
    return mesh


def cavity_reference(
    context: bpy.types.Context, transaction: GeometryTransaction, source: bpy.types.Object, origin: Vector, unit: float,
) -> bpy.types.Mesh | None:
    original = source.get(RESIN_REFERENCE)
    if not isinstance(original, bpy.types.Mesh):
        return None
    mesh = transaction.own_mesh(original.copy())
    world = source.evaluated_get(context.evaluated_depsgraph_get()).matrix_world.copy()
    world.translation -= origin
    mesh.transform(Matrix.Scale(unit, 4) @ world)
    if world.to_3x3().determinant() < 0:
        mesh.flip_normals()
    mesh.update()
    return mesh


class TNTMESH_OT_hollow_resin(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.hollow_resin"
    bl_label = "Create Hollow Copy"
    bl_description = "Hollow the evaluated mesh and keep the original geometry"
    bl_options = {"UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_resin
        unit = millimeters_per_unit(context.scene)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                protected = accessory(context, transaction, settings.protection, source, origin, unit)
                body, volume = resin.hollow(context, transaction, mesh, settings.wall_mm, settings.minimum_mm,
                                           settings.voxel_mm, protected, settings.reinforcement_mm)
                results = publish_parts(context, transaction, source, [body], origin, unit,
                                        labels=(tr("Hollow"),))
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        select_new_parts(context, source, results)
        self.report({"INFO"}, tr("Removed {volume:.2f} mL. Add a drain before printing.").format(volume=volume / 1000))
        return {"FINISHED"}


class TNTMESH_OT_drain_resin(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.drain_resin"
    bl_label = "Place Drain"
    bl_description = "Click the exterior to open a closed cavity"
    bl_options = {"UNDO"}

    suggested: BoolProperty(options={"SKIP_SAVE"})
    point: FloatVectorProperty(options={"SKIP_SAVE"})
    normal: FloatVectorProperty(options={"SKIP_SAVE"}, default=(0, 0, -1))

    def invoke(self, context: bpy.types.Context, _event: bpy.types.Event) -> set[str]:
        if self.suggested:
            return self.execute(context)
        if context.area is None or context.area.type != "VIEW_3D":
            return report_failure(self, MeshError("Use the 3D Viewport to place a drain."))
        source = active_mesh(context)
        self.source_pointer = source.as_pointer()
        view = context.area.spaces.active.region_3d
        if view is None:
            return {"CANCELLED"}
        context.area.header_text_set(tr("Click the exterior to place a drain · Esc to cancel"))
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def cancel(self, context: bpy.types.Context) -> None:
        if context.area is not None:
            context.area.header_text_set(None)

    def modal(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        source = active_mesh(context)
        if (source is None or source.as_pointer() != self.source_pointer or context.area is None
                or context.area.type != "VIEW_3D" or event.type in {"ESC", "RIGHTMOUSE"}):
            self.cancel(context)
            return {"CANCELLED"}
        if event.type != "LEFTMOUSE" or event.value != "PRESS":
            return {"PASS_THROUGH"}
        region = next(region for region in context.area.regions if region.type == "WINDOW")
        pixel = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
        if not (0 <= pixel.x < region.width and 0 <= pixel.y < region.height):
            return {"PASS_THROUGH"}
        depsgraph = context.evaluated_depsgraph_get()
        picker = SurfacePicker(source.evaluated_get(depsgraph), "SURFACE")
        hit = picker.pick(region, context.area.spaces.active.region_3d, pixel)
        if hit.surface is None:
            return {"RUNNING_MODAL"}
        self.point, self.normal = hit.surface, hit.normal
        self.cancel(context)
        return self.execute(context)

    def execute(self, context: bpy.types.Context) -> set[str]:
        source = active_mesh(context)
        settings = context.scene.tntmesh_resin
        unit = millimeters_per_unit(context.scene)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, source, transaction, unit)
                reference = cavity_reference(context, transaction, source, origin, unit)
                original = reference if reference is not None else mesh
                custom = None
                if self.suggested:
                    drain = resin.suggest(original, Vector(settings.print_axis), settings.diameter_mm,
                                          settings.depth_mm, drilled=mesh if reference is not None else None)
                    if drain is None:
                        raise MeshError("No drain fits along this print direction. Try placing one manually.")
                else:
                    inward = -Vector(self.normal) if settings.use_face_normal else Vector(settings.direction)
                    drain = resin.Drain((Vector(self.point) - origin) * unit, inward,
                                        settings.diameter_mm, settings.depth_mm)
                    if settings.shape == "CUSTOM":
                        custom = accessory(context, transaction, settings.cutter, source, origin, unit)
                        if custom is None:
                            raise MeshError("Choose a custom drain cutter mesh.")
                body = resin.drill(context, transaction, mesh, drain, custom, reference=reference)
                meshes, labels = [body], [tr("Drained")]
                if custom is None and settings.make_plug:
                    meshes.append(resin.plug(transaction, body, original, drain, settings.clearance_mm))
                    labels.append(tr("Drain Plug"))
                original.transform(Matrix.Scale(1 / unit, 4))
                original.name = ".TNTMesh closed cavity reference"
                results = publish_parts(context, transaction, source, meshes, origin, unit, labels=labels)
                results[0][RESIN_REFERENCE] = original
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        select_new_parts(context, source, results)
        self.report({"INFO"}, tr("Drain verified from the cavity to the exterior."))
        return {"FINISHED"}


class TNTMESH_PT_resin(bpy.types.Panel):
    bl_label = "Resin Preparation"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT"

    def draw(self, context: bpy.types.Context) -> None:
        settings = context.scene.tntmesh_resin
        hollow = self.layout.column(align=True)
        hollow.label(text="Hollow")
        for name in ("wall_mm", "minimum_mm", "voxel_mm"):
            hollow.prop(settings, name)
        hollow.label(text="Solid region")
        hollow.prop(settings, "protection", text="")
        if settings.protection:
            hollow.prop(settings, "reinforcement_mm")
        hollow.operator("tntmesh.hollow_resin", icon="MOD_SOLIDIFY")
        self.layout.separator()
        drain = self.layout.column(align=True)
        drain.label(text="Drain Holes")
        drain.prop(settings, "shape", text="")
        if settings.shape == "ROUND":
            drain.prop(settings, "diameter_mm")
            drain.prop(settings, "depth_mm")
            drain.prop(settings, "make_plug")
            if settings.make_plug:
                drain.prop(settings, "clearance_mm")
        else:
            drain.label(text="Drain cutter")
            drain.prop(settings, "cutter", text="")
        drain.prop(settings, "use_face_normal")
        if not settings.use_face_normal:
            drain.label(text="Inward direction")
            drain.row(align=True).prop(settings, "direction", text="", expand=True)
        drain.operator("tntmesh.drain_resin", icon="EYEDROPPER")
        if settings.shape == "ROUND":
            drain.label(text="Print direction")
            drain.row(align=True).prop(settings, "print_axis", text="", expand=True)
            drain.operator("tntmesh.drain_resin", text="Place Suggested Drain", icon="MOD_BOOLEAN").suggested = True


CLASSES = (TNTMESH_PG_resin, TNTMESH_OT_hollow_resin, TNTMESH_OT_drain_resin, TNTMESH_PT_resin)
