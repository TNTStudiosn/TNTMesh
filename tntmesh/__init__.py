# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import CollectionProperty, IntProperty, PointerProperty

from . import (
    assembly,
    assembly_ui,
    assembly_view,
    base_ui,
    calibration_ui,
    diagnostics_ui,
    draft,
    draft_operators,
    draw_cut,
    localization,
    operators,
    printer_ui,
    ui,
    viewport,
)
from .printer_props import TNTMESH_PG_printer
from .settings import TNTMESH_PG_base_contact, TNTMESH_PG_contour_point, TNTMESH_PG_settings

_CLASSES = (
    TNTMESH_PG_contour_point, TNTMESH_PG_base_contact, TNTMESH_PG_settings,
    TNTMESH_PG_printer, *draft.CLASSES,
    assembly.TNTMESH_PG_assembly,
    *operators.CLASSES,
    *draft_operators.CLASSES,
    draw_cut.TNTMESH_OT_draw_plane, *ui.CLASSES, *printer_ui.CLASSES, *calibration_ui.CLASSES,
    *assembly_ui.CLASSES, *base_ui.CLASSES, *diagnostics_ui.CLASSES,
)
_registered: list[type] = []


def register() -> None:
    if _registered:
        return
    localization.register()
    try:
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            _registered.append(cls)
        bpy.types.Scene.tntmesh_settings = PointerProperty(type=TNTMESH_PG_settings)
        bpy.types.Scene.tntmesh_drafts = CollectionProperty(type=draft.TNTMESH_PG_draft_plan)
        bpy.types.Scene.tntmesh_draft_index = IntProperty(min=0)
        bpy.types.Scene.tntmesh_printers = CollectionProperty(type=TNTMESH_PG_printer)
        bpy.types.Scene.tntmesh_printer_index = IntProperty(min=0)
        bpy.types.Scene.tntmesh_assembly = PointerProperty(type=assembly.TNTMESH_PG_assembly)
        viewport.register()
        assembly_view.register()
        base_ui.register()
        diagnostics_ui.register()
    except Exception:
        unregister()
        raise


def unregister() -> None:
    draw_cut.cancel_sessions()
    diagnostics_ui.unregister()
    base_ui.unregister()
    assembly_view.unregister()
    viewport.unregister()
    for name in ("tntmesh_assembly", "tntmesh_printer_index", "tntmesh_printers", "tntmesh_draft_index",
                 "tntmesh_drafts", "tntmesh_settings"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    while _registered:
        bpy.utils.unregister_class(_registered.pop())
    localization.unregister()
