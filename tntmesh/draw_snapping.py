# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

import bpy
from bpy_extras.view3d_utils import (
    location_3d_to_region_2d,
    region_2d_to_location_3d,
    region_2d_to_origin_3d,
    region_2d_to_vector_3d,
)
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .geometry.mesh import bounds

SNAP_RADIUS = 12


@dataclass(frozen=True)
class CursorPoint:
    screen: Vector
    surface: Vector | None = None


class SurfacePicker:
    def __init__(self, obj: bpy.types.Object, mode: str) -> None:
        self.mode = mode
        self.world = obj.matrix_world.copy()
        self.inverse = self.world.inverted_safe()
        self.coordinates = [vertex.co.copy() for vertex in obj.data.vertices]
        self.faces = [tuple(face.vertices) for face in obj.data.polygons]
        self.tree = BVHTree.FromPolygons(self.coordinates, self.faces)
        lower, upper = bounds(self.world @ Vector(corner) for corner in obj.bound_box)
        self.center = (lower + upper) / 2
        self.span = max(1e-3, (upper - lower).length)

    def pick(self, region: bpy.types.Region, view: bpy.types.RegionView3D, pixel: Vector) -> CursorPoint:
        direction = region_2d_to_vector_3d(region, view, pixel)
        if view.is_perspective:
            origin = region_2d_to_origin_3d(region, view, pixel)
        else:
            origin = region_2d_to_location_3d(region, view, pixel, self.center) - direction * self.span
        local_direction = (self.inverse.to_3x3() @ direction).normalized()
        point, _, face, _ = self.tree.ray_cast(self.inverse @ origin, local_direction)
        if point is None:
            return CursorPoint(pixel)
        nearest = CursorPoint(pixel, self.world @ point)
        if self.mode == "SURFACE":
            return nearest

        vertices = [self.world @ self.coordinates[index] for index in self.faces[face]]
        screen = [location_3d_to_region_2d(region, view, vertex) for vertex in vertices]
        distance = SNAP_RADIUS**2
        for i, candidate in enumerate(screen):
            if candidate is None:
                continue
            world = vertices[i]
            if self.mode == "EDGE":
                following = (i + 1) % len(vertices)
                end = screen[following]
                if end is None or end == candidate:
                    continue
                edge = end - candidate
                fraction = min(1.0, max(0.0, edge.dot(pixel - candidate) / edge.length_squared))
                candidate = candidate + edge * fraction
                world = perspective_edge_point(view, world, vertices[following], fraction)
            squared = (candidate - pixel).length_squared
            if squared < distance:
                distance = squared
                nearest = CursorPoint(candidate, world)
        return nearest


def perspective_edge_point(view: bpy.types.RegionView3D, start: Vector, end: Vector, fraction: float) -> Vector:
    if view.is_perspective:
        matrix = view.perspective_matrix
        first = (matrix @ Vector((*start, 1.0))).w
        second = (matrix @ Vector((*end, 1.0))).w
        fraction = fraction * first / ((1.0 - fraction) * second + fraction * first)
    return start.lerp(end, fraction)
