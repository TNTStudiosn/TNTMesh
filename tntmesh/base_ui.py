# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

import bpy
from bpy.app.handlers import persistent
from mathutils import Vector

from .geometry.base import BaseAnalysis, analyze_base, contact_outline
from .geometry.mesh import bounds, evaluated_mm, inspect
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .operators import MeshOperator, active_mesh, report_failure


@dataclass(frozen=True)
class Preview:
    scene: int
    obj: int
    data: int
    band: float
    area: float
    unit: float
    origin: Vector
    analysis: BaseAnalysis


_preview: Preview | None = None
_handle = None


@persistent
def invalidate(_scene=None, depsgraph=None, *_args) -> None:
    global _preview
    if _preview is None:
        return
    if depsgraph is None or any(
        update.id.as_pointer() in {_preview.obj, _preview.data}
        and (update.is_updated_geometry or update.is_updated_transform)
        for update in depsgraph.updates
    ):
        _preview = None


class TNTMESH_OT_find_base_contacts(bpy.types.Operator, MeshOperator):
    bl_idname = "tntmesh.find_base_contacts"
    bl_label = "Find Base Contacts"
    bl_description = "Detect and highlight where the figure rises out of its base"
    bl_options = {"UNDO"}

    def execute(self, context: bpy.types.Context) -> set[str]:
        global _preview
        scene = context.scene
        obj = active_mesh(context)
        settings = scene.tntmesh_settings
        config = settings.base_config(obj)
        unit = millimeters_per_unit(scene)
        try:
            with GeometryTransaction() as transaction:
                mesh, origin = evaluated_mm(context, obj, transaction, unit)
                inspect(mesh)
                lower, _ = bounds(vertex.co for vertex in mesh.vertices)
                analysis = analyze_base(mesh, config)
            context.view_layer.update()
            if not analysis.contacts:
                raise MeshError("No closed base contacts were found. Adjust the search height.")
        except (MeshError, RuntimeError, ValueError) as error:
            _preview = None
            return report_failure(self, error)
        settings.base_contacts.clear()
        settings.base_contact_source = obj
        for contact in analysis.contacts:
            item = settings.base_contacts.add()
            item.center = tuple(contact.center)
            item.height = contact.center.z - lower.z
            local = config.for_contact(contact)
            item.shift = local.adjustment - config.adjustment
            original = next((entry for entry in config.overrides
                             if (Vector(entry.center) - contact.center).length <= .025), None)
            if original is not None:
                item.connector = original.connector
                item.diameter = original.diameter
        settings.base_contact_index = min(settings.base_contact_index, len(analysis.contacts) - 1)
        settings.show_plane = True
        _preview = Preview(scene.as_pointer(), obj.as_pointer(), obj.data.as_pointer(),
                           config.band, config.area, unit, origin, analysis)
        self.report({"INFO"}, tr("Found {count} base contact(s).").format(count=len(analysis.contacts)))
        return {"FINISHED"}


class TNTMESH_UL_base_contacts(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.label(text=tr("Contact at {height:.2f} mm").format(height=item.height),
                     translate=False, icon="SNAP_FACE")


def draw_contacts(layout: bpy.types.UILayout, settings) -> None:
    if not settings.base_contacts:
        return
    layout.template_list(
        "TNTMESH_UL_base_contacts", "", settings, "base_contacts",
        settings, "base_contact_index", rows=2,
    )
    if settings.base_contact_index < len(settings.base_contacts):
        contact = settings.base_contacts[settings.base_contact_index]
        layout.prop(contact, "shift")
        if settings.base_pins:
            layout.prop(contact, "connector")
            if contact.connector:
                layout.prop(contact, "diameter")


def draw() -> None:
    import gpu
    from gpu_extras.batch import batch_for_shader

    context = bpy.context
    scene = context.scene
    settings = scene.tntmesh_settings
    obj = active_mesh(context)
    preview = _preview
    if (preview is None or obj is None or context.mode != "OBJECT" or settings.mode != "EASY"
            or settings.cut_kind != "BASE" or not settings.show_plane):
        return
    config = settings.base_config(obj)
    if (scene.as_pointer(), obj.as_pointer(), config.band, config.area, millimeters_per_unit(scene)) != (
        preview.scene, preview.obj, preview.band, preview.area, preview.unit,
    ):
        return

    shader = gpu.shader.from_builtin("UNIFORM_COLOR")
    depth = gpu.state.depth_test_get()
    gpu.state.depth_test_set("NONE")
    try:
        for index, contact in enumerate(preview.analysis.contacts):
            local = config.for_contact(contact)
            try:
                outline = contact_outline(contact, local)
            except MeshError:
                continue
            vertices = [preview.origin + point / preview.unit for point in outline]
            tint = (0.0, 1.0, 1.0, 1.0) if index == settings.base_contact_index else (
                0.72, 0.54, 1.0, 1.0,
            )
            shader.bind()
            shader.uniform_float("color", tint)
            batch_for_shader(shader, "LINE_STRIP", {"pos": vertices + vertices[:1]}).draw(shader)
    finally:
        gpu.state.depth_test_set(depth)


def register() -> None:
    global _handle
    if not bpy.app.background:
        _handle = bpy.types.SpaceView3D.draw_handler_add(draw, (), "WINDOW", "POST_VIEW")
        bpy.app.handlers.depsgraph_update_post.append(invalidate)
        bpy.app.handlers.load_post.append(invalidate)


def unregister() -> None:
    global _handle
    if _handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle, "WINDOW")
        _handle = None
    for events in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.load_post):
        if invalidate in events:
            events.remove(invalidate)
    invalidate()


CLASSES = (TNTMESH_OT_find_base_contacts, TNTMESH_UL_base_contacts)
