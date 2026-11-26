# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass
from math import cos, hypot, isfinite, sin

import bpy
from mathutils import Matrix, Vector

from ..model import SLIDE_DIRECTION, GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import ConnectorPlacementError, ConnectorResult, candidates, profile_prism
from .mesh import BOOLEAN_VOLUME_NOISE, absolute_volume, bounds, inspect
from .polygon import Point2


@dataclass(frozen=True)
class Dovetail:
    neck: float
    head: float
    height: float
    length: float
    lateral: float
    axial: float
    wall: float
    angle: float
    count: int

    @property
    def anchor(self) -> float:
        return min(self.height, self.neck) / 2

    @property
    def slope(self) -> float:
        return (self.head - self.neck) / (2 * self.height)

    @property
    def envelope(self) -> float:
        padding = self.lateral + self.wall
        return self.head / 2 + padding * (self.slope + hypot(1, self.slope))

    def validate(self) -> None:
        values = self.neck, self.head, self.height, self.length, self.lateral, self.axial, self.wall, self.angle
        if (not all(map(isfinite, values)) or min(self.neck, self.height, self.length, self.wall) <= 0
                or self.head <= self.neck or min(self.lateral, self.axial) < 0 or self.count < 1):
            raise MeshError("Set a dovetail head wider than its neck and check the dimensions.")
        if self.head - self.neck <= 2 * self.lateral * hypot(1, self.slope):
            raise MeshError("Reduce the side clearance or widen the dovetail head to retain the rail.")

    def footprint(self) -> tuple[Point2, ...]:
        half_width, half_length = self.head / 2, self.length / 2
        c, s = cos(self.angle), sin(self.angle)
        return tuple((x * c - y * s, x * s + y * c) for x, y in (
            (-half_width, -half_length), (half_width, -half_length),
            (half_width, half_length), (-half_width, half_length),
        ))


@dataclass(frozen=True)
class Seat:
    center: Vector
    removed_mm3: float


@dataclass(frozen=True)
class DovetailCut:
    design: Dovetail
    seam: Matrix
    low: float
    high: float
    inset: float
    exit_y: float

    @property
    def frame(self) -> Matrix:
        # Across the slot, below the cut, and out through the opening form a right-handed basis.
        return Matrix((self.seam.col[0], -self.seam.col[2], self.seam.col[1])).transposed()

    def socket(self, bottom: float, clearance: float) -> tuple[Point2, ...]:
        design = self.design
        top = design.height + clearance
        # Move the sloped sides by a true normal offset, including the enlarged top face.
        padding = clearance * hypot(1, design.slope)
        base_width = design.neck / 2 + bottom * design.slope + padding
        top_width = design.neck / 2 + top * design.slope + padding
        return ((-top_width, -self.high - top), (top_width, -self.high - top),
                (base_width, -self.high - bottom), (-base_width, -self.high - bottom))

    def tool(
        self, transaction: GeometryTransaction, center: Vector, ends: tuple[float, float],
        profile: tuple[Point2, ...],
    ) -> bpy.types.Mesh:
        # The ends already contain the distance along the rail. The profile fixes depth at the seam.
        return profile_prism(transaction, self.frame, Vector((center.x, 0)), ends[0], ends[1], profile)

    def validate_seat(
        self, context: bpy.types.Context, minus: bpy.types.Mesh, plus: bpy.types.Mesh, center: Vector,
    ) -> Seat | None:
        d = self.design
        half = d.length / 2
        with GeometryTransaction() as temporary:
            engine = ExactBoolean(context, temporary)
            root = d.neck / 2 + d.wall
            root_low, root_high = -self.low + self.inset, -self.low + d.anchor + d.wall
            guard = self.tool(temporary, center, (center.y - half - d.wall, center.y + half + d.wall),
                              ((-root, root_low), (root, root_low), (root, root_high), (-root, root_high)))
            if engine.run(guard, minus, "DIFFERENCE").polygons:
                return None
            guard = self.tool(temporary, center,
                              (center.y - half - d.axial - d.wall, center.y + half + d.wall),
                              self.socket(self.inset, d.lateral + d.wall))
            if engine.run(guard, plus, "DIFFERENCE").polygons:
                return None
            channel = self.tool(temporary, center, (center.y - half - d.axial, self.exit_y),
                                self.socket(-self.inset, d.lateral))
            removed = engine.run(channel, plus, "INTERSECT")
            try:
                size = inspect(removed)
            except MeshError:
                return None
            if size.shells != 1:
                return None
            return Seat(center, size.volume_mm3)


def candidate_seats(
    minus: bpy.types.Mesh, seam: Matrix, low: float, design: Dovetail, epsilon: float,
) -> Iterator[Vector]:
    inverse = seam.transposed()
    section = (inverse @ vertex.co for vertex in minus.vertices)
    cut_vertices = [point for point in section if abs(point.z - low) <= 2 * epsilon]
    if not cut_vertices:
        return
    lower, upper = bounds(cut_vertices)
    if (design.count - 1) * (2 * design.envelope) > upper.x - lower.x:
        return
    mid = (lower + upper) / 2
    spacing = 2 * design.envelope + 8 * epsilon
    y_values = tuple(lower.y + (upper.y - lower.y) * fraction
                     for fraction in (.5, .25, .75, .125, .875, .375, .625))
    for index in range(design.count):
        x = mid.x + (index - (design.count - 1) / 2) * spacing
        if lower.x < x < upper.x:
            for y in y_values:
                yield Vector((x, y, 0))
    for point in candidates(minus, seam, low, epsilon * 2):
        yield point
    # Finer lateral sampling lets long, irregular seams fit a larger number of rails.
    for index in range(1, design.count * 3):
        x = lower.x + (upper.x - lower.x) * index / (design.count * 3)
        for y in y_values:
            yield Vector((x, y, 0))


def layout(
    context: bpy.types.Context, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: Dovetail, epsilon: float, requested: tuple[Vector, ...] | None,
) -> tuple[DovetailCut, list[Seat]]:
    design.validate()
    seam = frame @ Matrix.Rotation(design.angle, 3, "Z")
    low, high = position - kerf / 2, position + kerf / 2
    inset = min(epsilon, design.anchor / 20, design.wall / 20, design.neck / (20 * max(1, design.slope)))
    outer = seam.col[1]
    exit_y = max(outer.dot(vertex.co) for vertex in plus.vertices) + max(inset * 16, design.wall)
    cut = DovetailCut(design, seam, low, high, inset, exit_y)
    protected = design.envelope
    seats: list[Seat] = []
    from_seam = seam.transposed() @ frame
    points: Iterator[Vector] = ((from_seam @ point for point in requested) if requested is not None
                                else candidate_seats(minus, seam, low, design, epsilon))
    for point in points:
        if not all(map(isfinite, point)) or any(abs(point.x - seat.center.x) < protected * 2 for seat in seats):
            continue
        seat = cut.validate_seat(context, minus, plus, point)
        if seat is not None:
            seats.append(seat)
            if len(seats) == design.count:
                return cut, seats
    raise ConnectorPlacementError("The dovetail does not fit with a clear exit and enough surrounding material.")


def add_dovetails(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: Dovetail, epsilon: float, requested: tuple[Vector, ...] | None,
) -> ConnectorResult:
    cut, seats = layout(engine.context, minus, plus, frame, position, kerf, design, epsilon, requested)
    original_minus, original_plus = inspect(minus), inspect(plus)
    neck, head = design.neck / 2, design.head / 2
    top, root, back = -cut.high - design.height, -cut.high, -cut.low + design.anchor
    profile = ((-head, top), (head, top), (neck, root), (neck, back), (-neck, back), (-neck, root))
    for seat in seats:
        center = seat.center
        pin = cut.tool(engine.transaction, center, (center.y - design.length / 2, center.y + design.length / 2),
                       profile)
        socket = cut.tool(engine.transaction, center, (center.y - design.length / 2 - design.axial, cut.exit_y),
                          cut.socket(-cut.inset, design.lateral))
        next_minus = engine.run(minus, pin, "UNION")
        next_plus = engine.run(plus, socket, "DIFFERENCE")
        for mesh in (minus, plus, pin, socket):
            engine.transaction.remove_mesh(mesh)
        minus, plus = next_minus, next_plus

    male, female = inspect(minus), inspect(plus)
    expected_rail = (design.height * (design.neck + design.head) / 2 + kerf * design.neck) * design.length * len(seats)
    expected_groove = sum(seat.removed_mm3 for seat in seats)
    actual = male.volume_mm3 - original_minus.volume_mm3, original_plus.volume_mm3 - female.volume_mm3
    collision = engine.run(minus, plus, "INTERSECT")
    if (male.shells != original_minus.shells or female.shells != original_plus.shells
            or absolute_volume(collision) > BOOLEAN_VOLUME_NOISE
            or any(abs(measured - expected) > max(BOOLEAN_VOLUME_NOISE, expected * .005)
                   for measured, expected in zip(actual, (expected_rail, expected_groove), strict=True))):
        raise MeshError("The dovetail rail and groove could not be cut cleanly.")
    engine.transaction.remove_mesh(collision)
    direction = cut.seam.col[1]
    minus[SLIDE_DIRECTION], plus[SLIDE_DIRECTION] = tuple(direction), tuple(-direction)
    to_seam = frame.transposed() @ cut.seam
    return ConnectorResult((minus, plus), tuple(to_seam @ seat.center for seat in seats))
