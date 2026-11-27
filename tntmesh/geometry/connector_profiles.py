# SPDX-License-Identifier: GPL-3.0-or-later
from math import acos, cos, hypot, sin, sqrt, tau

from ..model import MeshError
from .polygon import Point2, closed_outline, overlaps

PROFILE_ITEMS = (
    ("TAPER", "Tapered cylinder", "A round pin that narrows toward its tip"),
    ("SQUARE", "Square", "A square pin with four flat sides"),
    ("RECTANGLE", "Rectangular", "A keyed pin with independent width and height"),
    ("TRIANGLE", "Triangular", "An equilateral triangular pin"),
    ("OCTAGON", "Octagonal", "A regular eight-sided pin"),
    ("OVAL", "Oval", "An elliptical pin with independent width and height"),
    ("D", "D-shaped", "A round pin with one flat side"),
    ("STAR", "Star", "A five-pointed star with recessed corners"),
    ("CROSS", "Cross", "A pin with four square arms"),
    ("TONGUE", "Tongue and Groove", "A wide tongue with chamfered corners and a matching groove"),
)
STANDARD_SHAPES = frozenset(("ROUND", "HEX", *(item[0] for item in PROFILE_ITEMS)))
DIAMETER_SHAPES = {"ROUND", "TAPER", "HEX", "OCTAGON", "D", "STAR"}
TWO_DIMENSION_SHAPES = {"RECTANGLE", "OVAL", "TONGUE"}
PROFILE_OVERLAYS = STANDARD_SHAPES | {"MAGNET", "DOVETAIL", "PRESS_FIT", "ROD", "SNAP_FIT"}


def regular_profile(radius: float, sides: int) -> tuple[Point2, ...]:
    # Keep cardinal coordinates exact for coplanar intersections at the seam.
    return tuple((radius * round(cos(a), 15), radius * round(sin(a), 15))
                 for a in (tau * index / sides for index in range(sides)))


def outline(shape: str, diameter: float, width: float, height: float) -> tuple[Point2, ...]:
    radius, x, y = diameter / 2, width / 2, height / 2
    if shape == "TRIANGLE":
        return regular_profile(width / sqrt(3), 3)
    if shape == "SQUARE":
        y = x
    if shape in {"SQUARE", "RECTANGLE"}:
        return ((-x, -y), (x, -y), (x, y), (-x, y))
    if shape == "OVAL":
        return tuple((x * a, y * b) for a, b in regular_profile(1, 64))
    if shape == "D":
        arc = acos(-.55)
        return tuple((radius * cos(t), radius * sin(t)) for t in
                     (-arc + 2 * arc * index / 48 for index in range(49)))
    if shape == "STAR":
        return tuple((a * (radius if index % 2 == 0 else radius * .54),
                      b * (radius if index % 2 == 0 else radius * .54))
                     for index, (a, b) in enumerate(regular_profile(1, 10)))
    if shape == "CROSS":
        a = x / 3
        return ((-a, -x), (a, -x), (a, -a), (x, -a), (x, a), (a, a),
                (a, x), (-a, x), (-a, a), (-x, a), (-x, -a), (-a, -a))
    if shape == "TONGUE":
        bevel = min(x, y) * .3
        return ((-x + bevel, -y), (x - bevel, -y), (x, -y + bevel), (x, y - bevel),
                (x - bevel, y), (-x + bevel, y), (-x, y - bevel), (-x, -y + bevel))
    return regular_profile(radius, {"HEX": 6, "OCTAGON": 8}.get(shape, 64))


def area(points: tuple[Point2, ...]) -> float:
    return sum(a[0] * b[1] - a[1] * b[0] for a, b in zip(points, points[1:] + points[:1], strict=True)) / 2


def dilated(points: tuple[Point2, ...], gap: float) -> tuple[Point2, ...]:
    if not gap:
        return points
    edges = tuple((b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:] + points[:1], strict=True))
    normals = tuple((y / hypot(x, y), -x / hypot(x, y)) for x, y in edges)
    result = []
    for index, (x, y) in enumerate(points):
        previous, current = normals[index - 1], normals[index]
        alignment = 1 + previous[0] * current[0] + previous[1] * current[1]
        if alignment <= 1e-12:
            raise MeshError("The connector profile has a corner too sharp for its size.")
        bisector = gap / alignment
        result.append((x + (previous[0] + current[0]) * bisector, y + (previous[1] + current[1]) * bisector))
    # Reflex corners can lose an edge at a large offset. Reject inverted or crossed walls.
    pairs = zip(result, result[1:] + result[:1], edges, strict=True)
    if any((b[0] - a[0]) * edge[0] + (b[1] - a[1]) * edge[1] <= 0 for a, b, edge in pairs):
        raise MeshError("Reduce the clearance or wall size to preserve the connector profile.")
    try:
        closed_outline(result)
    except MeshError as error:
        raise MeshError("Reduce the clearance or wall size to preserve the connector profile.") from error
    return tuple(result)


def translated_overlap(profile: tuple[Point2, ...], x: float, y: float, epsilon: float) -> bool:
    if any(abs(delta) > max(values) - min(values) + epsilon
           for delta, values in zip((x, y), zip(*profile, strict=True), strict=True)):
        return False
    edges = tuple(zip(profile, profile[1:] + profile[:1], strict=True))
    shifted = tuple(((a[0] + x, a[1] + y), (b[0] + x, b[1] + y)) for a, b in edges)
    # A translated copy has the same area, so strict containment cannot occur without boundary contact.
    return any(overlaps(a, b, c, d, epsilon, epsilon * max(1, hypot(b[0] - a[0], b[1] - a[1])))
               for a, b in edges for c, d in shifted)
