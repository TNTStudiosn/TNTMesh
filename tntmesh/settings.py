# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
)

from .geometry.connector import Connector
from .geometry.custom_connector import CustomConnector
from .geometry.planar import PlanarCut
from .geometry.volume import VolumeCut


def is_mesh(self, obj: bpy.types.Object) -> bool:
    return obj.type == "MESH"


class TNTMESH_PG_contour_point(bpy.types.PropertyGroup):
    position: FloatVectorProperty(name="Position (mm)", size=2, precision=2, subtype="XYZ")


class TNTMESH_PG_settings(bpy.types.PropertyGroup):
    mode: EnumProperty(
        name="Mode",
        items=[("EASY", "Easy", "Cut the selected model now"),
               ("DRAFT", "Draft", "Plan multiple cuts before generating pieces")],
        default="EASY",
    )
    cut_kind: EnumProperty(
        name="Cut type",
        items=[
            ("PLANAR", "Straight", "Split along a plane"),
            ("BEZIER", "Bézier Curve", "Split along a cubic Bézier profile"),
            ("RECTANGLE", "Rectangle", "Extract a rectangular region"),
            ("ELLIPSE", "Ellipse", "Extract an elliptical region"),
            ("POLYGON", "Contour", "Extract a drawn or freehand contour"),
            ("OBJECT", "Cutter Object", "Extract the region inside a closed mesh"),
        ],
        default="PLANAR",
    )
    cutter: PointerProperty(name="Cutter", type=bpy.types.Object, poll=is_mesh)
    axis: EnumProperty(
        name="Axis", description="World axis perpendicular to the cutting plane",
        items=[*((name, name, "") for name in "XYZ"), ("FREE", "Free", "Rotate the cutting plane")],
        default="Z",
    )
    rotation: FloatVectorProperty(
        name="Plane rotation", subtype="EULER", unit="ROTATION", size=3, precision=2,
        description="World rotation of the plane from its default Z orientation",
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
    show_build_volume: BoolProperty(name="Show print volume")
    connector: EnumProperty(
        name="Connector",
        items=[
            ("NONE", "None", "Create two pieces without a connector"),
            ("ROUND", "Cylindrical", "Add a round pin and matching socket"),
            ("HEX", "Hexagonal", "Add a hexagonal pin and matching socket"),
            ("CUSTOM", "Custom Mesh", "Use a shaped pin mesh and a matching socket cutter"),
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
    connector_count: IntProperty(name="Connector count", min=1, default=1, soft_max=12)
    loose_pins: BoolProperty(
        name="Separate pins", description="Cut two sockets and generate removable pins",
    )
    pin_template: PointerProperty(name="Pin template", type=bpy.types.Object, poll=is_mesh)
    socket_template: PointerProperty(name="Socket template", type=bpy.types.Object, poll=is_mesh)
    hide_source: BoolProperty(name="Hide input after split", default=True)
    scale_axis: EnumProperty(
        name="Reference axis", items=[(name, name, "") for name in "XYZ"], default="Z",
    )
    target_size: FloatProperty(name="Target size (mm)", default=50.0, min=0.01, precision=2)
    repair_weld: FloatProperty(
        name="Weld distance (mm)", description="Merge vertices within this distance on the copy",
        default=0.001, min=0.0, precision=4,
    )
    repair_holes: BoolProperty(
        name="Fill small holes", description="Attempt to cap simple boundary loops on the copy",
    )
    repair_hole_edges: IntProperty(name="Max. hole edges", min=3, max=64, default=8)
    profile_size: FloatVectorProperty(
        name="Size (mm)", description="Width, height and depth of the extraction volume",
        default=(10.0, 10.0, 10.0), min=0.01, precision=2, size=3, subtype="XYZ",
    )
    profile_shift: FloatVectorProperty(
        name="In-plane shift (mm)", default=(0.0, 0.0), precision=2, size=2, subtype="XYZ",
    )
    curve_controls: FloatVectorProperty(
        name="Control heights (mm)", default=(4.0, -4.0), precision=2, size=2, subtype="XYZ",
    )
    curve_samples: IntProperty(name="Curve samples", min=4, max=256, default=24)
    contour_depth: FloatProperty(name="Depth (mm)", default=10.0, min=0.01, precision=2)
    contour: CollectionProperty(type=TNTMESH_PG_contour_point)
    contour_index: IntProperty(min=0)

    def config(self) -> PlanarCut | VolumeCut:
        if self.cut_kind != "PLANAR":
            size = (1.0, 1.0, self.contour_depth) if self.cut_kind == "POLYGON" else tuple(self.profile_size)
            return VolumeCut(
                self.cut_kind, self.axis, tuple(self.rotation), self.offset,
                tuple(self.profile_shift), size, tuple(self.curve_controls),
                self.curve_samples, self.cutter, tuple(tuple(point.position) for point in self.contour),
            )
        connector = None
        if self.connector == "CUSTOM":
            connector = CustomConnector(self.pin_template, self.socket_template, self.wall)
        elif self.connector != "NONE":
            connector = Connector(
                self.connector, self.diameter, self.insertion, self.lateral, self.axial, self.wall,
                self.connector_count, self.loose_pins,
            )
        return PlanarCut(self.axis, self.offset, self.kerf, connector, tuple(self.rotation))
