# SPDX-License-Identifier: GPL-3.0-or-later
import bpy

SPANISH = {
    "Import. Split. Connect. Print.": "Importa, divide, conecta e imprime.",
}
CATALOG = {
    locale: {("*", source): target for source, target in SPANISH.items()}
    for locale in ("es", "es_MX")
}


def register() -> None:
    bpy.app.translations.register(__package__, CATALOG)


def unregister() -> None:
    bpy.app.translations.unregister(__package__)
