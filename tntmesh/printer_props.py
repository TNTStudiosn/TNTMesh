# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import fields

import bpy
from bpy.props import EnumProperty, FloatProperty, FloatVectorProperty, StringProperty

from .printing import PrinterProfile

TECHNOLOGIES = (
    ("FDM", "FDM", "Filament printing"),
    ("RESIN", "Resin", "Photopolymer resin printing"),
)
PROFILE_FIELDS = tuple(field.name for field in fields(PrinterProfile))
VECTOR_FIELDS = {"build_mm", "margin_mm", "compensation_pct"}


class TNTMESH_PG_printer(bpy.types.PropertyGroup):
    manufacturer: StringProperty(name="Manufacturer", maxlen=128)
    model: StringProperty(name="Model", maxlen=128)
    technology: EnumProperty(name="Technology", items=TECHNOLOGIES)
    build_mm: FloatVectorProperty(
        name="Build volume (mm)", default=(220, 220, 250), min=0.01, subtype="XYZ",
    )
    margin_mm: FloatVectorProperty(
        name="Margin per side (mm)", default=(0, 0, 0), min=0, subtype="XYZ",
    )
    material: StringProperty(name="Material", maxlen=128)
    lateral_mm: FloatProperty(name="Per side (mm)", default=.15, min=0, precision=3)
    axial_mm: FloatProperty(name="Axial (mm)", default=.2, min=0, precision=3)
    min_wall_mm: FloatProperty(name="Min. wall (mm)", default=.8, min=.01, precision=3)
    compensation_pct: FloatVectorProperty(
        name="Compensation (%)", min=-99.99, subtype="XYZ",
    )
    density_g_cm3: FloatProperty(name="Density (g/cm³)", default=1.2, min=.01)
    price_per_kg: FloatProperty(name="Price per kg", min=0)

    def data(self) -> PrinterProfile:
        values = {name: getattr(self, name) for name in PROFILE_FIELDS}
        for name in VECTOR_FIELDS:
            values[name] = tuple(values[name])
        return PrinterProfile(**values)

    def set_data(self, profile: PrinterProfile) -> None:
        for name in PROFILE_FIELDS:
            setattr(self, name, getattr(profile, name))


def selected_printer(scene: bpy.types.Scene) -> TNTMESH_PG_printer | None:
    index = scene.tntmesh_printer_index
    return scene.tntmesh_printers[index] if index < len(scene.tntmesh_printers) else None
