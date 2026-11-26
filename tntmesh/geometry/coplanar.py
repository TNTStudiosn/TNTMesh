# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass

import bpy
from mathutils import Vector

from .polygon import Point2, signed_turn

DISTANCE_EPSILON = .00001
AREA_EPSILON = DISTANCE_EPSILON**2
LEAF_SIZE = 8


@dataclass(frozen=True)
class Triangle:
    face: int
    points: tuple[Vector, Vector, Vector]
    normal: Vector
    lower: Vector
    upper: Vector


@dataclass
class Box:
    lower: Vector
    upper: Vector
    items: list[Triangle]
    children: tuple["Box", "Box"] | None = None


def combined_limits(items: list[Triangle]) -> tuple[Vector, Vector]:
    lower = Vector(tuple(min(item.lower[axis] for item in items) for axis in range(3)))
    upper = Vector(tuple(max(item.upper[axis] for item in items) for axis in range(3)))
    return lower, upper


def hierarchy(items: list[Triangle]) -> Box:
    lower, upper = combined_limits(items)
    if len(items) <= LEAF_SIZE:
        return Box(lower, upper, items)
    longest = max(range(3), key=lambda axis: upper[axis] - lower[axis])
    items.sort(key=lambda item: item.lower[longest] + item.upper[longest])
    middle = len(items) // 2
    return Box(lower, upper, [], (hierarchy(items[:middle]), hierarchy(items[middle:])))


def touches(a: Box | Triangle, b: Box | Triangle) -> bool:
    return all(max(a.lower[axis], b.lower[axis]) <= min(a.upper[axis], b.upper[axis]) + DISTANCE_EPSILON
               for axis in range(3))


def clipped_area(subject: tuple[Point2, ...], clip: tuple[Point2, ...]) -> float:
    orientation = 1 if signed_turn(*clip) > 0 else -1
    polygon = list(subject)
    for start, end in zip(clip, clip[1:] + clip[:1], strict=True):
        if not polygon:
            break
        output = []
        previous = polygon[-1]
        previous_side = orientation * signed_turn(start, end, previous)
        for current in polygon:
            side = orientation * signed_turn(start, end, current)
            if (previous_side < 0) != (side < 0):
                amount = previous_side / (previous_side - side)
                output.append((previous[0] + (current[0] - previous[0]) * amount,
                               previous[1] + (current[1] - previous[1]) * amount))
            if side >= 0:
                output.append(current)
            previous, previous_side = current, side
        polygon = output
    if len(polygon) < 3:
        return 0.0
    return abs(sum(signed_turn(polygon[0], polygon[i], polygon[i + 1])
                   for i in range(1, len(polygon) - 1))) / 2


def overlap_area(first: Triangle, second: Triangle) -> float:
    normal = first.normal
    if abs(normal.dot(second.normal)) < 1 - 1e-6:
        return 0.0
    origin = first.points[0]
    if any(abs(normal.dot(point - origin)) > DISTANCE_EPSILON for point in second.points):
        return 0.0
    dominant = max(range(3), key=lambda axis: abs(normal[axis]))
    axes = tuple(axis for axis in range(3) if axis != dominant)
    subject = tuple((p[axes[0]], p[axes[1]]) for p in first.points)
    clip = tuple((p[axes[0]], p[axes[1]]) for p in second.points)
    return clipped_area(subject, clip) / abs(normal[dominant])


def leaf_pairs(a: Box, b: Box) -> Iterator[tuple[Triangle, Triangle]]:
    for i, first in enumerate(a.items):
        for second in b.items[i + 1:] if a is b else b.items:
            if first.face != second.face and touches(first, second):
                yield first, second


def pairs(a: Box, b: Box) -> Iterator[tuple[Triangle, Triangle]]:
    if not touches(a, b):
        return
    if a is b and a.children:
        left, right = a.children
        yield from pairs(left, left)
        yield from pairs(left, right)
        yield from pairs(right, right)
    elif a.children:
        for child in a.children:
            yield from pairs(child, b)
    elif b.children:
        for child in b.children:
            yield from pairs(a, child)
    else:
        yield from leaf_pairs(a, b)


def coplanar_faces(mesh: bpy.types.Mesh, coordinates: list[Vector]) -> set[int]:
    mesh.calc_loop_triangles()
    triangles = []
    for face in mesh.loop_triangles:
        points = tuple(coordinates[index] for index in face.vertices)
        cross = (points[1] - points[0]).cross(points[2] - points[0])
        if cross.length_squared <= AREA_EPSILON**2:
            continue
        lower = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
        upper = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
        triangles.append(Triangle(face.polygon_index, points, cross.normalized(), lower, upper))
    if not triangles:
        return set()
    root = hierarchy(triangles)
    affected = set()
    for first, second in pairs(root, root):
        if first.face in affected and second.face in affected:
            continue
        if overlap_area(first, second) > AREA_EPSILON:
            affected.update((first.face, second.face))
    return affected
