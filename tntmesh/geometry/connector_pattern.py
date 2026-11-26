# SPDX-License-Identifier: GPL-3.0-or-later
from bisect import bisect_right
from collections import defaultdict
from itertools import accumulate
from math import ceil, cos, isfinite, sin, sqrt, tau

from mathutils import Matrix, Vector

from ..model import MeshError
from .planar import PlaneSplit
from .polygon import Point2


def seam_border(cut: PlaneSplit, frame: Matrix, kerf: float) -> list[Vector]:
    mesh = cut.minus
    inverse = frame.transposed()
    seam = cut.position - kerf / 2
    points = [inverse @ vertex.co for vertex in mesh.vertices]
    edges: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for face in mesh.polygons:
        indices = tuple(face.vertices)
        if not all(abs(points[index].z - seam) <= 2 * cut.epsilon for index in indices):
            continue
        for start, end in zip(indices, (*indices[1:], indices[0]), strict=True):
            edges[tuple(sorted((start, end)))].append((start, end))
    boundary = [uses[0] for uses in edges.values() if len(uses) == 1]
    following = dict(boundary)
    if len(following) != len(boundary):
        raise MeshError("The cut contour is branched or open.")
    loops = []
    while following:
        first = next(iter(following))
        current = first
        loop = []
        while current in following:
            loop.append(points[current].xy)
            current = following.pop(current)
        if current != first or len(loop) < 3:
            raise MeshError("The cut contour is branched or open.")
        pairs = zip(loop, (*loop[1:], loop[0]), strict=True)
        area = sum(a.x * b.y - a.y * b.x for a, b in pairs)
        if area > cut.epsilon**2:
            loops.append((area, loop))
    if not loops:
        raise MeshError("The cut does not have a usable outer contour.")
    return max(loops, key=lambda pair: pair[0])[1]


def contour_points(
    cut: PlaneSplit, frame: Matrix, kerf: float, count: int, setback: float, angle: float,
) -> tuple[Point2, ...]:
    if not 1 <= count <= 32 or setback <= 0 or not all(map(isfinite, (setback, angle))):
        raise MeshError("Check the connector layout dimensions.")
    border = seam_border(cut, frame, kerf)
    edges = [end - start for start, end in zip(border, (*border[1:], border[0]), strict=True)]
    distances = [0.0, *accumulate(edge.length for edge in edges)]
    total = distances[-1]
    if total <= cut.epsilon:
        raise MeshError("The cut does not have a usable outer contour.")
    points = []
    for i in range(count):
        along = (((i + .5) / count + angle / tau) % 1.0) * total
        index = bisect_right(distances, along) - 1
        edge = edges[index].normalized()
        position = border[index] + edge * (along - distances[index])
        position += Vector((-edge.y, edge.x)) * setback
        points.append(tuple(position))
    return tuple(points)


def pattern_points(
    kind: str, count: int, spacing: float, angle: float, center: Point2,
) -> tuple[Point2, ...]:
    if not 1 <= count <= 32 or spacing <= 0 or not all(map(isfinite, (spacing, angle, *center))):
        raise MeshError("Check the connector layout dimensions.")
    if kind == "CIRCLE" and count > 1:
        radius = spacing / (2 * sin(tau / (2 * count)))
        points = [(radius * cos(tau * i / count), radius * sin(tau * i / count)) for i in range(count)]
    else:
        columns = ceil(sqrt(count)) if kind == "GRID" else count
        rows = ceil(count / columns)
        points = []
        for row in range(rows):
            width = min(columns, count - row * columns)
            points.extend(((i - (width - 1) / 2) * spacing, (row - (rows - 1) / 2) * spacing)
                          for i in range(width))
    cosine, sine = cos(angle), sin(angle)
    return tuple((center[0] + x * cosine - y * sine, center[1] + x * sine + y * cosine) for x, y in points)
