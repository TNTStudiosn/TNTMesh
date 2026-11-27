# SPDX-License-Identifier: GPL-3.0-or-later
from math import degrees, tau
from pathlib import Path

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Matrix, Vector

from . import assembly, assembly_guide, assembly_history
from .geometry.mesh import evaluated_mm, inspect
from .localization import tr
from .model import (
    DRAFT_ID,
    HINGE_AXIS,
    HINGE_OPENING,
    HINGE_PIVOT,
    PROJECT_ID,
    GeometryTransaction,
    MeshError,
    identify_part,
    millimeters_per_unit,
    owned_collection,
)
from .operators import report_failure, select_results
from .viewport import project_bounds


class TNTMESH_OT_assembly_project(bpy.types.Operator):
    bl_idname = "tntmesh.assembly_project"
    bl_label = "Use Selected Project"
    bl_description = "Show the project that owns the selected generated piece"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        obj = context.active_object
        return obj is not None and assembly.belongs(obj, obj.get(PROJECT_ID, ""))

    def execute(self, context: bpy.types.Context) -> set[str]:
        state = context.scene.tntmesh_assembly
        obj = context.active_object
        state.project = obj[PROJECT_ID]
        state.index = context.scene.objects.find(obj.name)
        state.hinge_fraction = 0
        return {"FINISHED"}


class TNTMESH_OT_assembly_action(bpy.types.Operator):
    bl_idname = "tntmesh.assembly_action"
    bl_label = "Manage Piece"
    bl_options = {"UNDO", "INTERNAL"}

    action: EnumProperty(items=[
        ("SELECT", "Select Piece", ""),
        ("FOCUS", "Focus Piece", ""),
        ("HIDE", "Toggle Piece Visibility", ""),
        ("ISOLATE", "Isolate in Project", ""),
        ("SHOW_ALL", "Show Project Pieces", ""),
        ("MEASURE", "Measure Piece", ""),
        ("DUPLICATE", "Duplicate Piece", ""),
        ("DELETE", "Delete Generated Piece", ""),
        ("RESET", "Back to Assembly", ""),
    ])

    @classmethod
    def description(cls, context, properties) -> str:
        return tr(cls.bl_rna.properties["action"].enum_items[properties.action].name)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and assembly.current_member(context) is not None

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if self.action == "DELETE":
            return context.window_manager.invoke_confirm(self, event)
        return self.execute(context)

    def execute(self, context: bpy.types.Context) -> set[str]:
        obj = assembly.current_member(context)
        state = context.scene.tntmesh_assembly
        state.project = obj[PROJECT_ID]
        if self.action == "RESET":
            state.distance = 0
            state.hinge_fraction = 0
        elif self.action in {"SELECT", "FOCUS"}:
            region = None
            if self.action == "FOCUS":
                area = context.area
                if area is None or area.type != "VIEW_3D":
                    return report_failure(self, MeshError("Open the 3D Viewport to focus the piece."))
                region = next((item for item in area.regions if item.type == "WINDOW"), None)
                if region is None:
                    return report_failure(self, MeshError("Open the 3D Viewport to focus the piece."))
            obj.hide_set(False)
            select_results(context, [obj])
            if region is not None:
                with context.temp_override(region=region):
                    bpy.ops.view3d.view_selected()
        elif self.action == "HIDE":
            obj.hide_set(not obj.hide_get())
        elif self.action == "ISOLATE":
            for piece in assembly.members(context):
                piece.hide_set(piece != obj)
            select_results(context, [obj])
        elif self.action == "SHOW_ALL":
            for piece in assembly.members(context):
                piece.hide_set(False)
        else:
            try:
                if self.action == "MEASURE":
                    self.measure(context, obj)
                elif self.action == "DUPLICATE":
                    self.duplicate(context, obj)
                elif self.action == "DELETE":
                    self.delete(obj)
            except (MeshError, ValueError, RuntimeError) as error:
                return report_failure(self, error)
        return {"FINISHED"}

    def measure(self, context: bpy.types.Context, obj: bpy.types.Object) -> None:
        unit = millimeters_per_unit(context.scene)
        with GeometryTransaction() as transaction:
            mesh, _ = evaluated_mm(context, obj, transaction, unit)
            result = inspect(mesh)
        self.report({"INFO"}, tr("Closed mesh · {volume:.2f} mm³ · {shells} shell(s)").format(
            volume=result.volume_mm3, shells=result.shells,
        ))

    def duplicate(self, context: bpy.types.Context, source: bpy.types.Object) -> None:
        scene = context.scene
        unit = millimeters_per_unit(scene)
        with GeometryTransaction() as transaction:
            obj = source.copy()
            transaction.objects.append(obj)
            obj.data = transaction.own_mesh(source.data.copy())
            collection = owned_collection(scene, "part")
            collection.objects.link(obj)
            if DRAFT_ID in obj:
                del obj[DRAFT_ID]
            if assembly_history.PARENT_PART in obj:
                del obj[assembly_history.PARENT_PART]
            for key in (HINGE_AXIS, HINGE_OPENING, HINGE_PIVOT):
                if key in obj.data:
                    del obj.data[key]
            assembly_history.set_path(obj, ())
            world = source.matrix_world.copy()
            world.translation.x += max(source.dimensions.x, 1 / unit) + 2 / unit
            obj.matrix_world = world
            identify_part(obj, source[PROJECT_ID])
            transaction.publish(obj)
        context.view_layer.update()
        obj.hide_set(False)
        select_results(context, [obj])
        scene.tntmesh_assembly.index = scene.objects.find(obj.name)

    def delete(self, obj: bpy.types.Object) -> None:
        if len(obj.users_scene) != 1 or obj.library is not None:
            raise MeshError("This piece is shared with another scene or library.")
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh.users == 0 and mesh.library is None:
            bpy.data.meshes.remove(mesh)


class TNTMESH_OT_check_assembly(bpy.types.Operator):
    bl_idname = "tntmesh.check_assembly"
    bl_label = "Check Assembly"
    bl_description = "Check whether project pieces overlap in the assembled position"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and len(assembly.members(context)) > 1

    def execute(self, context: bpy.types.Context) -> set[str]:
        try:
            conflicts = assembly.overlaps(context, assembly.members(context))
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            context.view_layer.update()
        if conflicts:
            first, second, volume = conflicts[0]
            message = tr("{count} overlap(s). {first} and {second}: {volume:.3f} mm³").format(
                count=len(conflicts), first=first.name, second=second.name, volume=volume,
            )
            self.report({"WARNING"}, message)
        else:
            self.report({"INFO"}, tr("No volume overlaps at the assembled position."))
        return {"FINISHED"}


class TNTMESH_UL_assembly_parts(bpy.types.UIList):
    def filter_items(self, context, data, propname):
        project = assembly.project_id(context)
        layer = context.view_layer.objects
        flags = [self.bitflag_filter_item if assembly.belongs(obj, project) and obj.name in layer
                 else 0 for obj in getattr(data, propname)]
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        row = layout.row(align=True)
        row.label(text="", icon="HIDE_ON" if item.hide_get() else "MESH_DATA")
        row.prop(item, "name", text="", emboss=False)


class TNTMESH_OT_check_insertion(bpy.types.Operator):
    bl_idname = "tntmesh.check_insertion"
    bl_label = "Check Insertion Path"
    bl_description = "Test the selected piece for collisions along an insertion path"

    axis: EnumProperty(name="Start from", items=[
        ("AUTO", "Assembly Direction", "Use the piece's suggested separation direction"),
        *((axis, axis, "") for axis in ("+X", "-X", "+Y", "-Y", "+Z", "-Z")),
    ])
    distance: FloatProperty(name="Travel distance (mm)", default=25, min=0, max=10000, precision=2)
    rotation: FloatProperty(
        name="Starting angle", subtype="ANGLE", min=-tau, max=tau,
        description="Angle at the start of insertion relative to the assembled pose",
    )
    rotation_axis: EnumProperty(name="Rotation axis", items=(
        ("Z", "World Z", "Rotate around the world Z axis"),
        ("X", "World X", "Rotate around the world X axis"),
        ("Y", "World Y", "Rotate around the world Y axis"),
        ("TRAVEL", "Travel Direction", "Rotate around the direction of travel"),
    ))
    rotation_pivot: EnumProperty(name="Rotation pivot", items=(
        ("CENTER", "Piece Center", "Rotate around the center of the piece's bounds"),
        ("ORIGIN", "Object Origin", "Rotate around the object's origin"),
        ("CURSOR", "3D Cursor", "Rotate around the 3D cursor"),
    ))
    sample_mm: FloatProperty(name="Sample travel (mm)", default=.25, min=.05, max=10, precision=2,
                             description="Maximum estimated movement between tested poses")
    steps: IntProperty(default=1, min=1, max=150, options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and len(assembly.members(context)) > 1

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        moving = assembly.current_member(context)
        if moving is not None and self.axis == "AUTO" and not self.properties.is_property_set("distance"):
            direction = assembly.slide_direction(moving, context.evaluated_depsgraph_get())
            if direction is not None:
                self.distance = assembly.slide_travel(context, moving, assembly.members(context), direction)
        return context.window_manager.invoke_props_dialog(self, width=345)

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        obj = assembly.current_member(context)
        if obj is not None:
            layout.label(text=obj.name, icon="MESH_DATA", translate=False)
        layout.use_property_split = True
        for prop in ("axis", "distance", "rotation"):
            layout.prop(self, prop)
        if self.rotation:
            for prop in ("rotation_axis", "rotation_pivot", "sample_mm"):
                layout.prop(self, prop)
            layout.label(text="Rotating paths are sampled.", icon="INFO")

    def execute(self, context: bpy.types.Context) -> set[str]:
        moving = assembly.current_member(context)
        pieces = assembly.members(context)
        if moving is None or len(pieces) < 2:
            return {"CANCELLED"}
        if self.axis == "AUTO":
            direction = next(offset for obj, _, offset in assembly.explosion_offsets(
                pieces, context.evaluated_depsgraph_get(), 1,
            ) if obj == moving)
        else:
            direction = Vector((0, 0, 0))
            direction["XYZ".index(self.axis[1])] = 1 if self.axis[0] == "+" else -1
        rotation_axis, pivot = None, None
        if self.rotation:
            rotation_axis = direction if self.rotation_axis == "TRAVEL" else Vector((
                float(self.rotation_axis == "X"), float(self.rotation_axis == "Y"), float(self.rotation_axis == "Z"),
            ))
            if self.rotation_pivot == "ORIGIN":
                pivot = moving.matrix_world.translation
            elif self.rotation_pivot == "CURSOR":
                pivot = context.scene.cursor.location
        try:
            hit = assembly.insertion_hit(context, moving, pieces, direction, self.distance, self.steps,
                                         rotation_axis=rotation_axis, rotation_radians=self.rotation,
                                         pivot_world=pivot, sample_mm=self.sample_mm)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        if hit is not None:
            message = ("Blocked by {name} at {distance:.2f} mm and {angle:.1f}°." if self.rotation
                       else "Blocked by {name} at {distance:.2f} mm.")
            self.report({"WARNING"}, tr(message).format(name=hit.obstacle.name, distance=hit.distance_mm,
                                                       angle=degrees(hit.rotation_radians)))
        elif self.rotation:
            self.report({"INFO"}, tr("No overlap found at the sampled poses."))
        else:
            self.report({"INFO"}, tr("No overlap found along the insertion path."))
        return {"FINISHED"}


class TNTMESH_OT_check_hinge(bpy.types.Operator):
    bl_idname = "tntmesh.check_hinge"
    bl_label = "Check Hinge Opening"
    bl_description = "Check the current assembly for obstructions around the recorded hinge axis"

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and assembly.hinge_motion(context) is not None

    def execute(self, context: bpy.types.Context) -> set[str]:
        motion = assembly.hinge_motion(context)
        if motion is None:
            return {"CANCELLED"}
        try:
            hit = assembly.insertion_hit(
                context, motion.moving, assembly.members(context), Vector((0, 0, 0)), 0,
                rotation_axis=motion.axis, rotation_radians=motion.opening, pivot_world=motion.pivot, sample_mm=1,
            )
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        state = context.scene.tntmesh_assembly
        if hit is not None:
            state.hinge_fraction = hit.rotation_radians / motion.opening
            state.hinge_blocker = hit.obstacle.name
            self.report({"WARNING"}, tr("Hinge blocked by {name} near {angle:.1f}°.").format(
                name=hit.obstacle.name, angle=degrees(hit.rotation_radians),
            ))
            return {"CANCELLED"}
        state.hinge_blocker = ""
        self.report({"INFO"}, tr("No overlap found at the sampled poses."))
        return {"FINISHED"}


class TNTMESH_OT_export_assembly_guide(bpy.types.Operator):
    bl_idname = "tntmesh.export_assembly_guide"
    bl_label = "Export Guide"
    bl_description = "Save numbered assembly views and a suggested assembly order"

    directory: StringProperty(subtype="DIR_PATH")
    guide_title: StringProperty(name="Title", maxlen=120)
    file_format: EnumProperty(
        name="Format",
        items=[
            ("HTML", "HTML and PNG", "Create a guide to open in a browser and two PNG images"),
            ("MARKDOWN", "Markdown and PNG", "Create an editable Markdown guide and two PNG images"),
            ("PNG", "PNG images", "Save the numbered assembled and exploded views"),
            ("ALL", "HTML, Markdown and PNG", "Save both documents and the numbered views"),
        ],
        default="HTML",
    )
    explosion: FloatProperty(
        name="Separation (mm)", description="Set the explosion distance. Use zero for automatic spacing",
        default=0, min=0, soft_max=100, max=10000, precision=2,
    )

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT" and bool(assembly.members(context))

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        if bpy.data.filepath and not self.directory:
            self.directory = str(Path(bpy.data.filepath).parent)
        if not self.properties.is_property_set("explosion"):
            self.explosion = context.scene.tntmesh_assembly.distance
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.prop(self, "guide_title")
        layout.prop(self, "file_format")
        layout.separator()
        layout.label(text=tr("Separation (mm)"), translate=False)
        layout.prop(self, "explosion", text="")

    def execute(self, context: bpy.types.Context) -> set[str]:
        destination = Path(self.directory)
        if not self.directory or not destination.is_dir():
            return report_failure(self, MeshError("Choose an existing destination folder."))
        pieces = assembly.members(context)
        if not pieces:
            return report_failure(self, MeshError("Select a generated piece to open its assembly."))
        wm = context.window_manager
        wm.progress_begin(0, 1)
        try:
            folder = assembly_guide.export(
                context, pieces, destination, self.guide_title, self.file_format, self.explosion,
            )
            wm.progress_update(1)
        except (MeshError, OSError, RuntimeError, ValueError, OverflowError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
        self.report({"INFO"}, tr("Saved the assembly guide in {folder}.").format(folder=folder.name))
        return {"FINISHED"}


class TNTMESH_PT_assembly(bpy.types.Panel):
    bl_label = "Assembly"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        scene = context.scene
        state = scene.tntmesh_assembly
        project = assembly.project_id(context)
        selected = context.active_object
        if selected is not None and assembly.belongs(selected, selected.get(PROJECT_ID, "")):
            if not state.project or selected.get(PROJECT_ID) != project:
                layout.operator("tntmesh.assembly_project", icon="FILE_FOLDER")
        pieces = assembly.members(context)
        if not pieces:
            layout.label(text="Select a generated piece to open its assembly.", icon="INFO")
            return
        layout.template_list(
            "TNTMESH_UL_assembly_parts", "", scene, "objects", state, "index", rows=3,
        )
        obj = assembly.current_member(context)
        if obj is not None:
            row = layout.row(align=True)
            for action, icon in (
                ("SELECT", "RESTRICT_SELECT_OFF"), ("HIDE", "HIDE_ON"),
                ("ISOLATE", "SOLO_ON"), ("SHOW_ALL", "HIDE_OFF"), ("FOCUS", "VIEWZOOM"),
            ):
                row.operator("tntmesh.assembly_action", text="", icon=icon).action = action
            extents = project_bounds(obj, context.evaluated_depsgraph_get(), Matrix.Identity(3))
            if extents is not None:
                size = (extents[1] - extents[0]) * millimeters_per_unit(scene)
                layout.label(text=" × ".join(f"{axis:.1f}" for axis in size) + " mm", translate=False)

        if len(pieces) > 1:
            motion = assembly.hinge_motion(context)
            explosion = layout.row()
            previewing = motion is not None and (state.hinge_fraction > 0 or bool(state.hinge_blocker))
            explosion.enabled = not previewing
            explosion.prop(state, "distance")
            if motion is not None:
                angle = degrees(motion.opening * state.hinge_fraction)
                layout.prop(state, "hinge_fraction", slider=True, translate=False,
                            text=tr("Opening · {angle:.0f}°").format(angle=angle))
                layout.operator("tntmesh.check_hinge", icon="CON_ROTLIKE")
            if state.distance > 0 or previewing:
                layout.operator("tntmesh.assembly_action", text="Back to Assembly", icon="LOOP_BACK").action = "RESET"
            layout.operator("tntmesh.check_assembly", icon="VIEWZOOM")
            layout.operator("tntmesh.check_insertion", icon="PLAY")
            if any(branch.connector == "PRESS_FIT" for part in pieces for branch in assembly_history.path(part)):
                notice = layout.column(align=True)
                notice.label(text="Rigid checks include press-fit contact.", icon="INFO")
        layout.operator("tntmesh.export_assembly_guide", text="Export Assembly Guide", icon="FILE_TEXT")

        if obj is not None:
            header, body = layout.panel("tntmesh_assembly_details", default_closed=True)
            header.label(text="Piece settings")
            if body:
                body.prop(obj, "color", text="Preview color")
                body.operator("tntmesh.assembly_action", text="Measure Piece").action = "MEASURE"
                body.operator("tntmesh.assembly_action", text="Duplicate Piece", icon="DUPLICATE").action = "DUPLICATE"
                body.operator("tntmesh.assembly_action", text="Delete Generated Piece", icon="X").action = "DELETE"


CLASSES = (TNTMESH_OT_assembly_project, TNTMESH_OT_assembly_action,
           TNTMESH_OT_check_assembly, TNTMESH_OT_check_insertion, TNTMESH_OT_check_hinge, TNTMESH_UL_assembly_parts,
           TNTMESH_OT_export_assembly_guide, TNTMESH_PT_assembly)
