# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import cos, hypot, isfinite, sin, tau

import bpy
from mathutils import Matrix, Vector

from ..model import MeshError
from .boolean import ExactBoolean
from .connector import ConnectorResult, profile_prism, safe_centers
from .mesh import VOLUME_EPSILON, inspect
from .polygon import Point2, signed_turn

DISC_SIDES = 64


@dataclass(frozen=True)
class Magnet:
    shape: str
    width: float
    length: float
    thickness: float
    lateral: float
    inset: float
    adhesive: float
    wall: float
    angle: float
    count: int

    @property
    def depth(self) -> float:
        return self.thickness + self.inset + self.adhesive

    @property
    def envelope(self) -> float:
        return max(hypot(*point) for point in self.profile(self.wall))

    def validate(self) -> None:
        measures = self.width, self.length, self.thickness, self.lateral, self.inset, self.adhesive, self.wall
        if (self.shape not in {"DISC", "BLOCK"} or not all(map(isfinite, (*measures, self.angle)))
                or min(self.width, self.length, self.thickness, self.wall) <= 0
                or min(self.lateral, self.inset, self.adhesive) < 0 or self.count < 1):
            raise MeshError("Check the magnet dimensions and clearances.")

    def profile(self, extra: float = 0.0) -> tuple[Point2, ...]:
        padding = self.lateral + extra
        if self.shape == "DISC":
            radius = (self.width / 2 + padding) / cos(tau / (2 * DISC_SIDES))
            return tuple(
                (radius * round(cos(angle), 15), radius * round(sin(angle), 15))
                for angle in (tau * i / DISC_SIDES for i in range(DISC_SIDES))
            )
        x, y = self.width / 2 + padding, self.length / 2 + padding
        cosine, sine = round(cos(self.angle), 15), round(sin(self.angle), 15)
        return tuple((a * cosine - b * sine, a * sine + b * cosine)
                     for a, b in ((-x, -y), (x, -y), (x, y), (-x, y)))


def magnet_centers(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, config: Magnet, epsilon: float,
    requested: tuple[Vector, ...] | None = None,
) -> list[Vector]:
    config.validate()
    low, high = position - kerf / 2, position + kerf / 2
    pin_gap = min(epsilon, config.wall / 10, config.thickness / 10)
    outer = config.profile(config.wall)
    depth = config.depth + config.wall
    return safe_centers(
        engine, minus, plus, frame, (low, high), (depth, depth), config.envelope, len(outer),
        epsilon, pin_gap, config.count, requested=requested, probe_profile=outer,
    )


def add_magnet_pockets(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, config: Magnet, epsilon: float,
    requested: tuple[Vector, ...] | None = None,
) -> ConnectorResult:
    centers = magnet_centers(engine, minus, plus, frame, position, kerf, config, epsilon, requested)
    low, high = position - kerf / 2, position + kerf / 2
    pin_gap = min(epsilon, config.wall / 10, config.thickness / 10)
    profile = config.profile()
    area = sum(signed_turn(profile[0], a, b) for a, b in zip(profile[1:-1], profile[2:], strict=True)) / 2
    expected = area * config.depth * len(centers)
    bodies = []
    for mesh, start, end in (
        (minus, low - config.depth, low + pin_gap), (plus, high - pin_gap, high + config.depth),
    ):
        before = inspect(mesh)
        body = mesh
        for center in centers:
            socket = profile_prism(engine.transaction, frame, center, start, end, profile)
            cut = engine.run(body, socket, "DIFFERENCE")
            engine.transaction.remove_mesh(socket)
            if body != mesh:
                engine.transaction.remove_mesh(body)
            body = cut
        after = inspect(body)
        removed = before.volume_mm3 - after.volume_mm3
        if (after.shells != before.shells or abs(removed - expected) > max(VOLUME_EPSILON, expected * .01)):
            raise MeshError("The magnet pockets could not be cut cleanly.")
        bodies.append(body)
    for mesh in (minus, plus):
        engine.transaction.remove_mesh(mesh)
    return ConnectorResult(tuple(bodies), tuple(centers))
