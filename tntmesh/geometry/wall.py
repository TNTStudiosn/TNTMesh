# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .mesh import bounds


def thin_wall_samples(
    mesh: bpy.types.Mesh, coordinates: list[Vector], minimum_mm: float,
) -> Iterator[tuple[int, Vector, Vector]]:
    triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
    tree = BVHTree.FromPolygons(coordinates, triangles, all_triangles=True)
    lower, upper = bounds(coordinates)
    epsilon = max(1e-7, (upper - lower).length * 2e-7)
    if minimum_mm <= epsilon:
        return
    for index, triangle in enumerate(mesh.loop_triangles):
        first, second, third = (coordinates[item] for item in triangles[index])
        center = (first + second + third) / 3
        direction = (third - first).cross(second - first).normalized()
        point, normal, hit, _ = tree.ray_cast(center + direction * epsilon, direction, minimum_mm - epsilon)
        if point is None or hit == index or normal.dot(direction) <= .5:
            continue
        if not set(triangles[index]).isdisjoint(triangles[hit]):
            continue
        if (point - center).length < minimum_mm:
            yield triangle.polygon_index, center, point
