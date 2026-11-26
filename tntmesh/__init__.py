# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import PointerProperty

from . import localization, operators, ui, viewport
from .settings import TNTMESH_PG_settings

_CLASSES = (TNTMESH_PG_settings, *operators.CLASSES, *ui.CLASSES)
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
        viewport.register()
    except Exception:
        unregister()
        raise


def unregister() -> None:
    viewport.unregister()
    if hasattr(bpy.types.Scene, "tntmesh_settings"):
        del bpy.types.Scene.tntmesh_settings
    while _registered:
        bpy.utils.unregister_class(_registered.pop())
    localization.unregister()
