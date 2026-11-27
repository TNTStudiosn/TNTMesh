# SPDX-License-Identifier: GPL-3.0-or-later
from math import radians

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
from .geometry.connector_profiles import PROFILE_ITEMS
from .geometry.custom_connector import CustomConnector
from .geometry.dovetail import Dovetail
from .geometry.glue import GlueAssist
from .geometry.hinge import Hinge
from .geometry.magnet import Magnet
from .geometry.planar import PlanarCut
from .geometry.press_fit import PressFit
from .geometry.region import RegionCut
from .geometry.rod import Rod
from .geometry.screw import Screw
from .geometry.snap_fit import SnapFit
from .geometry.symmetry import SymmetricCut
from .geometry.volume import Cut, VolumeCut
from .model import MeshError, millimeters_per_unit

MAGNET_SHAPES = (
    ("DISC", "Disc", "Create a circular magnet pocket"),
    ("BLOCK", "Block", "Create a rectangular magnet pocket"),
)
SNAP_FIT_FIELDS = ("width", "thickness", "reach", "hook", "ramp_angle", "angle", "material", "strain_limit")
PRESS_FIT_FIELDS = ("diameter", "reach", "interference", "slot", "angle", "material", "strain_limit")
ROD_FIELDS = ("shape", "size", "depth_minus", "depth_plus", "angle")
SCREW_FIELDS = ("diameter", "length", "pitch", "head_width", "head_height", "nut_width", "nut_height", "angle")
HINGE_FIELDS = ("diameter", "pin_diameter", "width", "knuckles", "stand_off", "angle", "shift", "opening")
GLUE_FIELDS = ("channels", "reservoir", "vent", "chamfer", "texture", "relief", "angle")


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
    def get_offset_view(self) -> float:
        return self.offset / millimeters_per_unit(self.id_data)

    def set_offset_view(self, value: float) -> None:
        self.offset = value * millimeters_per_unit(self.id_data)

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
            ("PATH", "Manual Path", "Split along an open path drawn in the viewport"),
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
    offset_view: FloatProperty(
        get=get_offset_view, set=set_offset_view, options={"HIDDEN", "SKIP_SAVE"},
    )
    kerf: FloatProperty(
        name="Kerf (mm)", description="Physical gap removed between the pieces",
        min=0.0, precision=3, step=5,
    )
    show_plane: BoolProperty(name="Show plane", default=True)
    show_cut_handle: BoolProperty(
        name="Show drag handle", description="Move the cutting plane along its normal in the viewport",
        default=True,
    )
    show_build_volume: BoolProperty(name="Show print volume")
    connector: EnumProperty(
        name="Connector",
        items=[
            ("NONE", "None", "Create two pieces without a connector"),
            ("ROUND", "Cylindrical", "Add a round pin and matching socket"),
            ("HEX", "Hexagonal", "Add a hexagonal pin and matching socket"),
            ("CUSTOM", "Custom Mesh", "Use a shaped pin mesh and a matching socket cutter"),
            ("MAGNET", "Magnets", "Cut pockets on both sides for purchased magnets"),
            ("DOVETAIL", "Dovetail", "Add an integrated sliding rail and an open-ended groove"),
            *PROFILE_ITEMS,
            ("SNAP_FIT", "Snap-fit", "Add a flexible hook and a matching retaining pocket"),
            ("HINGE", "Pin Hinge", "Add interlocking hinge barrels and a separate axle"),
            ("PRESS_FIT", "Press-fit", "Add a split pin held by radial interference"),
            ("ROD", "Rod Sockets", "Cut matching sockets for an external rod"),
            ("SCREW", "Machine Screw", "Cut a through-hole, a recessed head seat and a captive hex nut seat"),
        ],
        default="ROUND",
    )
    diameter: FloatProperty(
        name="Diameter (mm)", description="Pin diameter measured across opposite vertices",
        default=5.0, min=0.01, precision=2,
    )
    connector_width: FloatProperty(name="Width (mm)", default=6, min=.01, precision=2)
    connector_height: FloatProperty(name="Height (mm)", default=4, min=.01, precision=2)
    connector_angle: FloatProperty(name="Profile rotation", subtype="ANGLE", unit="ROTATION")
    connector_taper: FloatProperty(name="Tip reduction (%)", subtype="PERCENTAGE", default=25, min=0, max=80,
                                   description="Percent by which the pin tip is narrower than its base")
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
    connector_points: CollectionProperty(type=TNTMESH_PG_contour_point)
    connector_point_index: IntProperty(min=0)
    pin_positive: BoolProperty(
        name="Pin on positive side", description="Use the positive side of the cut normal for the integrated pin",
    )
    magnet_shape: EnumProperty(name="Shape", items=MAGNET_SHAPES)
    magnet_width: FloatProperty(name="Magnet width (mm)", default=6, min=.01, precision=2)
    magnet_length: FloatProperty(name="Magnet length (mm)", default=4, min=.01, precision=2)
    magnet_thickness: FloatProperty(name="Magnet thickness (mm)", default=3, min=.01, precision=2)
    magnet_inset: FloatProperty(
        name="Face inset (mm)", description="Recess the magnet face below the cut surface", min=0, precision=2,
    )
    magnet_adhesive: FloatProperty(
        name="Adhesive gap (mm)", description="Reserve room beneath each magnet for adhesive",
        default=.15, min=0, precision=2,
    )
    magnet_angle: FloatProperty(name="Magnet rotation", subtype="ANGLE", unit="ROTATION")
    dovetail_neck: FloatProperty(name="Neck (mm)", default=4, min=.01, precision=2)
    dovetail_head: FloatProperty(name="Head (mm)", default=6, min=.01, precision=2)
    dovetail_height: FloatProperty(name="Rail height (mm)", default=3, min=.01, precision=2)
    dovetail_length: FloatProperty(name="Rail length (mm)", default=7, min=.01, precision=2)
    dovetail_angle: FloatProperty(name="Exit angle", subtype="ANGLE", unit="ROTATION",
                                  description="Rotate the groove opening from the positive local Y axis of the cut")
    snap_width: FloatProperty(name="Beam width (mm)", default=5, min=.01, precision=2)
    snap_thickness: FloatProperty(name="Beam thickness (mm)", default=1.4, min=.01, precision=2)
    snap_reach: FloatProperty(name="Reach (mm)", default=12, min=.01, precision=2,
                              description="Reach into the socket beyond the socket-side cut face")
    snap_hook: FloatProperty(name="Hook height (mm)", default=.75, min=.01, precision=2)
    snap_ramp_angle: FloatProperty(name="Ramp angle", default=radians(32), min=radians(10), max=radians(60),
                                   subtype="ANGLE", unit="ROTATION")
    snap_angle: FloatProperty(name="Hook rotation", subtype="ANGLE", unit="ROTATION",
                              description="Rotate the direction the hook points in the cut plane")
    snap_material: StringProperty(name="Print material", maxlen=128,
                                  description="Material used for the flexible hook")
    snap_strain_limit: FloatProperty(
        name="Strain limit (%)", default=0, min=0, max=100, subtype="PERCENTAGE", precision=2,
        description="Allowable strain measured for this print material and layer orientation",
    )
    screw_diameter: FloatProperty(name="Screw diameter (mm)", default=3, min=.01, precision=2)
    screw_length: FloatProperty(
        name="Under-head length (mm)", default=25, min=.01, precision=2,
        description="Length measured from the underside of the screw head to its tip",
    )
    screw_pitch: FloatProperty(name="Thread pitch (mm)", default=.5, min=.01, precision=2)
    screw_head_width: FloatProperty(name="Head diameter (mm)", default=5.5, min=.01, precision=2)
    screw_head_height: FloatProperty(name="Head height (mm)", default=3, min=.01, precision=2)
    screw_nut_width: FloatProperty(
        name="Nut across flats (mm)", default=5.5, min=.01, precision=2,
        description="Distance between two opposite flat faces of the hex nut",
    )
    screw_nut_height: FloatProperty(name="Nut thickness (mm)", default=2.4, min=.01, precision=2)
    screw_angle: FloatProperty(name="Nut rotation", subtype="ANGLE", unit="ROTATION")
    rod_shape: EnumProperty(name="Stock shape", items=(
        ("ROUND", "Round", "Use a round rod"),
        ("SQUARE", "Square section", "Use a square rod"),
    ))
    rod_size: FloatProperty(name="Stock size (mm)", default=4, min=.01, precision=2)
    rod_depth_minus: FloatProperty(
        name="Negative side (mm)", default=6, min=.01, precision=2,
        description="Nominal rod insertion on the negative side of the cut",
    )
    rod_depth_plus: FloatProperty(
        name="Positive side (mm)", default=8, min=.01, precision=2,
        description="Nominal rod insertion on the positive side of the cut",
    )
    rod_angle: FloatProperty(name="Profile rotation", subtype="ANGLE", unit="ROTATION")
    press_diameter: FloatProperty(name="Bore diameter (mm)", default=5, min=.01, precision=2)
    press_reach: FloatProperty(name="Insertion (mm)", default=20, min=.01, precision=2)
    press_interference: FloatProperty(
        name="Radial interference (mm)", default=.18, min=.01, precision=2,
        description="Amount by which each relaxed prong extends beyond the bore radius",
    )
    press_slot: FloatProperty(name="Slot width (mm)", default=1.2, min=.01, precision=2)
    press_angle: FloatProperty(name="Slot rotation", subtype="ANGLE", unit="ROTATION")
    press_material: StringProperty(name="Print material", maxlen=128)
    press_strain_limit: FloatProperty(
        name="Allowable strain (%)", subtype="PERCENTAGE", min=0, max=100, precision=2,
        description="Verified elastic strain limit for the printed material and layer orientation",
    )
    hinge_diameter: FloatProperty(name="Barrel diameter (mm)", default=6, min=.01, precision=2)
    hinge_pin_diameter: FloatProperty(name="Axle diameter (mm)", default=2.4, min=.01, precision=2)
    hinge_width: FloatProperty(name="Hinge span (mm)", default=18, min=.01, precision=2)
    hinge_knuckles: IntProperty(name="Knuckles", default=3, min=3, max=32, soft_max=9)
    hinge_stand_off: FloatProperty(name="Axis offset (mm)", default=2, min=.01, precision=2,
                                   description="Distance from the model edge to the hinge axis")
    hinge_angle: FloatProperty(name="Edge rotation", subtype="ANGLE", unit="ROTATION",
                                description="Choose the mounting edge by rotating around the cut normal")
    hinge_shift: FloatProperty(name="Shift along edge (mm)", precision=2)
    hinge_opening: FloatProperty(name="Test opening", default=radians(90), min=radians(1), max=radians(180),
                                  subtype="ANGLE", unit="ROTATION", description="Opening to check for collisions")
    loose_pins: BoolProperty(
        name="Separate pins", description="Cut two sockets and generate removable pins",
    )
    glue_channels: BoolProperty(name="Adhesive Channels", description="Cut two shallow channels along the socket wall")
    glue_reservoir: BoolProperty(name="Glue Reservoir", description="Reserve space for excess adhesive below the pin")
    glue_vent: BoolProperty(name="Air Outlet", description="Open a narrow path from the socket to an outside edge")
    glue_chamfer: BoolProperty(name="Entry Chamfer", description="Widen the entrance to guide the pin into the socket")
    glue_texture: BoolProperty(name="Internal Texture", description="Add three shallow grooves inside the socket")
    glue_relief: FloatProperty(name="Relief (mm)", min=.05, default=.35, precision=2,
                               description="Size of the selected glue relief features")
    glue_angle: FloatProperty(name="Relief rotation", subtype="ANGLE", unit="ROTATION",
                              description="Aim the air outlet in the cut plane and rotate the internal channels")
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
    repair_orientation: BoolProperty(
        name="Correct face orientation",
        description="Orient closed shells and preserve enclosed cavities on the copy",
    )
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
    path_smoothing: IntProperty(
        name="Path smoothing", description="Soften the interior points of the manual path",
        min=0, max=12, default=0,
    )
    draw_snap: EnumProperty(
        name="Snap",
        items=[
            ("VIEW", "View Plane", "Project onto a plane through the model"),
            ("SURFACE", "Surface", "Use the point where the cursor ray hits the model"),
            ("VERTEX", "Vertex", "Snap to a nearby vertex of the surface under the cursor"),
            ("EDGE", "Edge", "Snap to a nearby edge of the surface under the cursor"),
        ],
        default="VIEW",
    )
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
            *PROFILE_ITEMS,
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
        ("ROUND", "Cylindrical", ""), ("HEX", "Hexagonal", ""), *PROFILE_ITEMS,
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
                         self.wall, count, self.loose_pins, self.connector_width, self.connector_height,
                         self.connector_angle, self.connector_taper / 100)

    def magnet_config(self, count: int) -> Magnet:
        return Magnet(
            self.magnet_shape, self.magnet_width, self.magnet_length, self.magnet_thickness,
            self.lateral, self.magnet_inset, self.magnet_adhesive, self.wall, self.magnet_angle, count,
        )

    def dovetail_config(self, count: int) -> Dovetail:
        return Dovetail(self.dovetail_neck, self.dovetail_head, self.dovetail_height, self.dovetail_length,
                        self.lateral, self.axial, self.wall, self.dovetail_angle, count)

    def snap_config(self, count: int) -> SnapFit:
        return SnapFit(
            self.snap_width, self.snap_thickness, self.snap_reach, self.snap_hook, self.snap_ramp_angle,
            self.lateral, self.axial, self.wall, self.snap_angle, count, self.snap_material, self.snap_strain_limit,
        )

    def press_config(self, count: int) -> PressFit:
        return PressFit(
            self.press_diameter, self.press_reach, self.press_interference, self.press_slot,
            self.lateral, self.axial, self.wall, self.press_angle, count, self.press_material, self.press_strain_limit,
        )

    def screw_config(self, count: int) -> Screw:
        return Screw(
            self.screw_diameter, self.screw_length, self.screw_pitch, self.screw_head_width, self.screw_head_height,
            self.screw_nut_width, self.screw_nut_height, self.screw_angle, self.lateral, self.axial, self.wall, count,
        )

    def rod_config(self, count: int) -> Rod:
        return Rod(
            self.rod_shape, self.rod_size, self.rod_depth_minus, self.rod_depth_plus,
            self.rod_angle, self.lateral, self.axial, self.wall, count,
        )

    def hinge_config(self) -> Hinge:
        return Hinge(
            self.hinge_diameter, self.hinge_pin_diameter, self.hinge_width, self.hinge_knuckles,
            self.hinge_stand_off, self.hinge_angle, self.hinge_shift, self.hinge_opening,
            self.lateral, self.axial, self.wall,
        )

    def glue_config(self) -> GlueAssist | None:
        values = {name: getattr(self, f"glue_{name}") for name in GLUE_FIELDS}
        if any(values[name] for name in GLUE_FIELDS[:5]):
            return GlueAssist(**values)
        return None

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
            size = (1.0, 1.0, self.contour_depth) if self.cut_kind in {"POLYGON", "PATH"} else tuple(self.profile_size)
            return VolumeCut(
                self.cut_kind, self.axis, tuple(self.rotation), self.offset,
                tuple(self.profile_shift), size, tuple(self.curve_controls),
                self.curve_samples, self.cutter, tuple(tuple(point.position) for point in self.contour),
                self.path_smoothing,
            )
        connector = None
        positions = tuple(tuple(point.position) for point in self.connector_points) if self.cut_kind == "PLANAR" else ()
        if self.connector == "CUSTOM":
            connector = CustomConnector(self.pin_template, self.socket_template, self.wall)
        elif self.connector == "MAGNET":
            connector = self.magnet_config(len(positions) or self.connector_count)
        elif self.connector == "DOVETAIL":
            connector = self.dovetail_config(len(positions) or self.connector_count)
        elif self.connector == "SNAP_FIT":
            connector = self.snap_config(len(positions) or self.connector_count)
        elif self.connector == "PRESS_FIT":
            connector = self.press_config(len(positions) or self.connector_count)
        elif self.connector == "ROD":
            connector = self.rod_config(len(positions) or self.connector_count)
        elif self.connector == "SCREW":
            connector = self.screw_config(len(positions) or self.connector_count)
        elif self.connector == "HINGE":
            if self.cut_kind != "PLANAR":
                raise MeshError("Choose a straight cut for the pin hinge.")
            connector = self.hinge_config()
        elif self.connector != "NONE":
            connector = self.standard_connector(self.connector, len(positions) or self.connector_count)
        cut = PlanarCut(
            self.axis, self.offset, self.kerf, connector, tuple(self.rotation),
            positions, self.cut_kind == "PLANAR" and self.connector != "ROD" and self.pin_positive
            and (self.connector in {"DOVETAIL", "PRESS_FIT", "SCREW", "SNAP_FIT"} or not self.loose_pins),
            self.glue_config() if isinstance(connector, Connector) else None,
        )
        if self.cut_kind == "SYMMETRY":
            return SymmetricCut(
                cut, self.symmetry_axis, self.symmetry_center,
                self.symmetry_secondary, tuple(self.symmetry_rotation),
            )
        return cut
