# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass, replace
from itertools import chain
from math import cos, hypot, isfinite, pi, sin
from typing import TYPE_CHECKING

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector_profiles import (
    DIAMETER_SHAPES,
    STANDARD_SHAPES,
    TWO_DIMENSION_SHAPES,
    area,
    dilated,
    outline,
    regular_profile,
    translated_overlap,
)
from .mesh import VOLUME_EPSILON, bounds, inspect, primitive
from .polygon import Point2

if TYPE_CHECKING:
    from .glue import GlueAssist

Section = tuple[float, tuple[Point2, ...]]


class ConnectorPlacementError(MeshError):
    """The requested connector footprint has no valid placement."""


@dataclass(frozen=True)
class Connector:
    shape: str = "ROUND"
    diameter: float = 5.0
    insertion: float = 4.0
    lateral: float = 0.15
    axial: float = 0.2
    wall: float = 0.8
    count: int = 1
    loose: bool = False
    width: float = 6.0
    height: float = 4.0
    angle: float = 0.0
    taper: float = .25
    mirror_profile: bool = False

    @property
    def socket_radius(self) -> float:
        return max(hypot(*point) for point in self.profile(self.lateral))

    @property
    def anchor(self) -> float:
        width = self.diameter if self.shape in DIAMETER_SHAPES else self.width
        if self.shape in TWO_DIMENSION_SHAPES:
            width = min(width, self.height)
        return min(self.insertion, width) / 2

    @property
    def envelope(self) -> float:
        return max(hypot(*point) for point in self.profile(self.lateral + self.wall))

    @property
    def uses_footprint(self) -> bool:
        return self.shape not in {"ROUND", "HEX", "TAPER"}

    @property
    def depths(self) -> tuple[float, float]:
        socket = self.insertion + self.axial + self.wall
        return (socket if self.loose else self.anchor + self.wall), socket

    def validate(self) -> None:
        values = (self.diameter, self.width, self.height, self.insertion, self.lateral, self.axial,
                  self.wall, self.angle, self.taper)
        if (self.shape not in STANDARD_SHAPES or not all(map(isfinite, values))
                or min(self.diameter, self.width, self.height, self.insertion, self.wall) <= 0
                or min(self.lateral, self.axial) < 0 or not 0 <= self.taper <= .8 or self.count < 1):
            raise MeshError("Check the connector dimensions and clearances.")
        self.profile(self.lateral + self.wall)

    def reflected(self, axis: str) -> "Connector":
        if self.shape in {"ROUND", "TAPER"} or (self.shape == "HEX" and not self.angle and not self.mirror_profile):
            return self
        return replace(self, angle=(pi if axis == "X" else 0) - self.angle, mirror_profile=not self.mirror_profile)

    def profile(self, clearance: float = 0, scale: float = 1) -> tuple[Point2, ...]:
        if self.shape in {"ROUND", "TAPER", "HEX", "OCTAGON"}:
            n = {"HEX": 6, "OCTAGON": 8}.get(self.shape, 64)
            factor = cos(pi / n)
            # A tapered flank needs a larger transverse offset to keep the normal gap equal to clearance.
            slope = self.diameter / 2 * self.taper * factor / self.insertion if self.shape == "TAPER" else 0
            points = regular_profile(self.diameter * scale / 2 + clearance * hypot(1, slope) / factor, n)
        else:
            points = dilated(outline(self.shape, self.diameter, self.width, self.height), clearance)
        if self.mirror_profile:
            points = tuple((x, -y) for x, y in reversed(points))
        if self.angle and self.shape not in {"ROUND", "TAPER"}:
            c, s = round(cos(self.angle), 15), round(sin(self.angle), 15)
            points = tuple((x * c - y * s, x * s + y * c) for x, y in points)
        return points

    def sections(self, start: float, end: float, low: float, high: float, clearance: float = 0) -> tuple[Section, ...]:
        if self.shape != "TAPER" or not self.taper:
            ring = self.profile(clearance)
            return (start, ring), (end, ring)
        stops = (high, high + self.insertion)
        if self.loose:
            stops = (low - self.insertion, low, *stops)
        levels = (start, *sorted({z for z in stops if start < z < end}), end)
        return tuple((z, self.profile_at(z, low, high, clearance)) for z in levels)

    def profile_at(self, z: float, low: float, high: float, clearance: float) -> tuple[Point2, ...]:
        if self.shape != "TAPER" or not self.taper:
            return self.profile(clearance)
        return self.profile(clearance, 1 - self.taper * min(1, max(
            0, (z - high) / self.insertion, (low - z) / self.insertion if self.loose else 0,
        )))


@dataclass(frozen=True)
class ConnectorResult:
    meshes: tuple[bpy.types.Mesh, ...]
    centers: tuple[Vector, ...]


def prism(
    transaction: GeometryTransaction,
    frame: Matrix,
    center: Vector,
    start: float,
    end: float,
    radius: float,
    sides: int,
) -> bpy.types.Mesh:
    return profile_prism(transaction, frame, center, start, end, regular_profile(radius, sides))


def profile_prism(
    transaction: GeometryTransaction, frame: Matrix, center: Vector,
    start: float, end: float, profile: tuple[Point2, ...],
) -> bpy.types.Mesh:
    return profile_loft(transaction, frame, center, ((start, profile), (end, profile)))


def profile_loft(
    transaction: GeometryTransaction, frame: Matrix, center: Vector, sections: tuple[Section, ...],
) -> bpy.types.Mesh:
    sides = len(sections[0][1])
    vertices = [
        frame @ Vector((center.x + x, center.y + y, z))
        for z, points in sections for x, y in points
    ]
    faces = [tuple(reversed(range(sides))), tuple(range(len(vertices) - sides, len(vertices)))]
    for base in range(0, len(vertices) - sides, sides):
        for index in range(sides):
            neighbor = (index + 1) % sides
            faces.append(tuple(base + value for value in (index, neighbor, sides + neighbor, sides + index)))
    return primitive(transaction, ".TNTMesh connector tool", vertices, faces)


def section_volume(sections: tuple[Section, ...]) -> float:
    volume = 0.0
    for (start, first), (end, last) in zip(sections[:-1], sections[1:], strict=True):
        middle = tuple(((x + a) / 2, (y + b) / 2) for (x, y), (a, b) in zip(first, last, strict=True))
        volume += (end - start) * (area(first) + 4 * area(middle) + area(last)) / 6
    return volume


def candidates(mesh: bpy.types.Mesh, frame: Matrix, seam: float, epsilon: float) -> Iterator[Vector]:
    inverse = frame.transposed()
    points = [inverse @ vertex.co for vertex in mesh.vertices]
    seam_points = [point for point in points if abs(point.z - seam) <= epsilon]
    if not seam_points:
        return
    lower, upper = bounds(seam_points)
    fractions = (0.5, 0.25, 0.75, 0.125, 0.875, 0.375, 0.625)
    for x_fraction in fractions:
        for y_fraction in fractions:
            yield Vector((
                lower.x + (upper.x - lower.x) * x_fraction,
                lower.y + (upper.y - lower.y) * y_fraction,
                0.0,
            ))


def safe_centers(
    engine: ExactBoolean,
    minus: bpy.types.Mesh,
    plus: bpy.types.Mesh,
    frame: Matrix,
    planes: tuple[float, float],
    depths: tuple[float, float],
    probe_profile: tuple[Point2, ...],
    epsilon: float,
    inset: float,
    count: int,
    requested: tuple[Vector, ...] | None = None,
    requested_error: str = "The requested connector positions do not fit.",
    preferred: tuple[Vector, ...] = (),
    allow_partial: bool = False,
    footprint_spacing: bool = False,
) -> list[Vector]:
    low, high = planes
    envelope = max(hypot(*point) for point in probe_profile)
    probes = ((minus, low - depths[0], low - inset), (plus, high + inset, high + depths[1]))
    centers = []
    search = requested if requested is not None else chain(
        preferred, candidates(minus, frame, low, epsilon * 2),
    )
    for center in search:
        if not all(map(isfinite, center)):
            raise ConnectorPlacementError(requested_error)
        if any((center - other).length < 2 * envelope and (
            not footprint_spacing or translated_overlap(probe_profile, center.x - other.x, center.y - other.y, epsilon)
        ) for other in centers):
            continue
        with GeometryTransaction() as temporary:
            test_engine = ExactBoolean(engine.context, temporary)
            for mesh, start, end in probes:
                probe = profile_prism(temporary, frame, center, start, end, probe_profile)
                sample = test_engine.run(probe, mesh, "DIFFERENCE")
                if sample.polygons:
                    break
            else:
                centers.append(center)
                if len(centers) == count:
                    break
    if not allow_partial and len(centers) < count:
        if requested is not None:
            raise ConnectorPlacementError(requested_error)
        if not centers:
            raise ConnectorPlacementError("No safe connector position. Reduce its size or move the cut.")
        raise ConnectorPlacementError("Not enough safe positions. Reduce the connector count or size.")
    return centers


def add_connector(
    engine: ExactBoolean,
    minus: bpy.types.Mesh,
    plus: bpy.types.Mesh,
    frame: Matrix,
    position: float,
    kerf: float,
    config: Connector,
    epsilon: float,
    requested: tuple[Vector, ...] | None = None,
    requested_error: str = "The requested connector positions do not fit.",
    preferred: tuple[Vector, ...] = (),
    glue: "GlueAssist | None" = None,
) -> ConnectorResult:
    from .glue import carve_socket

    config.validate()
    low = position - kerf / 2
    high = position + kerf / 2
    anchor = config.anchor
    # Keep the probe inside the cut plane. The applied tool crosses the seam.
    inset = min(epsilon, anchor / 10, config.wall / 10)
    if glue is not None:
        glue.validate(config)
    guard = glue.guard(config) if glue else config.profile(config.lateral + config.wall)
    centers = safe_centers(
        engine, minus, plus, frame, (low, high),
        glue.depths(config) if glue else config.depths, guard, epsilon, inset, config.count,
        requested, requested_error, preferred, footprint_spacing=config.uses_footprint,
    )

    socket_depth = config.insertion + config.axial
    pin_data = config.sections(low - (config.insertion if config.loose else anchor), high + config.insertion, low, high)
    positive_socket = config.sections(high - inset, high + socket_depth, low, high, config.lateral)
    negative_socket = config.sections(low - socket_depth, low + inset, low, high, config.lateral) if config.loose else ()
    socket_volume = section_volume(config.sections(high, high + socket_depth, low, high, config.lateral))
    pin_volume = section_volume(config.sections(low, high + config.insertion, low, high)) * len(centers)
    before_minus, before_plus = inspect(minus), inspect(plus)
    separate_pins = []
    removed_minus = removed_plus = 0.0
    backward = frame @ Matrix.Diagonal(Vector((1, -1, -1)))
    reflected_centers = [Vector((point.x, -point.y, 0)) for point in centers] if glue and config.loose else []

    for index, center in enumerate(centers):
        pin = profile_loft(engine.transaction, frame, center, pin_data)
        if config.loose:
            inspect(pin)
            separate_pins.append(pin)
            if glue:
                new_minus, volume = carve_socket(
                    engine, minus, backward, reflected_centers[index], -low,
                    config.reflected("Y"), glue.reflected("Y"), reflected_centers, inset,
                )
            else:
                negative_tool = profile_loft(engine.transaction, frame, center, negative_socket)
                new_minus = engine.run(minus, negative_tool, "DIFFERENCE")
                engine.transaction.remove_mesh(negative_tool)
                volume = socket_volume
            removed_minus += volume
        else:
            new_minus = engine.run(minus, pin, "UNION")
            engine.transaction.remove_mesh(pin)
        if glue:
            new_plus, volume = carve_socket(engine, plus, frame, center, high, config, glue, centers, inset)
        else:
            socket = profile_loft(engine.transaction, frame, center, positive_socket)
            new_plus = engine.run(plus, socket, "DIFFERENCE")
            engine.transaction.remove_mesh(socket)
            volume = socket_volume
        removed_plus += volume
        for mesh in (minus, plus):
            engine.transaction.remove_mesh(mesh)
        minus, plus = new_minus, new_plus

    after_minus, after_plus = inspect(minus), inspect(plus)
    deltas = (
        (after_minus.volume_mm3 - before_minus.volume_mm3,
         -removed_minus if config.loose else pin_volume),
        (before_plus.volume_mm3 - after_plus.volume_mm3, removed_plus),
    )
    if (after_minus.shells != before_minus.shells or after_plus.shells != before_plus.shells
            or any(abs(actual - expected) > max(VOLUME_EPSILON, abs(expected) * .01)
                   for actual, expected in deltas)):
        raise MeshError("The connector could not be joined or the socket could not be cut.")
    return ConnectorResult((minus, plus, *separate_pins), tuple(centers))
