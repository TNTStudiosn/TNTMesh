# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain
from math import cos, isfinite, sin, tau

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .mesh import VOLUME_EPSILON, bounds, inspect, primitive
from .polygon import Point2


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

    @property
    def sides(self) -> int:
        return 6 if self.shape == "HEX" else 64

    @property
    def socket_radius(self) -> float:
        # Translate each polygon edge by the requested gap along its normal.
        return self.diameter / 2 + self.lateral / cos(tau / (2 * self.sides))

    @property
    def anchor(self) -> float:
        return min(self.insertion / 2, self.diameter / 2)

    @property
    def envelope(self) -> float:
        return self.socket_radius + self.wall / cos(tau / (2 * self.sides))

    @property
    def depths(self) -> tuple[float, float]:
        socket = self.insertion + self.axial + self.wall
        return (socket if self.loose else self.anchor + self.wall), socket

    def validate(self) -> None:
        values = (self.diameter, self.insertion, self.lateral, self.axial, self.wall)
        if (self.shape not in {"ROUND", "HEX"} or not all(map(isfinite, values))
                or min(self.diameter, self.insertion, self.wall) <= 0
                or min(self.lateral, self.axial) < 0 or self.count < 1):
            raise MeshError("Check the connector dimensions and clearances.")


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
    # Cardinal vertices must be exact so coincident seam edges do not create slivers.
    profile = tuple(
        (round(cos(angle), 15), round(sin(angle), 15))
        for angle in (tau * index / sides for index in range(sides))
    )
    return profile_prism(transaction, frame, center, start, end, tuple((x * radius, y * radius) for x, y in profile))


def profile_prism(
    transaction: GeometryTransaction, frame: Matrix, center: Vector,
    start: float, end: float, profile: tuple[Point2, ...],
) -> bpy.types.Mesh:
    sides = len(profile)
    vertices = [
        frame @ Vector((center.x + x, center.y + y, z))
        for z in (start, end)
        for x, y in profile
    ]
    faces = [tuple(reversed(range(sides))), tuple(range(sides, 2 * sides))]
    for index in range(sides):
        neighbor = (index + 1) % sides
        faces.append((index, neighbor, sides + neighbor, sides + index))
    return primitive(transaction, ".TNTMesh connector tool", vertices, faces)


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
    envelope: float,
    sides: int,
    epsilon: float,
    inset: float,
    count: int,
    requested: tuple[Vector, ...] | None = None,
    requested_error: str = "The requested connector positions do not fit.",
    preferred: tuple[Vector, ...] = (),
    allow_partial: bool = False,
    probe_profile: tuple[Point2, ...] = (),
) -> list[Vector]:
    low, high = planes
    probes = ((minus, low - depths[0], low - inset), (plus, high + inset, high + depths[1]))
    centers = []
    search = requested if requested is not None else chain(
        preferred, candidates(minus, frame, low, epsilon * 2),
    )
    for center in search:
        if not all(map(isfinite, center)):
            raise ConnectorPlacementError(requested_error)
        if any((center - other).length < 2 * envelope for other in centers):
            continue
        with GeometryTransaction() as temporary:
            test_engine = ExactBoolean(engine.context, temporary)
            for mesh, start, end in probes:
                probe = (profile_prism(temporary, frame, center, start, end, probe_profile) if probe_profile
                         else prism(temporary, frame, center, start, end, envelope, sides))
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
) -> ConnectorResult:
    config.validate()
    low = position - kerf / 2
    high = position + kerf / 2
    anchor = config.anchor
    # Keep the probe inside the cut plane. The applied tool crosses the seam.
    inset = min(epsilon, anchor / 10, config.wall / 10)
    centers = safe_centers(
        engine, minus, plus, frame, (low, high),
        config.depths, config.envelope, config.sides, epsilon, inset, config.count,
        requested, requested_error, preferred,
    )

    polygon_factor = config.sides * sin(tau / config.sides) / 2
    pin_area = polygon_factor * (config.diameter / 2)**2
    socket_area = polygon_factor * config.socket_radius**2
    socket_depth = config.insertion + config.axial
    socket_volume = socket_area * socket_depth * len(centers)
    pin_volume = pin_area * (config.insertion + kerf) * len(centers)
    before_minus, before_plus = inspect(minus), inspect(plus)
    separate_pins = []

    for center in centers:
        pin_start = low - (config.insertion if config.loose else anchor)
        pin = prism(
            engine.transaction, frame, center, pin_start, high + config.insertion,
            config.diameter / 2, config.sides,
        )
        if config.loose:
            inspect(pin)
            separate_pins.append(pin)
            negative_tool = prism(
                engine.transaction, frame, center, low - socket_depth, low + inset,
                config.socket_radius, config.sides,
            )
            new_minus = engine.run(minus, negative_tool, "DIFFERENCE")
            engine.transaction.remove_mesh(negative_tool)
        else:
            new_minus = engine.run(minus, pin, "UNION")
            engine.transaction.remove_mesh(pin)
        socket = prism(
            engine.transaction, frame, center, high - inset, high + socket_depth,
            config.socket_radius, config.sides,
        )
        new_plus = engine.run(plus, socket, "DIFFERENCE")
        for mesh in (minus, plus, socket):
            engine.transaction.remove_mesh(mesh)
        minus, plus = new_minus, new_plus

    after_minus, after_plus = inspect(minus), inspect(plus)
    deltas = (
        (after_minus.volume_mm3 - before_minus.volume_mm3,
         -socket_volume if config.loose else pin_volume),
        (before_plus.volume_mm3 - after_plus.volume_mm3, socket_volume),
    )
    if (after_minus.shells != before_minus.shells or after_plus.shells != before_plus.shells
            or any(abs(actual - expected) > max(VOLUME_EPSILON, abs(expected) * .01)
                   for actual, expected in deltas)):
        raise MeshError("The connector could not be joined or the socket could not be cut.")
    return ConnectorResult((minus, plus, *separate_pins), tuple(centers))
