# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass

import bpy
from mathutils import Vector

LEAF_SIZE = 8


@dataclass(frozen=True)
class Triangle:
    face: int
    points: tuple[Vector, Vector, Vector]
    normal: Vector
    lower: Vector
    upper: Vector


@dataclass(frozen=True)
class Box:
    lower: Vector
    upper: Vector
    items: list[Triangle]
    children: tuple["Box", "Box"] | None = None


def hierarchy(items: list[Triangle]) -> Box:
    lower = Vector(tuple(min(item.lower[axis] for item in items) for axis in range(3)))
    upper = Vector(tuple(max(item.upper[axis] for item in items) for axis in range(3)))
    if len(items) <= LEAF_SIZE:
        return Box(lower, upper, items)
    longest = max(range(3), key=lambda axis: upper[axis] - lower[axis])
    items.sort(key=lambda item: item.lower[longest] + item.upper[longest])
    middle = len(items) // 2
    return Box(lower, upper, [], (hierarchy(items[:middle]), hierarchy(items[middle:])))


def triangles_from(
    mesh: bpy.types.Mesh, coordinates: list[Vector], *, minimum_area: float = 0.0,
) -> list[Triangle]:
    mesh.calc_loop_triangles()
    triangles = []
    for face in mesh.loop_triangles:
        a, b, c = (coordinates[index] for index in face.vertices)
        cross = (b - a).cross(c - a)
        if cross.length_squared <= minimum_area**2:
            continue
        lower = Vector(tuple(min(a[axis], b[axis], c[axis]) for axis in range(3)))
        upper = Vector(tuple(max(a[axis], b[axis], c[axis]) for axis in range(3)))
        triangles.append(Triangle(face.polygon_index, (a, b, c), cross.normalized(), lower, upper))
    return triangles
