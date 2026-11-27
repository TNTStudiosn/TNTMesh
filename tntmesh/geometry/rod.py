# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import cos, hypot, isfinite, pi, sin

import bpy
from mathutils import Matrix, Vector

from ..model import MeshError
from .boolean import ExactBoolean, measure_intersection
from .connector import ConnectorResult, profile_prism, safe_centers
from .connector_profiles import area, regular_profile
from .mesh import BOOLEAN_VOLUME_NOISE, inspect, primitive, weld_collapsed_edges
from .polygon import Point2

ROUND_SIDES = 64


@dataclass(frozen=True)
class Rod:
    shape: str
    size: float
    depth_minus: float
    depth_plus: float
    angle: float
    lateral: float
    axial: float
    wall: float
    count: int

    def validate(self) -> None:
        sizes = (self.size, self.depth_minus, self.depth_plus, self.wall)
        if (self.shape not in {"ROUND", "SQUARE"} or not all(map(isfinite, (*sizes, self.angle, self.lateral, self.axial)))
                or min(sizes) <= 0 or min(self.lateral, self.axial) < 0 or self.count < 1):
            raise MeshError("Check the rod size, insertion depths and clearances.")
        if self.axial >= min(self.depth_minus, self.depth_plus):
            raise MeshError("Reduce the rod's axial clearance so it still engages both pieces.")

    def length(self, kerf: float) -> float:
        return self.depth_minus + kerf + self.depth_plus

    def reflected(self, _axis: str) -> "Rod":
        return replace(self, angle=-self.angle)

    def profile(self, padding: float) -> tuple[Point2, ...]:
        half = self.size / 2 + padding
        if self.shape == "ROUND":
            # The flat sides of the bore clear the circumference of the stock.
            return regular_profile(half / cos(pi / ROUND_SIDES), ROUND_SIDES)
        c, s = cos(self.angle), sin(self.angle)
        return tuple((half * (x * c - y * s), half * (x * s + y * c))
                     for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)))

    @property
    def envelope(self) -> float:
        return max(hypot(*point) for point in self.profile(self.lateral + self.wall))


def rod_centers(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: Rod, epsilon: float, requested: tuple[Vector, ...] | None,
) -> list[Vector]:
    design.validate()
    padding = design.axial + design.wall
    return safe_centers(
        engine, minus, plus, frame, (position - kerf / 2, position + kerf / 2),
        (design.depth_minus + padding, design.depth_plus + padding), design.profile(design.lateral + design.wall),
        epsilon, min(epsilon, design.wall / 10), design.count, requested, footprint_spacing=design.shape == "SQUARE",
    )


def add_rod_sockets(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: Rod, epsilon: float, requested: tuple[Vector, ...] | None = None,
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
    centers = rod_centers(engine, minus, plus, identity, position, kerf, design, epsilon, requested)
    tx = engine.transaction
    inset = min(epsilon, design.wall / 10)
    socket_profile = design.profile(design.lateral)
    stock_profile = design.profile(0)
    depth_minus, depth_plus = design.depth_minus + design.axial, design.depth_plus + design.axial
    bodies = []
    for body, depth, start, end in (
        (minus, depth_minus, low - depth_minus, low + inset),
        (plus, depth_plus, high - inset, high + depth_plus),
    ):
        before = inspect(body)
        # The guards keep these cutters disjoint. A single Difference avoids
        # repeatedly tessellating the cut face and the edges of earlier bores.
        template = profile_prism(tx, identity, Vector((0, 0, 0)), start, end, socket_profile)
        stride = len(template.vertices)
        vertices = [vertex.co + center for center in centers for vertex in template.vertices]
        faces = [tuple(index * stride + vertex for vertex in face.vertices)
                 for index in range(len(centers)) for face in template.polygons]
        tx.remove_mesh(template)
        tool = primitive(tx, ".TNTMesh rod socket tool", vertices, faces)
        result = engine.run(body, tool, "DIFFERENCE")
        tx.remove_mesh(body)
        tx.remove_mesh(tool)
        weld_collapsed_edges(result)
        after = inspect(result)
        expected = area(socket_profile) * depth * len(centers)
        if (before.shells != after.shells
                or abs(before.volume_mm3 - after.volume_mm3 - expected) > max(BOOLEAN_VOLUME_NOISE, expected * .005)):
            raise MeshError("The rod sockets could not be cut cleanly.")
        bodies.append(result)

    # The sweep between the two farthest seated poses must be empty.
    for center in centers:
        travel = profile_prism(tx, identity, center, low - depth_minus, high + depth_plus, stock_profile)
        obstructed = any(measure_intersection(engine, travel, body) for body in bodies)
        tx.remove_mesh(travel)
        if obstructed:
            raise MeshError("The rod cannot pass through both sockets along the cut normal.")

    if frame != identity:
        transform = frame.to_4x4()
        for body in bodies:
            body.transform(transform)
            body.update()
    return ConnectorResult(tuple(bodies), tuple(centers))
