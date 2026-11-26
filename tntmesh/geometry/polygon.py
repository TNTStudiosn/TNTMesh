# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Sequence
from math import ceil, floor, hypot, isfinite

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


def smooth_path(points: Sequence[Point2], passes: int) -> list[Point2]:
    path = list(points)
    for _ in range(passes):
        path = [
            path[0],
            *(((before[0] + 2 * current[0] + after[0]) / 4,
               (before[1] + 2 * current[1] + after[1]) / 4)
              for before, current, after in zip(path[:-2], path[1:-1], path[2:], strict=True)),
            path[-1],
        ]
    return path


def border_hit(point: Point2, next_point: Point2, corners: tuple[Point2, ...]) -> tuple[Point2, float]:
    direction = (point[0] - next_point[0], point[1] - next_point[1])
    exits = []
    for side, corner in enumerate(corners):
        axis = 1 - side % 2
        speed = direction[axis]
        if (speed if side in (1, 2) else -speed) > 0:
            exits.append(((corner[axis] - point[axis]) / speed, side))
    if not exits:
        raise MeshError("The path has adjacent points that are too close.")
    distance, side = min(exits)
    hit = (point[0] + distance * direction[0], point[1] + distance * direction[1])
    a, b = corners[side], corners[(side + 1) % 4]
    tangent = side % 2
    fraction = (hit[tangent] - a[tangent]) / (b[tangent] - a[tangent])
    return hit, side + min(1, max(0, fraction))


def extended_path(
    points: Sequence[Point2], lower: Point2, upper: Point2, smoothing: int,
) -> tuple[list[Point2], list[Point2]]:
    if len(points) < 2 or any(not all(map(isfinite, point)) for point in points):
        raise MeshError("Draw a path with at least two valid points.")
    if not 0 <= smoothing <= 12:
        raise MeshError("Choose up to 12 path smoothing passes.")
    epsilon = max(hypot(upper[0] - lower[0], upper[1] - lower[1]) * 1e-7, 1e-6)
    if any(hypot(a[0] - b[0], a[1] - b[1]) <= epsilon for a, b in zip(points[:-1], points[1:], strict=True)):
        raise MeshError("The path has adjacent points that are too close.")
    path = smooth_path(points, smoothing)
    low = tuple(min(lower[axis], *(point[axis] for point in path)) for axis in range(2))
    high = tuple(max(upper[axis], *(point[axis] for point in path)) for axis in range(2))
    pad = max(hypot(high[0] - low[0], high[1] - low[1]) * .1, .01)
    corners = ((low[0] - pad, low[1] - pad), (high[0] + pad, low[1] - pad),
               (high[0] + pad, high[1] + pad), (low[0] - pad, high[1] + pad))
    start, first = border_hit(path[0], path[1], corners)
    end, last = border_hit(path[-1], path[-2], corners)
    if first < last:
        first += 4
    border = [corners[index % 4] for index in range(floor(last) + 1, ceil(first))]
    return [start, *path, end], border


def path_outline(
    points: Sequence[Point2], lower: Point2, upper: Point2, smoothing: int,
) -> list[Point2]:
    path, border = extended_path(points, lower, upper, smoothing)
    return closed_outline([*path, *border])
