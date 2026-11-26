# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import cos, isfinite, sin, tau

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .mesh import VOLUME_EPSILON, bounds, inspect, primitive


@dataclass(frozen=True)
class Connector:
    shape: str = "ROUND"
    diameter: float = 5.0
    insertion: float = 4.0
    lateral: float = 0.15
    axial: float = 0.2
    wall: float = 0.8

    @property
    def sides(self) -> int:
        return 6 if self.shape == "HEX" else 64

    @property
    def socket_radius(self) -> float:
        # Translate each polygon edge by the requested gap along its normal.
        return self.diameter / 2 + self.lateral / cos(tau / (2 * self.sides))

    def validate(self) -> None:
        values = (self.diameter, self.insertion, self.lateral, self.axial, self.wall)
        if (self.shape not in {"ROUND", "HEX"} or not all(map(isfinite, values))
                or min(self.diameter, self.insertion, self.wall) <= 0
                or min(self.lateral, self.axial) < 0):
            raise MeshError("Check the connector dimensions and clearances.")


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
    profile = [
        (round(cos(angle), 15), round(sin(angle), 15))
        for angle in (tau * index / sides for index in range(sides))
    ]
    vertices = [
        frame @ Vector((center.x + radius * x, center.y + radius * y, z))
        for z in (start, end)
        for x, y in profile
    ]
    faces = [tuple(reversed(range(sides))), tuple(range(sides, 2 * sides))]
    for index in range(sides):
        neighbor = (index + 1) % sides
        faces.append((index, neighbor, sides + neighbor, sides + index))
    return primitive(transaction, ".TNTMesh connector tool", vertices, faces)


def candidates(mesh: bpy.types.Mesh, frame: Matrix, seam: float, epsilon: float):
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


def add_connector(
    engine: ExactBoolean,
    minus: bpy.types.Mesh,
    plus: bpy.types.Mesh,
    frame: Matrix,
    position: float,
    kerf: float,
    config: Connector,
    epsilon: float,
) -> tuple[bpy.types.Mesh, bpy.types.Mesh]:
    config.validate()
    low = position - kerf / 2
    high = position + kerf / 2
    anchor = min(config.insertion / 2, config.diameter / 2)
    envelope = config.socket_radius + config.wall / cos(tau / (2 * config.sides))
    # Keep the probe inside the cut plane. The applied tool crosses the seam.
    inset = min(epsilon, anchor / 10, config.wall / 10)
    probes = (
        (minus, low - anchor - config.wall, low - inset),
        (plus, high + inset, high + config.insertion + config.axial + config.wall),
    )
    for center in candidates(minus, frame, low, epsilon * 2):
        with GeometryTransaction() as temporary:
            test_engine = ExactBoolean(engine.context, temporary)
            for mesh, start, end in probes:
                probe = prism(temporary, frame, center, start, end, envelope, config.sides)
                sample = test_engine.run(probe, mesh, "DIFFERENCE")
                if sample.polygons:
                    break
            else:
                break
    else:
        raise MeshError("No safe connector position. Reduce its size or move the cut.")

    pin = prism(
        engine.transaction, frame, center, low - anchor, high + config.insertion,
        config.diameter / 2, config.sides,
    )
    socket = prism(
        engine.transaction, frame, center, high - inset, high + config.insertion + config.axial,
        config.socket_radius, config.sides,
    )
    male = engine.run(minus, pin, "UNION")
    female = engine.run(plus, socket, "DIFFERENCE")
    before_male, after_male = inspect(minus), inspect(male)
    before_female, after_female = inspect(plus), inspect(female)
    polygon_factor = config.sides * sin(tau / config.sides) / 2
    pin_volume = polygon_factor * (config.diameter / 2)**2 * (config.insertion + kerf)
    socket_volume = polygon_factor * config.socket_radius**2 * (config.insertion + config.axial)
    deltas = (
        (after_male.volume_mm3 - before_male.volume_mm3, pin_volume),
        (before_female.volume_mm3 - after_female.volume_mm3, socket_volume),
    )
    if (after_male.shells != before_male.shells or after_female.shells != before_female.shells
            or any(abs(actual - expected) > max(VOLUME_EPSILON, expected * .01)
                   for actual, expected in deltas)):
        raise MeshError("The connector could not be joined or the socket could not be cut.")
    return male, female
