# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty

from .geometry.connector import Connector
from .geometry.planar import PlanarCut


class TNTMESH_PG_settings(bpy.types.PropertyGroup):
    axis: EnumProperty(
        name="Axis", description="World axis perpendicular to the cutting plane",
        items=[(name, name, "") for name in "XYZ"], default="Z",
    )
    offset: FloatProperty(
        name="Offset (mm)", description="Distance from the center along the cut axis",
        precision=2, step=25,
    )
    kerf: FloatProperty(
        name="Kerf (mm)", description="Physical gap removed between the pieces",
        min=0.0, precision=3, step=5,
    )
    show_plane: BoolProperty(name="Show plane", default=True)
    connector: EnumProperty(
        name="Connector",
        items=[
            ("NONE", "None", "Create two pieces without a connector"),
            ("ROUND", "Cylindrical", "Add a round pin and matching socket"),
            ("HEX", "Hexagonal", "Add a hexagonal pin and matching socket"),
        ],
        default="ROUND",
    )
    diameter: FloatProperty(
        name="Diameter (mm)", description="Pin diameter measured across opposite vertices",
        default=5.0, min=0.01, precision=2,
    )
    insertion: FloatProperty(
        name="Insertion (mm)", description="Length of the pin inside the matching piece",
        default=4.0, min=0.01, precision=2,
    )
    lateral: FloatProperty(
        name="Per side (mm)", description="Clearance from each side of the pin to the socket wall",
        default=0.15, min=0.0, precision=3, step=5,
    )
    axial: FloatProperty(
        name="Axial (mm)", description="Additional clearance at the bottom of the socket",
        default=0.2, min=0.0, precision=3, step=5,
    )
    wall: FloatProperty(
        name="Min. wall (mm)", description="Minimum material around the socket and pin root",
        default=0.8, min=0.01, precision=2,
    )
    hide_source: BoolProperty(name="Hide input after split", default=True)
    scale_axis: EnumProperty(
        name="Reference axis", items=[(name, name, "") for name in "XYZ"], default="Z",
    )
    target_size: FloatProperty(name="Target size (mm)", default=50.0, min=0.01, precision=2)

    def config(self) -> PlanarCut:
        connector = None
        if self.connector != "NONE":
            connector = Connector(
                self.connector, self.diameter, self.insertion, self.lateral, self.axial, self.wall
            )
        return PlanarCut(self.axis, self.offset, self.kerf, connector)
