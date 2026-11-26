# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterator
from dataclasses import dataclass

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .mesh import bounds

_DETAIL_SAMPLES = ((.6, .2, .2), (.2, .6, .2), (.2, .2, .6))


@dataclass(frozen=True)
class WallSample:
    triangle: int
    face: int
    start: Vector
    end: Vector

    @property
    def thickness(self) -> float:
        return (self.end - self.start).length


def wall_samples(
    mesh: bpy.types.Mesh, coordinates: list[Vector], distance_mm: float, *, detailed: bool = False,
) -> Iterator[WallSample]:
    triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
    tree = BVHTree.FromPolygons(coordinates, triangles, all_triangles=True)
    lower, upper = bounds(coordinates)
    epsilon = max(1e-7, (upper - lower).length * 2e-7)
    if detailed:
        distance_mm = (upper - lower).length
    if distance_mm <= epsilon:
        return
    for index, triangle in enumerate(mesh.loop_triangles):
        first, second, third = (coordinates[item] for item in triangles[index])
        direction = (third - first).cross(second - first).normalized()
        positions = [(first + second + third) / 3]
        if detailed:
            positions.extend(first * a + second * b + third * c for a, b, c in _DETAIL_SAMPLES)
        vertices = set(triangles[index])
        best = None
        for start in positions:
            end, normal, hit, _ = tree.ray_cast(start + direction * epsilon, direction, distance_mm - epsilon)
            if end is None or hit == index or normal.dot(direction) <= .5 or not vertices.isdisjoint(triangles[hit]):
                continue
            sample = WallSample(index, triangle.polygon_index, start, end)
            if sample.thickness < distance_mm and (best is None or sample.thickness < best.thickness):
                best = sample
        if best is not None:
            yield best
