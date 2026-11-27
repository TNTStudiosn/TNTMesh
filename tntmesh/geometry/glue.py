# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import cos, hypot, isfinite, pi, sin

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..model import MeshError
from .boolean import ExactBoolean
from .connector import Connector, ConnectorPlacementError, profile_loft, profile_prism
from .connector_profiles import regular_profile
from .mesh import BOOLEAN_VOLUME_NOISE, inspect, weld_collapsed_edges
from .polygon import Point2


@dataclass(frozen=True)
class GlueAssist:
    channels: bool = False
    reservoir: bool = False
    vent: bool = False
    chamfer: bool = False
    texture: bool = False
    relief: float = .35
    angle: float = 0

    def validate(self, design: Connector) -> None:
        if not all(map(isfinite, (self.relief, self.angle))) or not .05 <= self.relief <= design.insertion / 4:
            raise MeshError("Set glue relief between 0.05 mm and one quarter of the insertion depth.")

    def reflected(self, axis: str) -> "GlueAssist":
        return replace(self, angle=(pi if axis == "X" else 0) - self.angle)

    def guard_radius(self, design: Connector) -> float:
        expanded = max(hypot(*point) for point in design.profile(design.lateral + self.relief))
        return max(expanded, design.socket_radius + 2 * self.relief) + design.wall

    def guard(self, design: Connector) -> tuple[Point2, ...]:
        return regular_profile(self.guard_radius(design) / cos(pi / 64), 64)

    def depths(self, design: Connector) -> tuple[float, float]:
        low, high = design.depths
        extra = 0.0
        if self.reservoir:
            extra = self.relief
        elif self.channels or self.vent:
            extra = min(.05, self.relief / 5)
        return low + (extra if design.loose else 0), high + extra


def radial_extent(profile: tuple[Point2, ...], direction: Vector) -> float:
    # Each standard profile encloses its origin. Find the first boundary on the ray.
    reaches = []
    for a, b in zip(profile, (*profile[1:], profile[0]), strict=True):
        vx, vy = b[0] - a[0], b[1] - a[1]
        denominator = direction.x * vy - direction.y * vx
        if abs(denominator) < 1e-10:
            continue
        along = (a[0] * vy - a[1] * vx) / denominator
        edge = (a[0] * direction.y - a[1] * direction.x) / denominator
        if along > 0 and -1e-6 <= edge <= 1 + 1e-6:
            reaches.append(along)
    if not reaches:
        raise MeshError("The glue channel could not find the socket wall.")
    return min(reaches)


def strip(direction: Vector, low: float, high: float, half_width: float) -> tuple[Point2, ...]:
    across = Vector((-direction.y, direction.x, 0))
    return tuple(tuple((direction * a + across * b).xy) for a, b in (
        (low, -half_width), (high, -half_width), (high, half_width), (low, half_width),
    ))


def outlet(
    engine: ExactBoolean, body: bpy.types.Mesh, frame: Matrix, center: Vector, face: float,
    design: Connector, glue: GlueAssist, points: list[Vector], direction: Vector, epsilon: float,
) -> bpy.types.Mesh:
    # Cast in the same coordinates as the tools. A second crossing can mean a
    # cavity or another lobe lies between the first hit and the actual exterior.
    body.calc_loop_triangles()
    tree = BVHTree.FromPolygons(
        [vertex.co for vertex in body.vertices], [tuple(triangle.vertices) for triangle in body.loop_triangles],
        all_triangles=True,
    )
    axis = frame @ direction
    tangent = Vector((-direction.y, direction.x, 0))
    width = .75 * glue.relief
    offset = max(epsilon * 8, 1e-4)
    exits = []
    for across in (-width, 0, width):
        for height in (.2 * glue.relief, glue.relief, glue.relief + design.wall):
            start = frame @ (center + tangent * across + Vector((0, 0, face + height)))
            point, normal, _, distance = tree.ray_cast(start, axis)
            if point is None or normal.dot(axis) <= 0 or tree.ray_cast(point + axis * offset, axis)[0] is not None:
                raise ConnectorPlacementError("The glue vent needs a direct path to an outside edge.")
            exits.append(distance)

    protected = glue.guard_radius(design)
    for other in points:
        if other == center:
            continue
        delta = other - center
        along = min(max(delta.dot(direction), 0), max(exits))
        if (delta - direction * along).length < protected + width:
            raise ConnectorPlacementError("The glue vent passes too close to another socket. Rotate or move it.")

    interior = min(exits) - design.wall
    if interior <= design.socket_radius + width + epsilon:
        raise ConnectorPlacementError("The glue vent leaves too little material next to the socket.")
    tx = engine.transaction
    guard = profile_prism(tx, frame, center, face + min(epsilon, width / 10),
                          face + glue.relief + design.wall, strip(direction, 0, interior, width + design.wall))
    outside = engine.run(guard, body, "DIFFERENCE")
    try:
        if outside.polygons:
            raise ConnectorPlacementError("The glue vent leaves too little material below or beside the outlet.")
    finally:
        tx.remove_mesh(outside)
        tx.remove_mesh(guard)
    return profile_prism(tx, frame, center, face - epsilon, face + glue.relief,
                         strip(direction, 0, max(exits) + design.wall, width))


def carve_socket(
    engine: ExactBoolean, body: bpy.types.Mesh, frame: Matrix, center: Vector, face: float,
    design: Connector, glue: GlueAssist, centers: list[Vector], epsilon: float,
) -> tuple[bpy.types.Mesh, float]:
    tx = engine.transaction
    depth = design.insertion + design.axial
    floor = face + depth
    start = face - epsilon * 2
    relief = glue.relief
    original = design.sections(start, floor, face, face, design.lateral)
    levels = {level for level, _ in original}
    bands = tuple(face + design.insertion * fraction for fraction in (.25, .5, .75)) if glue.texture else ()
    levels.update(level + offset for level in bands for offset in (-relief / 2, 0, relief / 2))
    if glue.chamfer:
        levels.add(face + relief)
    if glue.reservoir:
        levels.update((floor - relief, floor + relief))

    def padding(z: float) -> float:
        bevel = max(0, relief - max(0, z - face)) if glue.chamfer else 0
        reservoir = min(relief, max(0, z - floor + relief)) if glue.reservoir else 0
        texture = max((max(0, relief - 2 * abs(z - level)) / 3 for level in bands), default=0)
        return max(bevel, reservoir, texture)

    # Use one loft for all radial relief to avoid coincident cylindrical walls
    # between separate cutters and keep the taper continuous.
    tool = profile_loft(tx, frame, center, tuple(
        (z, design.profile_at(z, face, face, design.lateral + padding(z)))
        for z in sorted(levels)
    ))
    features = [tool]
    angles = (glue.angle + pi / 2, glue.angle - pi / 2) if glue.channels else ()
    exit_tool = None
    if glue.vent:
        direction = Vector((cos(glue.angle), sin(glue.angle), 0))
        exit_tool = outlet(engine, body, frame, center, face, design, glue, centers, direction, epsilon)
        angles += (glue.angle,)
    # Extend the slots past the nominal floor so glue and air can escape
    # beside a fully seated pin without a coplanar Boolean at the bottom.
    slot_floor = floor + min(.05, relief / 5)
    slot_profile = design.sections(start - epsilon, slot_floor, face, face, design.lateral)
    for angle in angles:
        direction = Vector((cos(angle), sin(angle), 0))
        sections = tuple(
            (z, strip(direction, 0, radial_extent(ring, direction) + glue.relief, glue.relief))
            for z, ring in slot_profile
        )
        features.append(profile_loft(tx, frame, center, sections))
    if exit_tool is not None:
        features.append(exit_tool)
    carved, volume = body, 0.0
    for feature in features:
        removed = engine.run(carved, feature, "INTERSECT")
        weld_collapsed_edges(removed)
        if removed.polygons:
            stats = inspect(removed)
            # A channel can shave separate patches on a concave socket.
            # The caller validates the resulting body's shell count after carving.
            updated = engine.run(carved, feature, "DIFFERENCE")
            weld_collapsed_edges(updated)
            if carved != body:
                tx.remove_mesh(carved)
            carved = updated
            volume += stats.volume_mm3
        tx.remove_mesh(removed)
        tx.remove_mesh(feature)
    if volume <= BOOLEAN_VOLUME_NOISE:
        raise MeshError("The glue features did not remove material from the socket.")
    return carved, volume
