# SPDX-License-Identifier: GPL-3.0-or-later
import bpy


class TNTMESH_PT_main(bpy.types.Panel):
    bl_label = "TNTMesh"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "TNTMesh"

    def draw(self, context: bpy.types.Context) -> None:
        self.layout.label(text="Import. Split. Connect. Print.")


CLASSES = (TNTMESH_PT_main,)
