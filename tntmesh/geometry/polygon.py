# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Sequence
from math import hypot, isfinite

from ..model import MeshError

Point2 = tuple[float, float]


def signed_turn(a: Point2, b: Point2, c: Point2) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def overlaps(a: Point2, b: Point2, c: Point2, d: Point2, edge_eps: float, cross_eps: float) -> bool:
    if any(
        max(min(a[axis], b[axis]), min(c[axis], d[axis]))
        > min(max(a[axis], b[axis]), max(c[axis], d[axis])) + edge_eps
        for axis in (0, 1)
    ):
        return False
    ab = (signed_turn(a, b, c), signed_turn(a, b, d))
    cd = (signed_turn(c, d, a), signed_turn(c, d, b))
    return all(min(pair) <= cross_eps and max(pair) >= -cross_eps for pair in (ab, cd))


def closed_outline(points: Sequence[Point2]) -> list[Point2]:
    if len(points) < 3 or any(not all(map(isfinite, point)) for point in points):
        raise MeshError("Draw a contour with at least three valid points.")
    span = max(max(point[axis] for point in points) - min(point[axis] for point in points)
               for axis in (0, 1))
    epsilon = max(span * 1e-7, 1e-6)
    cross_epsilon = span * epsilon
    count = len(points)

    for index, a in enumerate(points):
        b = points[(index + 1) % count]
        c = points[(index + 2) % count]
        if hypot(a[0] - b[0], a[1] - b[1]) <= epsilon:
            raise MeshError("The contour has adjacent points that are too close.")
        if abs(signed_turn(a, b, c)) <= cross_epsilon and (
            (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1]) < 0
        ):
            raise MeshError("The contour crosses or folds over itself.")
        for other in range(index + 2, count):
            if index == 0 and other == count - 1:
                continue
            if overlaps(a, b, points[other], points[(other + 1) % count], epsilon, cross_epsilon):
                raise MeshError("The contour crosses or folds over itself.")

    base = points[0]
    area_twice = sum(signed_turn(base, points[i], points[i + 1]) for i in range(1, count - 1))
    if abs(area_twice) <= cross_epsilon:
        raise MeshError("The contour does not enclose an area.")
    return list(points) if area_twice > 0.0 else list(reversed(points))
