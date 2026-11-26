# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

from . import localization, ui

_CLASSES = (*ui.CLASSES,)
_registered: list[type] = []


def register() -> None:
    localization.register()
    try:
        for cls in _CLASSES:
            bpy.utils.register_class(cls)
            _registered.append(cls)
    except Exception:
        unregister()
        raise


def unregister() -> None:
    while _registered:
        bpy.utils.unregister_class(_registered.pop())
    localization.unregister()
