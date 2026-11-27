# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import cos, isfinite, pi, sin

import bpy
from mathutils import Matrix, Vector

from ..model import MeshError
from .boolean import ExactBoolean, measure_intersection
from .connector import ConnectorResult, profile_loft, profile_prism, safe_centers, section_volume
from .connector_profiles import area, regular_profile
from .mesh import BOOLEAN_VOLUME_NOISE, inspect, weld_collapsed_edges
from .polygon import Point2

RING = regular_profile(1, 64)


@dataclass(frozen=True)
class PressFit:
    diameter: float
    reach: float
    interference: float
    slot: float
    lateral: float
    axial: float
    wall: float
    angle: float
    count: int
    material: str
    strain_limit: float

    @property
    def radius(self) -> float:
        return self.diameter / 2

    @property
    def pin_radius(self) -> float:
        return self.radius - self.lateral

    @property
    def compressed_radius(self) -> float:
        return self.radius - self.lateral / 2

    @property
    def travel(self) -> float:
        return self.interference + self.lateral / 2

    @property
    def mouth_depth(self) -> float:
        return min(self.reach / 8, self.radius / 3)

    @property
    def anchor(self) -> float:
        return self.radius

    @property
    def envelope(self) -> float:
        return self.radius + self.travel + self.wall

    def reflected(self, _axis: str) -> "PressFit":
        # The slotted section is symmetric about both of its rotated axes.
        return replace(self, angle=-self.angle)

    def free_span(self, kerf: float) -> float:
        # Use the start of the swell and the full-width end of the rounded root.
        return kerf + .55 * self.reach - self.slot * .625

    def strain(self, kerf: float) -> float:
        # End-loaded cantilever strain, with a factor of two on the nominal
        # estimate for the variable cross-section. This is a screening model.
        thickness = self.radius + self.interference - self.slot / 2
        return 300 * thickness * self.travel / self.free_span(kerf) ** 2

    def validate_dimensions(self) -> None:
        sizes = self.diameter, self.reach, self.interference, self.slot, self.lateral, self.axial, self.wall
        if not all(map(isfinite, (*sizes, self.angle))) or min(sizes) <= 0 or self.count < 1:
            raise MeshError("Set positive press-fit dimensions, interference and clearances.")
        if (self.slot - 2 * self.travel < self.lateral
                or self.pin_radius - self.slot / 2 < self.lateral or self.free_span(0) <= 0):
            raise MeshError("The press-fit slot must leave room for compression and two printable prongs.")

    def validate(self, kerf: float) -> None:
        self.validate_dimensions()
        if not self.material.strip() or not isfinite(self.strain_limit) or not 0 < self.strain_limit <= 100:
            raise MeshError("Enter the print material and its verified strain limit for the press-fit.")
        span = self.free_span(kerf)
        if span < 4 * (self.pin_radius - self.slot / 2) or self.travel > .1 * span:
            raise MeshError("Lengthen the press-fit pin or reduce its interference.")
        if self.strain(kerf) > self.strain_limit:
            raise MeshError("The press-fit exceeds the configured strain limit. Reduce interference or increase reach.")

    def section(self, x: float, y: float) -> tuple[Point2, ...]:
        c, s = cos(self.angle), sin(self.angle)
        return tuple((a * x * c - b * y * s, a * x * s + b * y * c) for a, b in RING)


def press_centers(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: PressFit, epsilon: float, requested: tuple[Vector, ...] | None,
) -> list[Vector]:
    design.validate(kerf)
    return safe_centers(
        engine, minus, plus, frame, (position - kerf / 2, position + kerf / 2),
        (design.anchor + design.wall, design.reach + design.axial + design.wall),
        regular_profile(design.envelope / cos(pi / len(RING)), len(RING)), epsilon,
        min(epsilon, design.wall / 20), design.count, requested,
    )


def add_press_fits(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: PressFit, epsilon: float, requested: tuple[Vector, ...] | None,
) -> ConnectorResult:
    low, high = position - kerf / 2, position + kerf / 2
    identity = Matrix.Identity(3)
    if frame != identity:
        inverse = frame.transposed().to_4x4()
        for body, seam in ((minus, low), (plus, high)):
            body.transform(inverse)
            for vertex in body.vertices:
                if abs(vertex.co.z - seam) < epsilon:
                    vertex.co.z = seam
            body.update()
    centers = press_centers(engine, minus, plus, identity, position, kerf, design, epsilon, requested)
    before_minus, before_plus = inspect(minus), inspect(plus)
    tx = engine.transaction
    tip = high + design.reach
    radius = design.pin_radius
    # Build the fork at the origin before rotation, translation or union with
    # the body. Applying the slot to the large joined part can make Exact
    # re-tessellate and collapse otherwise unrelated faces around the seam.
    neutral = replace(design, angle=0)
    root = neutral.section(radius, radius)
    swelling = neutral.section(radius, design.radius + design.interference)
    lead = neutral.section(radius * .8, radius * .8)
    local_tip = kerf + design.reach
    blank_sections = (
        (-design.anchor, root), (kerf + .55 * design.reach, root),
        (kerf + .76 * design.reach, swelling), (kerf + .86 * design.reach, swelling), (local_tip, lead),
    )
    floor = tip + design.axial
    mouth = design.section(design.radius + design.travel, design.radius + design.travel)
    throat = design.section(design.radius, design.radius)
    socket_sections = (
        (high, mouth), (high + design.mouth_depth, throat), (floor, throat),
    )
    inset = min(epsilon, design.wall / 20)
    cutter = ((high - inset, mouth), *socket_sections)
    slot_end = design.slot / 2
    slot_center = design.slot * .625
    # Round the bottom of the slot in the longitudinal plane of the flex.
    arc = tuple((slot_end * x, slot_center + slot_end * y) for x, y in RING[len(RING) // 2:])
    arc += ((slot_end, slot_center), (slot_end, local_tip + inset), (-slot_end, local_tip + inset))
    slot_frame = Matrix((identity.col[1], identity.col[2], identity.col[0])).transposed()
    origin = Vector((0, 0, 0))
    blank = profile_loft(tx, identity, origin, blank_sections)
    slot = profile_prism(tx, slot_frame, origin, -design.radius, design.radius, arc)
    fork = engine.run(blank, slot, "DIFFERENCE")
    tx.remove_mesh(blank)
    tx.remove_mesh(slot)
    weld_collapsed_edges(fork)
    pin_check = inspect(fork)
    if pin_check.shells != 1:
        raise MeshError("The press-fit prongs could not be cut as a single pin.")
    transform = Matrix.Rotation(design.angle, 4, "Z")

    expected_pin = (pin_check.volume_mm3 - area(root) * design.anchor) * len(centers)
    expected_socket = section_volume(socket_sections) * len(centers)
    for center in centers:
        pin = tx.own_mesh(fork.copy())
        transform.translation = Vector((center.x, center.y, low))
        pin.transform(transform)
        pin.update()
        joined = engine.run(minus, pin, "UNION")
        socket = profile_loft(tx, identity, center, cutter)
        carved = engine.run(plus, socket, "DIFFERENCE")
        weld_collapsed_edges(joined)
        weld_collapsed_edges(carved)

        # The compressed outline is bounded by this constant section at every
        # depth. Convexity keeps intermediate loft sections within the bore.
        # The through-approach tube proves axial travel up to the socket floor.
        envelope = design.section(design.compressed_radius, design.compressed_radius)
        approach = profile_prism(tx, identity, center, low - inset, tip, envelope)
        if (measure_intersection(engine, approach, carved)
                or measure_intersection(engine, pin, carved) <= BOOLEAN_VOLUME_NOISE):
            raise MeshError("The press-fit blocks assembly or has no retaining interference.")
        for mesh in (minus, plus, pin, socket, approach):
            tx.remove_mesh(mesh)
        minus, plus = joined, carved
    tx.remove_mesh(fork)

    after_minus, after_plus = inspect(minus), inspect(plus)
    deltas = ((after_minus.volume_mm3 - before_minus.volume_mm3, expected_pin),
              (before_plus.volume_mm3 - after_plus.volume_mm3, expected_socket))
    if (after_minus.shells != before_minus.shells or after_plus.shells != before_plus.shells
            or any(abs(actual - expected) > max(BOOLEAN_VOLUME_NOISE, expected * .005)
                   for actual, expected in deltas)):
        raise MeshError("The press-fit pin or socket could not be cut cleanly.")
    if frame != identity:
        transform = frame.to_4x4()
        for body in (minus, plus):
            body.transform(transform)
            body.update()
    return ConnectorResult((minus, plus), tuple(centers))
