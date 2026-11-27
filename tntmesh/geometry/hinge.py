# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import cos, degrees, isfinite, pi

import bpy
from mathutils import Matrix, Vector

from ..localization import tr
from ..model import HINGE_AXIS, HINGE_OPENING, HINGE_PIVOT, SLIDE_DIRECTION, MeshError
from .boolean import ExactBoolean, measure_intersection
from .connector import profile_loft, profile_prism
from .connector_profiles import regular_profile
from .mesh import bounds, inspect
from .sweep import RotarySweep, rotation_probes
from .triangle_bounds import Box

SIDES = 48
POLYGON_INRADIUS = cos(pi / SIDES)
SWING_SAMPLE_MM = 1.0


@dataclass(frozen=True)
class Hinge:
    diameter: float
    pin_diameter: float
    width: float
    knuckles: int
    stand_off: float
    angle: float
    shift: float
    opening: float
    lateral: float
    axial: float
    wall: float

    @property
    def bearing(self) -> float:
        return self.diameter / 2

    @property
    def bore(self) -> float:
        return (self.pin_diameter / 2 + self.lateral) / POLYGON_INRADIUS

    @property
    def head(self) -> float:
        return self.bore + self.wall / 2

    @property
    def knuckle_width(self) -> float:
        return (self.width - (self.knuckles - 1) * self.axial) / self.knuckles

    def validate(self, kerf: float) -> None:
        values = (
            self.diameter, self.pin_diameter, self.width, self.stand_off, self.angle,
            self.shift, self.opening, self.lateral, self.axial, self.wall, kerf,
        )
        if (not all(map(isfinite, values)) or min(self.pin_diameter, self.diameter,
                                                self.lateral, self.axial, self.wall) <= 0
                or not 3 <= self.knuckles <= 32 or not 0 < self.opening <= pi + 1e-6):
            raise MeshError("Check hinge dimensions, clearances and opening angle.")
        if self.bearing * POLYGON_INRADIUS - self.bore < self.wall or self.knuckle_width < self.wall:
            raise MeshError("Increase the hinge dimensions or reduce the clearances to preserve the bearing wall.")
        if self.stand_off <= self.head:
            raise MeshError("Increase the hinge offset so the axle head clears the outside edge.")
        if kerf / 2 + self.wall / 4 >= self.bearing * POLYGON_INRADIUS:
            raise MeshError("Reduce cut separation so the hinge can reach both sides.")


def hinge_frame(frame: Matrix, angle: float) -> Matrix:
    return frame @ Matrix.Rotation(angle, 3, "Z")


def validate_swing(
    engine: ExactBoolean, fixed: bpy.types.Mesh, moving: bpy.types.Mesh,
    pivot: Vector, axis: Vector, opening: float,
) -> None:
    fixed_box = Box(*bounds(vertex.co for vertex in fixed.vertices), [], 0)
    points = [vertex.co.copy() for vertex in moving.vertices]
    moving_box = Box(*bounds(points), [], 0)
    sweep = RotarySweep.make(moving_box, pivot, axis, Vector((0, 0, 0)), opening)
    probe = engine.transaction.own_mesh(moving.copy())
    try:
        for step in rotation_probes(sweep, fixed_box, 0, SWING_SAMPLE_MM):
            rotation, offset = sweep.pose(step)
            for vertex, original in zip(probe.vertices, points, strict=True):
                vertex.co = rotation @ original + offset
            probe.update()
            if measure_intersection(engine, probe, fixed):
                raise MeshError(tr("The hinge collides near {angle:.1f}°. Reduce its opening or move the hinge.").format(
                    angle=degrees(opening * step),
                ))
    finally:
        engine.transaction.remove_mesh(probe)


def add_hinge(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, frame: Matrix,
    position: float, kerf: float, design: Hinge, epsilon: float,
) -> tuple[bpy.types.Mesh, bpy.types.Mesh, bpy.types.Mesh]:
    design.validate(kerf)
    work = hinge_frame(frame, design.angle)
    inverse = work.transposed()
    lower, upper = bounds(inverse @ vertex.co for piece in (minus, plus) for vertex in piece.vertices)
    edge = upper.x
    along = (lower.y + upper.y) / 2 + design.shift
    start = along - design.width / 2
    end = along + design.width / 2
    if start <= lower.y + epsilon or end >= upper.y - epsilon:
        raise MeshError("The hinge span must fit inside the model's edge.")
    pivot_x = edge + design.stand_off
    pivot = work @ Vector((pivot_x, along, position))
    # Radial X, radial -Z and axial Y form a right-handed coordinate system.
    barrel_frame = Matrix((work.col[0], -work.col[2], work.col[1])).transposed()
    center = Vector((pivot_x, -position, 0))
    transaction = engine.transaction
    bodies = [minus, plus]
    shell_counts = [inspect(piece).shells for piece in bodies]
    radius = design.bearing
    relief = (radius + design.lateral) / POLYGON_INRADIUS
    barrel_profile = regular_profile(radius, SIDES)
    relief_profile = regular_profile(relief, SIDES)
    root = edge - 2 * design.wall
    near = kerf / 2 + design.wall / 4
    far = near + 2 * design.wall
    clearance = design.axial * .45

    def rectangle(x0: float, x1: float, low: float, high: float) -> tuple[tuple[float, float], ...]:
        return ((x0, low), (x1, low), (x1, high), (x0, high))

    for index in range(design.knuckles):
        side = index % 2
        a = start + index * (design.knuckle_width + design.axial)
        b = a + design.knuckle_width
        radial_low, radial_high = (-far, -near) if side else (near, far)
        anchor = profile_prism(transaction, barrel_frame, Vector((0, -position, 0)), a, b,
                               rectangle(root, edge - design.wall / 2, radial_low, radial_high))
        outside = engine.run(anchor, bodies[side], "DIFFERENCE")
        if outside.polygons:
            raise MeshError("The hinge needs solid material at every knuckle. Move it or reduce its span.")
        barrel = profile_prism(transaction, barrel_frame, center, a, b, barrel_profile)
        channel = profile_prism(transaction, barrel_frame, center, a - clearance, b + clearance, relief_profile)
        tab = profile_prism(transaction, barrel_frame, Vector((0, -position, 0)), a, b,
                            rectangle(root, pivot_x, radial_low, radial_high))
        mount = engine.run(barrel, tab, "UNION")
        joined = engine.run(bodies[side], mount, "UNION")
        carved = engine.run(bodies[1 - side], channel, "DIFFERENCE")
        for mesh in (anchor, outside, barrel, channel, tab, mount, *bodies):
            transaction.remove_mesh(mesh)
        bodies[side], bodies[1 - side] = joined, carved

    left, right = start - design.axial, end + design.axial
    bore = profile_prism(transaction, barrel_frame, center, left - design.wall, right + design.wall,
                         regular_profile(design.bore, SIDES))
    fixed, moving = (engine.run(body, bore, "DIFFERENCE") for body in bodies)
    for mesh in (*bodies, bore):
        transaction.remove_mesh(mesh)
    if [inspect(body).shells for body in (fixed, moving)] != shell_counts:
        raise MeshError("A hinge knuckle detached or the axle bore broke through its housing.")

    pin_radius = design.pin_diameter / 2
    head = regular_profile(design.head, SIDES)
    shank = regular_profile(pin_radius, SIDES)
    nose = regular_profile(pin_radius * .8, SIDES)
    pin = profile_loft(transaction, barrel_frame, center, (
        (left - design.wall, head), (left, head), (left, shank),
        (right - min(.4, pin_radius / 2), shank), (right, nose),
    ))
    inspect(pin)
    if any(measure_intersection(engine, pin, body) for body in (fixed, moving)):
        raise MeshError("The axle does not clear the hinge bearings.")
    if measure_intersection(engine, fixed, moving):
        raise MeshError("The hinge bodies overlap at the assembled position.")
    axis = work.col[1]
    validate_swing(engine, fixed, moving, pivot, axis, design.opening)
    moving[HINGE_PIVOT], moving[HINGE_AXIS], moving[HINGE_OPENING] = tuple(pivot), tuple(axis), design.opening
    pin[SLIDE_DIRECTION] = tuple(-axis)
    return fixed, moving, pin
