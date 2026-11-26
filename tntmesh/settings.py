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
    StringProperty,
)

from .geometry.base import BaseCut, ContactOverride
from .geometry.connector import Connector
from .geometry.custom_connector import CustomConnector
from .geometry.planar import PlanarCut
from .geometry.region import RegionCut
from .geometry.symmetry import SymmetricCut
from .geometry.volume import Cut, VolumeCut


def is_mesh(self, obj: bpy.types.Object) -> bool:
    return obj.type == "MESH"


class TNTMESH_PG_contour_point(bpy.types.PropertyGroup):
    position: FloatVectorProperty(name="Position (mm)", size=2, precision=2, subtype="XYZ")

class TNTMESH_PG_base_contact(bpy.types.PropertyGroup):
    center: FloatVectorProperty(size=3)
    height: FloatProperty()
    shift: FloatProperty(name="Contact shift (mm)", precision=3)
    connector: BoolProperty(name="Add connector", default=True)
    diameter: FloatProperty(
        name="Pin diameter (mm)", description="Enter zero to keep the common diameter",
        min=0, precision=3,
    )



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
            ("REGION", "Surface Region", "Extract a solid piece from matching faces"),
            ("SYMMETRY", "Symmetric Cuts", "Reflect a straight cut across a symmetry plane"),
            ("BASE", "Separate Base", "Find rising contacts and cut the figure from its base"),
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
    region_method: EnumProperty(name="Region source", items=[
        ("MATERIAL", "By Material Slot", "Use faces assigned to a material slot"),
        ("SELECTION", "Selected Faces", "Use the face selection saved on the mesh"),
        ("FACE_MASK", "Face Mask", "Use a Boolean attribute on the face domain"),
        ("VERTEX_GROUP", "Vertex Group", "Use faces whose vertices reach the group weight"),
        ("COLOR", "Color Attribute", "Match all face colors within the given RGB tolerance"),
    ])
    region_depth: FloatProperty(name="Depth (mm)", default=2, min=.01, precision=3)
    region_slot: IntProperty(name="Source material slot", default=1, min=1)
    region_attribute: StringProperty(name="Name")
    region_color: FloatVectorProperty(
        name="Target color", default=(1.0, 0.0, 0.0), min=0, max=1, size=3, subtype="COLOR",
    )
    region_tolerance: FloatProperty(name="RGB tolerance", default=.05, min=0, max=1, precision=3)
    region_weight: FloatProperty(name="Minimum weight", default=.5, min=.001, max=1, precision=3)
    region_grow: IntProperty(
        name="Grow / shrink", description="Add or remove rings of edge-adjacent faces",
        default=0, min=-50, max=50,
    )
    region_smoothing: IntProperty(
        name="Boundary smoothing", description="Relax the cut contour along the original surface",
        default=0, min=0, max=12,
    )
    region_connector: EnumProperty(
        name="Connector",
        items=[
            ("NONE", "None", "Extract the region without a connector"),
            ("ROUND", "Cylindrical", "Find a matching pin position inside the region seam"),
            ("HEX", "Hexagonal", "Find a matching hexagonal pin position inside the region seam"),
        ],
        default="NONE",
    )
    symmetry_axis: EnumProperty(
        name="Symmetry axis", items=[(name, name, "") for name in "XYZ"], default="X",
    )
    symmetry_center: FloatProperty(
        name="Center shift (mm)", description="Shift the symmetry plane from the model center",
        precision=3,
    )
    symmetry_secondary: FloatProperty(
        name="Second cut shift (mm)", description="Shift the reflected cut along its own normal",
        precision=3,
    )
    symmetry_rotation: FloatVectorProperty(
        name="Second cut rotation", description="Rotate the reflected cut in its local axes",
        subtype="EULER", unit="ROTATION", size=3,
    )
    base_band: FloatProperty(
        name="Search height (mm)", description="Height above the model bottom to search, or zero for automatic",
        min=0, default=0, precision=2,
    )
    base_area: FloatProperty(name="Min. contact (mm²)", min=.01, default=.5, precision=2)
    base_margin: FloatProperty(name="Contact margin (mm)", min=0, default=.05, precision=3)
    base_adjustment: FloatProperty(name="Contact shift (mm)", precision=3)
    base_pins: BoolProperty(name="Connect the contacts")
    base_shape: EnumProperty(name="Connector", items=[
        ("ROUND", "Cylindrical", ""), ("HEX", "Hexagonal", ""),
    ])
    base_contacts: CollectionProperty(type=TNTMESH_PG_base_contact)
    base_contact_index: IntProperty(min=0)
    base_contact_source: PointerProperty(type=bpy.types.Object, poll=is_mesh)

    def region_config(self) -> RegionCut:
        connector = None if self.region_connector == "NONE" else self.standard_connector(
            self.region_connector, self.connector_count,
        )
        return RegionCut(
            self.region_method, self.region_depth, self.region_slot, self.region_attribute,
            tuple(self.region_color), self.region_tolerance, self.region_weight, self.region_grow,
            self.region_smoothing, connector,
        )

    def standard_connector(self, shape: str, count: int) -> Connector:
        return Connector(shape, self.diameter, self.insertion, self.lateral, self.axial,
                         self.wall, count, self.loose_pins)

    def base_config(self, source: bpy.types.Object | None = None) -> BaseCut:
        connector = None
        if self.base_pins:
            connector = self.standard_connector(self.base_shape, 1)
        items = self.base_contacts if source is None or self.base_contact_source == source else ()
        overrides = tuple(
            ContactOverride(tuple(item.center), item.shift, item.connector, item.diameter)
            for item in items
        )
        return BaseCut(self.base_band, self.base_area, self.base_margin, self.base_adjustment,
                       connector, overrides)

    def config(self, source: bpy.types.Object | None = None) -> Cut:
        if self.cut_kind == "BASE":
            return self.base_config(source)
        if self.cut_kind == "REGION":
            return self.region_config()
        if self.cut_kind not in {"PLANAR", "SYMMETRY"}:
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
            connector = self.standard_connector(self.connector, self.connector_count)
        cut = PlanarCut(self.axis, self.offset, self.kerf, connector, tuple(self.rotation))
        if self.cut_kind == "SYMMETRY":
            return SymmetricCut(
                cut, self.symmetry_axis, self.symmetry_center,
                self.symmetry_secondary, tuple(self.symmetry_rotation),
            )
        return cut
