# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from math import ceil, isfinite, prod

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..model import MeshError
from .mesh import bounds

MAX_VOXELS = 4_000_000


@dataclass(frozen=True)
class Pocket:
    center: Vector
    area_mm2: float


@dataclass(frozen=True)
class Suction:
    pockets: tuple[Pocket, ...]
    count: int
    step_mm: float
    sampled_rows: int
    uncertain_rows: int


@dataclass(eq=False, slots=True)
class Region:
    parent: "Region | None" = None
    size: int = 1
    peak: Pocket | None = None

    def root(self) -> "Region":
        node = self
        while node.parent is not None:
            if node.parent.parent is not None:
                node.parent = node.parent.parent
            node = node.parent
        return node


@dataclass(slots=True)
class Span:
    start: int
    end: int
    region: Region


class Layers:
    def __init__(self, marker_limit: int) -> None:
        self.outside = Region()
        self.outside.size = MAX_VOXELS + 1
        self.pockets: list[Pocket] = []
        self.count = 0
        self.marker_limit = marker_limit

    def remember(self, pocket: Pocket | None) -> None:
        if pocket is None:
            return
        self.count += 1
        if len(self.pockets) < self.marker_limit:
            self.pockets.append(pocket)
            return
        smallest = min(range(len(self.pockets)), key=lambda index: self.pockets[index].area_mm2)
        if pocket.area_mm2 > self.pockets[smallest].area_mm2:
            self.pockets[smallest] = pocket

    def join(self, first: Region, second: Region) -> None:
        a, b = first.root(), second.root()
        if a is b:
            return
        if a.size < b.size:
            a, b = b, a
        b.parent = a
        a.size += b.size
        if a is self.outside:
            self.remember(b.peak)
        elif b.peak is not None and (a.peak is None or b.peak.area_mm2 > a.peak.area_mm2):
            a.peak = b.peak
        b.peak = None

    def neighbors(self, first: list[Span], second: list[Span]) -> None:
        i = j = 0
        while i < len(first) and j < len(second):
            a, b = first[i], second[j]
            if a.start < b.end and b.start < a.end:
                self.join(a.region, b.region)
            if a.end <= b.end:
                i += 1
            if b.end <= a.end:
                j += 1


def material_intervals(tree: BVHTree, start: Vector, epsilon: float) -> list[tuple[float, float]] | None:
    direction = Vector((1, 0, 0))
    intervals = []
    entry = None
    point = start
    while True:
        hit, normal, _, _ = tree.ray_cast(point, direction)
        if hit is None:
            return intervals if entry is None else None
        if normal.x < -1e-6:
            if entry is not None:
                return None
            entry = hit.x
        elif normal.x > 1e-6:
            if entry is None or hit.x <= entry:
                return None
            intervals.append((entry, hit.x))
            entry = None
        point = hit + direction * epsilon
        if point.x <= hit.x:
            return None


def air_spans(
    solid: list[tuple[float, float]], first_x: float, step: float, width: int,
) -> Iterator[tuple[int, int]]:
    start = 0
    for enter, leave in solid:
        # Indices represent cell centers. Runs use a half-open interval.
        left = max(0, ceil((enter - first_x) / step))
        right = min(width, ceil((leave - first_x) / step))
        if left >= right:
            continue
        if start < left:
            yield start, left
        start = max(start, right)
    if start < width:
        yield start, width


def estimate(
    mesh: bpy.types.Mesh, direction: Vector, step_mm: float, marker_limit: int,
    progress: Callable[[float], None] | None = None,
) -> Suction:
    if not all(map(isfinite, (*direction, step_mm))) or direction.length < 1e-8 or step_mm < .05:
        raise MeshError("Set a print direction and a sampling step of at least 0.05 mm.")
    z = direction.normalized()
    x = z.orthogonal().normalized()
    inverse = Matrix((x, z.cross(x), z))
    frame = inverse.transposed()
    points = [inverse @ vertex.co for vertex in mesh.vertices]
    lower, upper = bounds(points)
    size = upper - lower
    # The default budget bounds progress time for large models and very fine step requests.
    step = max(step_mm, max(size) / (MAX_VOXELS // 9))
    shape = tuple(ceil(value / step) + 3 for value in size)
    while prod(shape) > MAX_VOXELS:
        step *= max(1.02, (prod(shape) / MAX_VOXELS) ** (1 / 3))
        shape = tuple(ceil(value / step) + 3 for value in size)
    width, height, depth = shape
    base = lower - Vector((.631, .719, .837)) * step
    epsilon = max(step * 1e-5, max(size) * 2.5e-7)
    mesh.calc_loop_triangles()
    tree = BVHTree.FromPolygons(points, [tuple(face.vertices) for face in mesh.loop_triangles], all_triangles=True)
    layers = Layers(marker_limit)
    previous = [[] for _ in range(height)]
    previous_roots: set[Region] = set()
    uncertain_rows = 0
    for k in range(depth):
        layer_z = base.z + k * step
        rows: list[list[Span]] = []
        for j in range(height):
            row_y = base.y + j * step
            ray = Vector((base.x - step, row_y, layer_z))
            solid = material_intervals(tree, ray, epsilon)
            if solid is None:
                ray.y += .017 * step
                ray.z += .013 * step
                solid = material_intervals(tree, ray, epsilon)
            if solid is None:
                # A remaining ambiguous row is open in the estimate and disclosed to the caller.
                uncertain_rows += 1
                solid = []
            row = []
            for left, right in air_spans(solid, base.x, step, width):
                external = j in (0, height - 1) or left == 0 or right == width
                row.append(Span(left, right, layers.outside if external else Region()))
            if j:
                layers.neighbors(row, rows[-1])
            layers.neighbors(row, previous[j])
            rows.append(row)

        sections: dict[Region, tuple[int, int, Span]] = {}
        for j, row in enumerate(rows):
            for span in row:
                root = span.region.root()
                span.region = root
                if root is layers.outside:
                    continue
                cells, widest_row, widest = sections.get(root, (0, j, span))
                if span.end - span.start > widest.end - widest.start:
                    widest_row, widest = j, span
                sections[root] = (cells + span.end - span.start, widest_row, widest)
        for region, (cells, j, span) in sections.items():
            area = cells * step**2
            if region.peak is None or area > region.peak.area_mm2:
                center_x = base.x + (span.start + span.end - 1) / 2 * step
                center = frame @ Vector((center_x, base.y + j * step, layer_z))
                region.peak = Pocket(center, area)

        current_roots = set(sections)
        retired = {region.root() for region in previous_roots} - current_roots - {layers.outside}
        for region in retired:
            layers.remember(region.peak)
            region.peak = None
        previous, previous_roots = rows, current_roots
        if progress is not None and (k % 8 == 0 or k == depth - 1):
            progress((k + 1) / depth)

    for region in previous_roots:
        layers.remember(region.peak)
    pockets = tuple(sorted(layers.pockets, key=lambda pocket: pocket.area_mm2, reverse=True))
    return Suction(pockets, layers.count, step, height * depth, uncertain_rows)
