# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import ceil, cos, hypot, isfinite, sin, tan

import bpy
from mathutils import Matrix, Vector

from ..model import MeshError
from .boolean import ExactBoolean
from .connector import ConnectorResult, profile_prism, safe_centers
from .mesh import BOOLEAN_VOLUME_NOISE, absolute_volume, inspect
from .polygon import Point2


@dataclass(frozen=True)
class SnapFit:
    width: float
    thickness: float
    reach: float
    hook: float
    ramp_angle: float
    lateral: float
    axial: float
    wall: float
    angle: float
    count: int
    material: str
    strain_limit: float
    reverse_flex: bool = False

    @property
    def anchor(self) -> float:
        return self.thickness

    @property
    def ramp(self) -> float:
        return self.hook / tan(self.ramp_angle)

    @property
    def land(self) -> float:
        return min(self.thickness / 2, self.hook)

    @property
    def shoulder(self) -> float:
        return self.reach - self.ramp - self.land

    def reflected(self, axis: str) -> "SnapFit":
        return replace(self, angle=-self.angle, reverse_flex=self.reverse_flex ^ (axis == "Y"))

    def strain(self, kerf: float) -> float:
        # Conservative point load at the near edge of the hook's land.
        length = self.shoulder + kerf
        return 150 * self.thickness * self.hook / (length * length)

    def displacement(self, along: float, load: float) -> float:
        ratio = max(0, along) / load
        deflection = ratio * ratio * (3 - ratio) / 2 if ratio < 1 else 1 + 1.5 * (ratio - 1)
        return self.hook * deflection

    def validate_dimensions(self) -> None:
        dimensions = (self.width, self.thickness, self.reach, self.hook,
                      self.ramp_angle, self.lateral, self.axial, self.wall, self.angle)
        if (not all(map(isfinite, dimensions)) or min(self.width, self.thickness, self.reach, self.hook,
                                                    self.wall) <= 0
                or not .17 <= self.ramp_angle <= 1.05 or self.count < 1):
            raise MeshError("Check the snap-fit beam, hook and ramp dimensions.")
        if self.lateral <= 0 or self.axial <= 0:
            raise MeshError("Set positive side and axial clearances for the snap-fit.")
        if self.axial >= self.shoulder or self.hook <= self.lateral:
            raise MeshError("Keep a retaining shoulder by reducing clearance or increasing the hook or reach.")

    def validate(self, kerf: float) -> None:
        self.validate_dimensions()
        load = self.shoulder + kerf
        if load < 5 * self.thickness or self.hook > .12 * load:
            raise MeshError("Lengthen the snap-fit beam or reduce its thickness or hook height.")
        if not self.material.strip() or not isfinite(self.strain_limit) or self.strain_limit <= 0:
            raise MeshError("Enter the print material and its verified strain limit for the snap-fit.")
        if self.strain(kerf) > self.strain_limit:
            raise MeshError("The snap-fit exceeds the configured strain limit. Lengthen or thin the beam.")

    def socket_range(self, kerf: float) -> tuple[float, float]:
        travel = self.displacement(self.reach + kerf, self.shoulder + kerf)
        return -self.thickness / 2 - self.lateral - travel, self.thickness / 2 + self.lateral

    def footprint(self, kerf: float, padding: float = 0) -> tuple[Point2, ...]:
        low, high = self.socket_range(kerf)
        width = self.width / 2 + self.lateral + padding
        if self.reverse_flex:
            low, high = -high - self.hook, -low
        else:
            high += self.hook
        c, s = cos(self.angle), sin(self.angle)
        return tuple((x * c - y * s, x * s + y * c) for x, y in (
            (-width, low - padding), (width, low - padding),
            (width, high + padding), (-width, high + padding),
        ))

    @property
    def envelope(self) -> float:
        self.validate_dimensions()
        return max(hypot(*point) for point in self.footprint(0, self.wall))


def snap_centers(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: SnapFit, epsilon: float, requested: tuple[Vector, ...] | None,
) -> list[Vector]:
    design.validate(kerf)
    return safe_centers(
        engine, minus, plus, frame, (position - kerf / 2, position + kerf / 2),
        (design.anchor + design.wall, design.reach + design.axial + design.wall),
        design.footprint(kerf, design.wall), epsilon, min(epsilon, design.wall / 20), design.count,
        requested=requested, footprint_spacing=True,
    )


def flexed(profile: tuple[Point2, ...], low: float, load: float, design: SnapFit) -> tuple[Point2, ...]:
    deformed = []
    for (y, z), (next_y, next_z) in zip(profile, (*profile[1:], profile[0]), strict=True):
        segments = max(1, ceil(abs(next_z - z) / (load / 12)))
        for index in range(segments):
            fraction = index / segments
            level = z + (next_z - z) * fraction
            shifted = y + (next_y - y) * fraction - design.displacement(level - low, load)
            deformed.append((shifted, level))
    return tuple(deformed)


def add_snap_fits(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: SnapFit, epsilon: float, requested: tuple[Vector, ...] | None,
) -> ConnectorResult:
    centers = snap_centers(engine, minus, plus, frame, position, kerf, design, epsilon, requested)
    rotated = frame @ Matrix.Rotation(design.angle, 3, "Z")
    local = rotated.transposed() @ frame
    section = Matrix((rotated.col[1], rotated.col[2], rotated.col[0])).transposed()
    low, high = position - kerf / 2, position + kerf / 2
    start, tip = low - design.anchor, high + design.reach
    shoulder, ridge = high + design.shoulder, tip - design.ramp
    lock, floor = shoulder - design.axial, tip + design.axial
    half = design.thickness / 2
    socket_low, socket_high = design.socket_range(kerf)
    entry = high - min(epsilon, design.wall / 20)
    pin_shape = (
        (-half, start), (half, start), (half, shoulder), (half + design.hook, shoulder),
        (half + design.hook, ridge), (half, tip), (-half, tip),
    )
    socket_shape = (
        (socket_low, entry), (socket_high, entry), (socket_high, lock),
        (socket_high + design.hook, lock), (socket_high + design.hook, floor), (socket_low, floor),
    )
    insertion_shape = flexed(pin_shape, low, shoulder - low, design)
    original_minus, original_plus = inspect(minus), inspect(plus)
    transaction = engine.transaction

    def tool(center: Vector, profile: tuple[Point2, ...], width: float, shift: float = 0) -> bpy.types.Mesh:
        center = local @ center
        if design.reverse_flex:
            profile = tuple((-y, z + shift) for y, z in reversed(profile))
        elif shift:
            profile = tuple((y, z + shift) for y, z in profile)
        return profile_prism(transaction, section, Vector((center.y, 0, 0)),
                             center.x - width / 2, center.x + width / 2, profile)

    socket_width = design.width + 2 * design.lateral
    for center in centers:
        pin = tool(center, pin_shape, design.width)
        socket = tool(center, socket_shape, socket_width)
        joined = engine.run(minus, pin, "UNION")
        carved = engine.run(plus, socket, "DIFFERENCE")
        for mesh in (minus, plus, pin, socket):
            transaction.remove_mesh(mesh)
        minus, plus = joined, carved

    male, female = inspect(minus), inspect(plus)
    pin_volume = design.width * (
        design.thickness * (tip - low) + design.hook * (design.land + design.ramp / 2)
    )
    socket_volume = socket_width * (
        (socket_high - socket_low) * (floor - high) + design.hook * (floor - lock)
    )
    deltas = ((male.volume_mm3 - original_minus.volume_mm3, pin_volume * len(centers)),
              (original_plus.volume_mm3 - female.volume_mm3, socket_volume * len(centers)))
    if (male.shells != original_minus.shells or female.shells != original_plus.shells
            or any(abs(actual - expected) > max(BOOLEAN_VOLUME_NOISE, expected * .005)
                   for actual, expected in deltas)):
        raise MeshError("The snap-fit beam or socket could not be cut cleanly.")

    for center in centers:
        # The flexed hook stays below the throat for the whole axial approach.
        # The seated pocket also contains the relaxed shape and the release between them.
        checks = ((pin_shape, 0, False), (insertion_shape, 0, False),
                  (pin_shape, -design.axial - design.land / 2, True))
        for shape, shift, catches in checks:
            probe = tool(center, shape, design.width, shift)
            overlap = engine.run(probe, plus, "INTERSECT")
            volume = absolute_volume(overlap)
            transaction.remove_mesh(overlap)
            transaction.remove_mesh(probe)
            if (volume > max(BOOLEAN_VOLUME_NOISE, pin_volume * 1e-6)) != catches:
                raise MeshError("The snap-fit blocks insertion or its hook does not retain the parts.")
    return ConnectorResult((minus, plus), tuple(centers))
