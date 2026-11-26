# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass
from math import pi, sin, sqrt
from typing import Protocol

from mathutils import Quaternion, Vector

from ..model import MeshError
from .mesh import bounds
from .triangle_bounds import Box, Triangle

DISTANCE_EPSILON = 1e-5
AXIS_EPSILON = 1e-14
MAX_ROTARY_INTERVALS = 32768
ROTATION_LIMIT_ERROR = "Rotation scan exceeded its limit. Increase the sample distance or shorten the path."
Window = tuple[float, float]


class Bounded(Protocol):
    @property
    def lower(self) -> Vector: ...

    @property
    def upper(self) -> Vector: ...


@dataclass(frozen=True)
class RotarySweep:
    corners: tuple[Vector, ...]
    pivot: Vector
    axis: Vector
    travel: Vector
    angle: float
    radius: float
    projected_radius: Vector

    @classmethod
    def make(cls, box: Bounded, pivot: Vector, axis: Vector, travel: Vector, angle: float) -> "RotarySweep":
        corners = tuple(Vector((x, y, z)) for x in (box.lower.x, box.upper.x)
                        for y in (box.lower.y, box.upper.y) for z in (box.lower.z, box.upper.z))
        unit_axis = axis.normalized()
        radius = max((corner - pivot).cross(unit_axis).length for corner in corners)
        projected = Vector(sqrt(max(0.0, 1.0 - value**2)) * radius for value in unit_axis)
        return cls(corners, pivot, unit_axis, travel, angle, radius, projected)

    def pose(self, fraction: float) -> tuple[Quaternion, Vector]:
        rotation = Quaternion(self.axis, self.angle * fraction)
        offset = self.pivot - rotation @ self.pivot + self.travel * fraction
        return rotation, offset

def rotation_probes(
    sweep: RotarySweep, obstacle: Bounded, minimum: float, sample_mm: float,
) -> Iterator[float]:
    pending = [(minimum, 1.0)]
    last = None
    iterations = 0
    while pending:
        iterations += 1
        if iterations > MAX_ROTARY_INTERVALS:
            raise MeshError(ROTATION_LIMIT_ERROR)
        low, high = pending.pop()
        middle = (low + high) / 2
        rotation, offset = sweep.pose(middle)
        lower, upper = bounds(rotation @ corner + offset for corner in sweep.corners)
        # Bound each coordinate of the motion away from the midpoint. Rotation has
        # zero movement along its axis, even when the chosen pivot is far away.
        half_span = (high - low) / 2
        angle = min(pi, abs(sweep.angle) * half_span)
        chord = 2 * sin(angle / 2)
        margins = [abs(sweep.travel[i]) * half_span + sweep.projected_radius[i] * chord for i in range(3)]
        if any(lower[i] - margins[i] > obstacle.upper[i] or upper[i] + margins[i] < obstacle.lower[i]
               for i in range(3)):
            continue
        if sweep.travel.length * half_span + sweep.radius * chord > sample_mm:
            pending.extend(((low, middle), (middle, high)))
            continue
        for sample in (high, middle, low):
            if sample != last:
                yield sample
                last = sample


def clip_interval(window: Window, low: float, high: float, speed: float) -> Window | None:
    if abs(speed) < 1e-12:
        return window if low <= DISTANCE_EPSILON and high >= -DISTANCE_EPSILON else None
    start, end = sorted((low / speed, high / speed))
    start, end = max(window[0], start), min(window[1], end)
    if start > end:
        if start - end > DISTANCE_EPSILON:
            return None
        boundary = max(window[0], min(window[1], end))
        return boundary, boundary
    return start, end


def box_interval(
    moving: Bounded, obstacle: Bounded, direction: Vector, window: Window,
) -> Window | None:
    for i in range(3):
        overlap = clip_interval(
            window, obstacle.lower[i] - moving.upper[i] - DISTANCE_EPSILON,
            obstacle.upper[i] - moving.lower[i] + DISTANCE_EPSILON, direction[i],
        )
        if overlap is None:
            return None
        window = overlap
    return window


def edges(triangle: Triangle) -> tuple[Vector, Vector, Vector]:
    a, b, c = triangle.points
    return (b - a).normalized(), (c - b).normalized(), (a - c).normalized()


def separating_axes(moving: Triangle, obstacle: Triangle) -> Iterator[Vector]:
    yield moving.normal
    yield obstacle.normal
    first = edges(moving)
    second = edges(obstacle)
    if moving.normal.cross(obstacle.normal).length_squared <= AXIS_EPSILON:
        for edge in (*first, *second):
            yield moving.normal.cross(edge)
    else:
        for a in first:
            for b in second:
                cross = a.cross(b)
                if cross.length_squared > AXIS_EPSILON:
                    yield cross.normalized()


def triangle_interval(
    moving: Triangle, obstacle: Triangle, direction: Vector, window: Window,
) -> Window | None:
    # Project onto the separating axes of the two triangles, then intersect the
    # intervals where each pair of projections overlaps under translation.
    # David Eberly, Dynamic Collision Detection Using OBBs, section 4.
    origin = moving.points[0]
    first = [point - origin for point in moving.points]
    second = [point - origin for point in obstacle.points]
    for axis in separating_axes(moving, obstacle):
        a = [axis.dot(point) for point in first]
        b = [axis.dot(point) for point in second]
        overlap = clip_interval(window, min(b) - max(a), max(b) - min(a), axis.dot(direction))
        if overlap is None:
            return None
        window = overlap
    return window


def contact_intervals(
    moving: Box, obstacle: Box, direction: Vector, window: Window,
) -> Iterator[Window]:
    overlap = box_interval(moving, obstacle, direction, window)
    if overlap is None:
        return
    if moving.children and (not obstacle.children or
                            (moving.upper - moving.lower).length_squared
                            >= (obstacle.upper - obstacle.lower).length_squared):
        for child in moving.children:
            yield from contact_intervals(child, obstacle, direction, overlap)
    elif obstacle.children:
        for child in obstacle.children:
            yield from contact_intervals(moving, child, direction, overlap)
    else:
        for first in moving.items:
            for second in obstacle.items:
                broad = box_interval(first, second, direction, overlap)
                if broad is not None:
                    contact = triangle_interval(first, second, direction, broad)
                    if contact is not None:
                        yield contact


def probe_positions(
    moving: Box, obstacle: Box, direction: Vector, window: Window, steps: int, travel: float,
) -> Iterator[float]:
    low, high = window
    yield high
    distances = {low, high}
    for start, end in contact_intervals(moving, obstacle, direction, window):
        distances.update((max(low, start), min(high, end)))
    for i in range(1, steps):
        sample = i * travel / steps
        if low < sample < high:
            distances.add(sample)
    # Contact events partition the path. Test the open intervals to distinguish
    # actual interior overlap from a point, edge or face that merely touches.
    last = high
    for distance in sorted(distances, reverse=True):
        if last - distance > DISTANCE_EPSILON:
            yield (last + distance) / 2
            yield distance
            last = distance
    if last != low:
        yield low
