# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator

import bpy
from mathutils import Vector

from .polygon import Point2, signed_turn
from .triangle_bounds import Box, Triangle, hierarchy, triangles_from

DISTANCE_EPSILON = .00001
AREA_EPSILON = DISTANCE_EPSILON**2


def touches(a: Box | Triangle, b: Box | Triangle) -> bool:
    low_a, high_a = a.lower, a.upper
    low_b, high_b = b.lower, b.upper
    eps = DISTANCE_EPSILON
    return (low_a.x <= high_b.x + eps and low_b.x <= high_a.x + eps
            and low_a.y <= high_b.y + eps and low_b.y <= high_a.y + eps
            and low_a.z <= high_b.z + eps and low_b.z <= high_a.z + eps)


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


def pairs(root: Box) -> Iterator[tuple[Triangle, Triangle]]:
    pending = [(root, root)]
    while pending:
        a, b = pending.pop()
        if not touches(a, b):
            continue
        if a is b and a.children:
            left, right = a.children
            pending.extend(((left, left), (left, right), (right, right)))
        elif a.children and (not b.children or a.count >= b.count):
            left, right = a.children
            pending.extend(((left, b), (right, b)))
        elif b.children:
            left, right = b.children
            pending.extend(((a, left), (a, right)))
        else:
            yield from leaf_pairs(a, b)


def coplanar_faces(mesh: bpy.types.Mesh, coordinates: list[Vector]) -> set[int]:
    triangles = triangles_from(mesh, coordinates, minimum_area=AREA_EPSILON)
    if not triangles:
        return set()
    root = hierarchy(triangles)
    affected = set()
    for first, second in pairs(root):
        if first.face in affected and second.face in affected:
            continue
        if overlap_area(first, second) > AREA_EPSILON:
            affected.update((first.face, second.face))
    return affected
