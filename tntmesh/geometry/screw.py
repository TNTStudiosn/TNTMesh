# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import ceil, cos, hypot, isfinite, pi, sin

import bpy
from mathutils import Matrix, Vector

from ..localization import tr
from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean, measure_intersection
from .connector import ConnectorResult, candidates, profile_prism
from .connector_profiles import regular_profile
from .mesh import BOOLEAN_VOLUME_NOISE, inspect, primitive, weld_collapsed_edges
from .polygon import Point2

SIDES = 64
NUT_FACTOR = cos(pi / 6)
IDENTITY = Matrix.Identity(3).freeze()
ACCESS_ERROR = "The screw and nut need unobstructed exterior seats with enough surrounding wall."


def circular(radius: float) -> tuple[Point2, ...]:
    return regular_profile(radius / cos(pi / SIDES), SIDES)


@dataclass(frozen=True)
class Screw:
    diameter: float
    length: float
    pitch: float
    head_width: float
    head_height: float
    nut_width: float
    nut_height: float
    angle: float
    lateral: float
    axial: float
    wall: float
    count: int

    def validate(self) -> None:
        sizes = (self.diameter, self.length, self.pitch, self.head_width, self.head_height,
                 self.nut_width, self.nut_height, self.wall)
        if (not all(map(isfinite, (*sizes, self.angle, self.lateral, self.axial))) or min(sizes) <= 0
                or min(self.lateral, self.axial) < 0 or self.count < 1):
            raise MeshError("Check the screw, head and nut dimensions.")
        if min(self.head_width, self.nut_width) <= self.diameter + 2 * self.lateral:
            raise MeshError("Leave a bearing shoulder around the screw bore.")
        if self.nut_width / 2 + self.lateral >= self.nut_width / (2 * NUT_FACTOR):
            raise MeshError("Reduce side clearance so the hex nut cannot turn inside its seat.")

    def reflected(self, _axis: str) -> "Screw":
        return replace(self, angle=-self.angle)

    def profile(self, side: int, padding: float) -> tuple[Point2, ...]:
        if side < 0:
            return circular(self.head_width / 2 + padding)
        radius = (self.nut_width / 2 + padding) / NUT_FACTOR
        c, s = cos(self.angle), sin(self.angle)
        return tuple((x * c - y * s, x * s + y * c) for x, y in regular_profile(radius, 6))

    @property
    def envelope(self) -> float:
        return max(hypot(*p) for side in (-1, 1) for p in self.profile(side, self.lateral + self.wall))


@dataclass(frozen=True)
class ScrewSeat:
    center: Vector
    head: float
    nut: float


def local_bodies(
    tx: GeometryTransaction, bodies: tuple[bpy.types.Mesh, bpy.types.Mesh], frame: Matrix,
    position: float, kerf: float, epsilon: float,
) -> tuple[bpy.types.Mesh, bpy.types.Mesh]:
    inverse = frame.transposed().to_4x4()
    local = tuple(tx.own_mesh(body.copy()) for body in bodies)
    for body, sign in zip(local, (-1, 1), strict=True):
        boundary = position + sign * kerf / 2
        body.transform(inverse)
        for vertex in body.vertices:
            if abs(vertex.co.z - boundary) < epsilon:
                vertex.co.z = boundary
        body.update()
    return local


def find_seat(
    engine: ExactBoolean, body: bpy.types.Mesh, center: Vector, sign: int,
    seam: float, far: float, design: Screw, epsilon: float,
) -> float:
    guard = design.profile(sign, design.lateral + design.wall)
    near = seam + sign * epsilon
    with GeometryTransaction() as temporary:
        exact = ExactBoolean(engine.context, temporary)
        column = profile_prism(temporary, IDENTITY, center, *sorted((near, far)), guard)
        filled = exact.run(body, column, "INTERSECT")
        if not filled.polygons:
            raise MeshError(ACCESS_ERROR)
        exits = []
        for face in filled.polygons:
            level = tuple(filled.vertices[index].co.z for index in face.vertices)
            facing = sign * face.normal.z
            if facing < -1e-5 and any(abs(z - near) > epsilon for z in level):
                raise MeshError(ACCESS_ERROR)
            if facing > 1e-5:
                exits.extend(sign * z for z in level)
        height = design.head_height if sign < 0 else design.nut_height
        if not exits:
            raise MeshError(ACCESS_ERROR)
        outer = min(exits)
        seat = outer - height - design.axial
        if seat <= sign * seam + design.wall + epsilon:
            raise MeshError(ACCESS_ERROR)
        # Up to the first exterior surface the complete footprint must be
        # solid. Above that level, the inward-face check rejects re-entry.
        solid = profile_prism(temporary, IDENTITY, center, *sorted((near, sign * (outer - epsilon))), guard)
        missing = exact.run(solid, body, "DIFFERENCE")
        if missing.polygons:
            raise MeshError(ACCESS_ERROR)
        return sign * seat


def layout(
    engine: ExactBoolean, bodies: tuple[bpy.types.Mesh, bpy.types.Mesh], position: float,
    kerf: float, design: Screw, epsilon: float, requested: tuple[Vector, ...] | None,
) -> tuple[list[ScrewSeat], tuple[float, float]]:
    design.validate()
    inset = min(epsilon, design.wall / 20)
    low, high = position - kerf / 2, position + kerf / 2
    # Cross the exterior decisively. A cutter ending within the float error
    # of the surface can leave a zero-thickness cap across a through-bore.
    overreach = max(16 * epsilon, min(design.wall, design.diameter) / 10)
    far = (min(v.co.z for v in bodies[0].vertices) - overreach,
           max(v.co.z for v in bodies[1].vertices) + overreach)
    search = requested if requested is not None else candidates(bodies[0], IDENTITY, low, epsilon * 2)
    seats = []
    spacing = 2 * design.envelope
    error = MeshError(ACCESS_ERROR)
    for center in search:
        if not all(map(isfinite, center)):
            raise MeshError("Check the screw positions.")
        if any((center - seat.center).length < spacing for seat in seats):
            if requested is not None:
                raise MeshError("The screw seats overlap. Increase their spacing.")
            continue
        try:
            head = find_seat(engine, bodies[0], center, -1, low, far[0], design, inset)
            nut = find_seat(engine, bodies[1], center, 1, high, far[1], design, inset)
            minimum = nut - head + design.nut_height + design.pitch
            if design.length + inset < minimum:
                length = ceil((minimum - inset) * 100) / 100
                raise MeshError(tr("Use a screw at least {size:.2f} mm long at this position.").format(size=length))
        except MeshError as problem:
            if requested is not None:
                raise
            error = problem
            continue
        seats.append(ScrewSeat(center, head, nut))
        if len(seats) == design.count:
            return seats, far
    raise error


def cut_batch(
    engine: ExactBoolean, body: bpy.types.Mesh, profile: tuple[Point2, ...],
    ranges: list[tuple[Vector, float, float]],
) -> bpy.types.Mesh:
    tx = engine.transaction
    vertices = []
    faces = []
    for center, start, end in ranges:
        offset = len(vertices)
        tool = profile_prism(tx, IDENTITY, center, start, end, profile)
        vertices.extend(v.co.copy() for v in tool.vertices)
        faces.extend(tuple(offset + vertex for vertex in face.vertices) for face in tool.polygons)
        tx.remove_mesh(tool)
    tool = primitive(tx, ".TNTMesh screw cutter", vertices, faces)
    carved = engine.run(body, tool, "DIFFERENCE")
    tx.remove_mesh(tool)
    weld_collapsed_edges(carved)
    return carved


def add_screws(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: Screw, epsilon: float, requested: tuple[Vector, ...] | None = None,
    obstacle: bpy.types.Mesh | None = None,
) -> ConnectorResult:
    tx = engine.transaction
    bodies = local_bodies(tx, (minus, plus), frame, position, kerf, epsilon)
    seats, far = layout(engine, bodies, position, kerf, design, epsilon, requested)
    output = []
    for side, body, exterior in zip((-1, 1), bodies, far, strict=True):
        before = inspect(body)
        drilled = cut_batch(engine, body, circular(design.diameter / 2 + design.lateral),
                            [(seat.center, *far) for seat in seats])
        carved = cut_batch(engine, drilled, design.profile(side, design.lateral), [
            (seat.center, *sorted((exterior, seat.head if side < 0 else seat.nut))) for seat in seats
        ])
        after = inspect(carved)
        if after.shells != before.shells or before.volume_mm3 - after.volume_mm3 <= BOOLEAN_VOLUME_NOISE:
            raise MeshError("The screw holes or bearing seats could not be cut cleanly.")
        for mesh in (body, drilled):
            tx.remove_mesh(mesh)
        output.append(carved)

    access = far
    blockers = list(output)
    if obstacle is not None:
        third = tx.own_mesh(obstacle.copy())
        third.transform(frame.transposed().to_4x4())
        third.update()
        access = (min(far[0], min(vertex.co.z for vertex in third.vertices) - epsilon),
                  max(far[1], max(vertex.co.z for vertex in third.vertices) + epsilon))
        blockers.append(third)
    # Leave a mesh-coordinate tolerance on coplanar bearing faces and stock
    # set to zero clearance. The drilled profiles keep their exact dimensions.
    tolerance = min(epsilon, design.diameter / 100)
    for seat in seats:
        probes = (
            (access[0], max(access[1], seat.head + design.length), circular(design.diameter / 2 - tolerance)),
            (access[0], seat.head - tolerance, design.profile(-1, -tolerance)),
            (seat.nut + tolerance, access[1], design.profile(1, -tolerance)),
        )
        for start, end, profile in probes:
            probe = profile_prism(tx, IDENTITY, seat.center, start, end, profile)
            blocked = any(measure_intersection(engine, probe, body) for body in blockers)
            tx.remove_mesh(probe)
            if blocked:
                raise MeshError("Hardware is obstructed along the screw axis.")
    if obstacle is not None:
        tx.remove_mesh(third)
    tx.remove_mesh(minus)
    tx.remove_mesh(plus)
    for body in output:
        body.transform(frame.to_4x4())
        body.update()
    return ConnectorResult(tuple(output), tuple(seat.center for seat in seats))
