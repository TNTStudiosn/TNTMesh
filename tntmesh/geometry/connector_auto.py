# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import cos, floor, sin, sqrt, tau

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..model import MeshError
from .boolean import ExactBoolean
from .connector import Connector, candidates, safe_centers
from .mesh import bounds
from .planar import PlaneSplit, invert_frame
from .polygon import Point2

MIN_DIAMETER = 1.2
MIN_INSERTION = .6
MAX_RECOMMENDED = 6
PROBE_CANDIDATES = 64


@dataclass(frozen=True)
class Suggestion:
    connector: Connector
    positions: tuple[Point2, ...]
    pin_positive: bool


@dataclass(frozen=True)
class Seam:
    tree: BVHTree
    height: float
    inward: Vector
    epsilon: float

    def depth(self, x: float, y: float) -> float:
        entry = Vector((x, y, self.height)) - self.inward * (4 * self.epsilon)
        cap, _, _, _ = self.tree.ray_cast(entry, self.inward, 8 * self.epsilon)
        if cap is None:
            return 0.0
        inner = cap + self.inward * (4 * self.epsilon)
        _, _, _, distance = self.tree.ray_cast(inner, self.inward)
        return distance + 4 * self.epsilon if distance is not None else 0.0


def seam_section(
    mesh: bpy.types.Mesh, frame: Matrix, height: float, direction: float, epsilon: float,
) -> tuple[Seam, float, list[Vector]]:
    inverse = frame.transposed()
    points = [inverse @ vertex.co for vertex in mesh.vertices]
    faces = [tuple(face.vertices) for face in mesh.polygons]
    tree = BVHTree.FromPolygons(points, faces)
    cap = [face for face in mesh.polygons if face.area > 0 and
           all(abs(points[index].z - height) <= 2 * epsilon for index in face.vertices)]
    area = sum(face.area for face in cap)
    centers = [Vector(((inverse @ face.center).x, (inverse @ face.center).y, 0.0))
               for face in sorted(cap, key=lambda face: -face.area)[:15]]
    return Seam(tree, height, Vector((0, 0, direction)), epsilon), area, centers


def least_depths(seams: tuple[Seam, Seam], center: Vector, design: Connector) -> tuple[float, float]:
    radius = design.envelope
    # Use a coarse perimeter for ranking. Exact solid probes validate the whole footprint.
    samples = [(center.x, center.y), *(
        (center.x + radius * cos(i * tau / 12), center.y + radius * sin(i * tau / 12))
        for i in range(12)
    )]
    return tuple(min(seam.depth(*point) for point in samples) for seam in seams)


def suggest(
    engine: ExactBoolean, cut: PlaneSplit, frame: Matrix, kerf: float, baseline: Connector,
) -> Suggestion:
    low, high = cut.position - kerf / 2, cut.position + kerf / 2
    epsilon = cut.epsilon
    minus, minus_area, minus_centers = seam_section(cut.minus, frame, low, -1, epsilon)
    plus, plus_area, plus_centers = seam_section(cut.plus, frame, high, 1, epsilon)
    area = min(minus_area, plus_area)
    centers = list(candidates(cut.minus, frame, low, 2 * epsilon))
    if not centers or area <= 0:
        raise MeshError("No connector fits this cut with the current wall and clearances.")
    lower, upper = bounds(centers)
    width = min((upper - lower).xy) / .75
    diam_limit = min(baseline.diameter, width * .65, sqrt(area) * .45)
    depths = {tuple(center): (minus.depth(center.x, center.y), plus.depth(center.x, center.y))
              for center in [*centers, *minus_centers, *plus_centers]}
    centers = [Vector(center) for center, thickness in depths.items() if min(thickness) > baseline.wall]
    centers.sort(key=lambda center: (-min(depths[tuple(center)]), center.length_squared))
    seams = minus, plus
    seen = set()
    for scale in (1, .8, .6, .45, .3, .2):
        diameter = max(MIN_DIAMETER, floor(diam_limit * scale * 10) / 10)
        if diameter > diam_limit or diameter in seen:
            continue
        seen.add(diameter)
        count = min(MAX_RECOMMENDED, max(1, floor(area / (diameter * diameter * 12))))
        shape = "HEX" if count == 1 else "ROUND"
        design = replace(baseline, shape=shape, diameter=diameter, count=count)
        distances = [(point, least_depths(seams, point, design)) for point in centers[:PROBE_CANDIDATES]]
        options = (False, True) if not design.loose else (False,)
        for fraction in (1.0, .75, .5, .32, .2):
            insertion = floor(min(baseline.insertion, diameter * 1.2) * fraction * 10) / 10
            if insertion < MIN_INSERTION:
                continue
            design = replace(design, insertion=insertion)
            placed = []
            for flip in options:
                fit = fit_suggestion(engine, cut, frame, kerf, design, distances, flip)
                if fit is not None:
                    placed.append(fit)
            if placed:
                return max(placed, key=lambda result: (result.connector.count, result.reserve))
    raise MeshError("No connector fits this cut with the current wall and clearances.")


@dataclass(frozen=True)
class FittedSuggestion(Suggestion):
    reserve: float


def fit_suggestion(
    engine: ExactBoolean, cut: PlaneSplit, frame: Matrix, kerf: float, design: Connector,
    distances: list[tuple[Vector, tuple[float, float]]], flip: bool,
) -> FittedSuggestion | None:
    depths = design.depths
    actual = cut.flipped() if flip else cut
    basis = invert_frame(frame) if flip else frame
    ranked = {
        (point.x, -point.y if flip else point.y, 0.0):
            min(thickness[1] - depths[0], thickness[0] - depths[1]) if flip
            else min(thickness[0] - depths[0], thickness[1] - depths[1])
        for point, thickness in distances
    }
    requested = tuple(Vector(point) for point, reserve in sorted(ranked.items(), key=lambda item: -item[1])
                      if reserve >= -actual.epsilon)
    if not requested:
        return None
    local = design.reflected("Y") if flip else design
    centers = safe_centers(
        engine, actual.minus, actual.plus, basis,
        (actual.position - kerf / 2, actual.position + kerf / 2),
        depths, local.profile(design.lateral + design.wall), actual.epsilon,
        min(actual.epsilon, design.anchor / 10, design.wall / 10), design.count,
        requested=requested, allow_partial=True,
    )
    if not centers:
        return None
    return FittedSuggestion(
        replace(design, count=len(centers)),
        tuple((point.x, -point.y if flip else point.y) for point in centers),
        flip, min(ranked[tuple(point)] for point in centers),
    )
