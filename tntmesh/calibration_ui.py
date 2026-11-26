# SPDX-License-Identifier: GPL-3.0-or-later
from uuid import uuid4

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from mathutils import Matrix

from .geometry import calibration
from .geometry.connector import Connector
from .localization import tr
from .model import (
    ROLE,
    GeometryTransaction,
    MeshError,
    identify_part,
    millimeters_per_unit,
    owned_collection,
)
from .operators import active_mesh, report_failure, select_results
from .printer_props import selected_printer

CALIBRATION = "tntmesh_calibration"
CLEARANCE = "tntmesh_clearance_mm"
MATERIAL = "tntmesh_calibration_material"


class TNTMESH_OT_calibrate_connectors(bpy.types.Operator):
    bl_idname = "tntmesh.calibrate_connectors"
    bl_label = "Calibrate Connectors"
    bl_description = "Make a reusable test pin and labeled sockets with different clearances"
    bl_options = {"UNDO"}

    shape: EnumProperty(name="Connector", items=[
        ("ROUND", "Cylindrical", ""), ("HEX", "Hexagonal", ""),
    ])
    diameter: FloatProperty(name="Diameter (mm)", default=5, min=0.01, max=100, precision=3)
    insertion: FloatProperty(name="Insertion (mm)", default=4, min=0.01, max=100, precision=3)
    axial: FloatProperty(name="Axial (mm)", default=0.2, min=0, max=10, precision=3)
    wall: FloatProperty(name="Min. wall (mm)", default=1.2, min=0.1, max=20, precision=2)
    material: StringProperty(name="Material", maxlen=128)
    start: FloatProperty(name="Start clearance (mm)", default=0.05, min=0, max=10, precision=3)
    end: FloatProperty(name="End clearance (mm)", default=0.4, min=0, max=10, precision=3)
    sampling: EnumProperty(name="Spacing", items=[
        ("STEP", "Increment", ""), ("COUNT", "Sample count", ""),
    ])
    step: FloatProperty(name="Increment (mm)", default=0.05, min=0.001, max=10, precision=3)
    count: IntProperty(name="Sample count", default=8, min=1, max=calibration.MAX_SAMPLES)
    engraved: BoolProperty(name="Engrave clearances", default=True)

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return context.mode == "OBJECT"

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        profile = selected_printer(context.scene)
        settings = context.scene.tntmesh_settings
        self.shape = "HEX" if settings.connector == "HEX" else "ROUND"
        self.diameter = min(100, settings.diameter)
        self.insertion = min(100, settings.insertion)
        self.axial = min(10, profile.axial_mm if profile else settings.axial)
        self.wall = min(20, profile.min_wall_mm if profile else self.wall)
        self.material = profile.material if profile else ""
        return context.window_manager.invoke_props_dialog(self, width=360)

    def clearances(self) -> list[int]:
        return calibration.clearance_range(
            self.start, self.end, step=self.step if self.sampling == "STEP" else None,
            count=self.count,
        )

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        layout.use_property_split = True
        for name in ("shape", "diameter", "insertion", "axial", "wall", "material"):
            layout.prop(self, name)
        layout.separator()
        layout.prop(self, "sampling")
        layout.prop(self, "start")
        if self.sampling != "COUNT" or self.count != 1:
            layout.prop(self, "end")
        layout.prop(self, "step" if self.sampling == "STEP" else "count")
        layout.prop(self, "engraved")
        try:
            clearances = self.clearances()
        except MeshError as error:
            layout.label(text=tr(str(error)), translate=False, icon="ERROR")
        else:
            layout.label(text=tr("{count} sockets and one pin").format(count=len(clearances)),
                         translate=False, icon="INFO")

    def execute(self, context: bpy.types.Context) -> set[str]:
        scene = context.scene
        unit = millimeters_per_unit(scene)
        settings = Connector(self.shape, self.diameter, self.insertion, axial=self.axial, wall=self.wall)
        wm = context.window_manager
        wm.progress_begin(0, 2)
        try:
            clearances = self.clearances()
            with GeometryTransaction() as transaction:
                coupons = calibration.generate(context, transaction, settings, clearances, self.engraved)
                wm.progress_update(1)
                collection = owned_collection(scene, "calibration")
                project_id = uuid4().hex
                cursor = scene.cursor.location
                results = []
                for coupon in coupons:
                    coupon.mesh.transform(Matrix.Scale(1 / unit, 4))
                    coupon.mesh.update()
                    label = (
                        tr("Test pin") if coupon.clearance is None else
                        tr("Socket {clearance:.3f} mm").format(clearance=coupon.clearance)
                    )
                    obj = transaction.object(collection, label, coupon.mesh)
                    obj.location = coupon.position_mm / unit
                    obj.location.x += cursor.x
                    obj.location.y += cursor.y
                    identify_part(obj, project_id)
                    obj[CALIBRATION] = "PIN" if coupon.clearance is None else "SOCKET"
                    obj[MATERIAL] = self.material
                    if coupon.clearance is not None:
                        obj[CLEARANCE] = coupon.clearance
                    results.append(obj)
                for obj in results:
                    transaction.publish(obj)
            context.view_layer.update()
            select_results(context, results)
            scene.tntmesh_settings.show_plane = False
            wm.progress_update(2)
        except (MeshError, RuntimeError, ValueError) as error:
            return report_failure(self, error)
        finally:
            wm.progress_end()
            context.view_layer.update()
        self.report({"INFO"}, tr("Created a calibration pin and {count} sockets.").format(
            count=len(clearances),
        ))
        return {"FINISHED"}


def chosen_clearance(context: bpy.types.Context) -> float | None:
    obj = active_mesh(context)
    if obj is not None and obj.get(CALIBRATION) == "SOCKET" and obj.get(ROLE) == "part":
        value = obj.get(CLEARANCE)
        if isinstance(value, (int, float)) and 0 <= value <= 10:
            return float(value)
    return None


class TNTMESH_OT_save_calibrated_clearance(bpy.types.Operator):
    bl_idname = "tntmesh.save_calibrated_clearance"
    bl_label = "Save Clearance to Profile"
    bl_description = "Set the selected printer profile's clearance to the active socket value"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context: bpy.types.Context) -> bool:
        return (context.mode == "OBJECT" and selected_printer(context.scene) is not None
                and chosen_clearance(context) is not None)

    def execute(self, context: bpy.types.Context) -> set[str]:
        profile = selected_printer(context.scene)
        previous = profile.lateral_mm
        profile.lateral_mm = chosen_clearance(context)
        try:
            profile.data().validate()
        except MeshError as error:
            profile.lateral_mm = previous
            return report_failure(self, error)
        self.report({"INFO"}, tr("Saved {clearance:.3f} mm per side to the printer profile.").format(
            clearance=profile.lateral_mm,
        ))
        return {"FINISHED"}


CLASSES = (TNTMESH_OT_calibrate_connectors, TNTMESH_OT_save_calibrated_clearance)
