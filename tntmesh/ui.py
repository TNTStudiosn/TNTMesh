# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from .operators import active_mesh, managed_parts


class TNTMESH_PT_main(bpy.types.Panel):
    bl_label = "TNTMesh"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.tntmesh_settings
        obj = active_mesh(context)
        if context.mode != "OBJECT":
            layout.label(text="Switch to Object Mode to use TNTMesh.", icon="INFO")
            return

        layout.operator("tntmesh.import_stl", icon="IMPORT")
        if obj is None:
            layout.label(text="Select a mesh or import an STL.", icon="INFO")
        else:
            layout.label(text=obj.name, icon="MESH_DATA", translate=False)
            header, body = layout.panel("tntmesh_scale", default_closed=True)
            header.label(text="Scale", icon="FULLSCREEN_ENTER")
            if body:
                body.row(align=True).prop(settings, "scale_axis", expand=True)
                body.prop(settings, "target_size")
                if context.scene.unit_settings.system == "NONE":
                    body.label(text="Without scene units, 1 BU = 1 mm.", icon="INFO")
                body.operator("tntmesh.resize")

            layout.separator()
            cut = layout.box()
            cut.label(text="Split", icon="MOD_BOOLEAN")
            cut.row(align=True).prop(settings, "axis", expand=True)
            cut.prop(settings, "offset")
            cut.prop(settings, "show_plane")
            cut.label(text="Connector")
            cut.prop(settings, "connector", text="")

            header, body = layout.panel("tntmesh_cut_settings", default_closed=True)
            header.label(text="Cut settings")
            if body:
                body.prop(settings, "kerf")
                body.prop(settings, "hide_source")
                if settings.connector != "NONE":
                    for prop in ("diameter", "insertion", "lateral", "axial", "wall"):
                        body.prop(settings, prop)

            action = layout.row()
            action.scale_y = 1.45
            action.operator("tntmesh.split", icon="CHECKMARK")
            layout.operator("tntmesh.validate", icon="VIEWZOOM")

        if managed_parts(context, "ALL"):
            layout.separator()
            layout.operator("tntmesh.export_stl", icon="EXPORT")


CLASSES = (TNTMESH_PT_main,)
