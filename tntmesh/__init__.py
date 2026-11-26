# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import CollectionProperty, IntProperty, PointerProperty

from . import draft, draft_operators, draw_cut, localization, operators, ui, viewport
from .settings import TNTMESH_PG_settings

_CLASSES = (
    TNTMESH_PG_settings, *draft.CLASSES, *operators.CLASSES, *draft_operators.CLASSES,
    draw_cut.TNTMESH_OT_draw_plane, *ui.CLASSES,
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
        viewport.register()
    except Exception:
        unregister()
        raise


def unregister() -> None:
    draw_cut.cancel_sessions()
    viewport.unregister()
    for name in ("tntmesh_draft_index", "tntmesh_drafts", "tntmesh_settings"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    while _registered:
        bpy.utils.unregister_class(_registered.pop())
    localization.unregister()
