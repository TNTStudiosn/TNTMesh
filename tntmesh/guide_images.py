# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, replace
from math import ceil, floor
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .assembly import explosion_offsets
from .exporters import is_loose_connector
from .geometry.mesh import bounds
from .model import MeshError, millimeters_per_unit

WIDTH, HEIGHT = 960, 680
BACKGROUND = (0.018, 0.055, 0.084)
PALETTE = (
    (0.15, 0.86, 0.93), (0.64, 0.44, 0.99), (0.99, 0.64, 0.30),
    (0.38, 0.89, 0.60), (0.97, 0.46, 0.62), (0.57, 0.73, 0.99),
)
DIGITS = (
    (7, 5, 5, 5, 7), (2, 6, 2, 2, 7), (7, 1, 7, 4, 7), (7, 1, 7, 1, 7),
    (5, 5, 7, 1, 1), (7, 4, 7, 1, 7), (7, 4, 7, 5, 7), (7, 1, 2, 2, 2),
    (7, 5, 7, 5, 7), (7, 5, 7, 1, 7),
)


@dataclass(frozen=True)
class Surface:
    inverse: Matrix
    tree: BVHTree
    corners: tuple[Vector, ...]
    offset: Vector
    color: tuple[float, float, float]
    loose: bool


def label_view(pixels: np.ndarray, owners: np.ndarray, regions: list[tuple[int, int, int, int]]) -> None:
    reserved = np.zeros((HEIGHT, WIDTH), dtype=bool)
    for piece in sorted(set(np.unique(owners)) - {0}):
        left, bottom, right, top = regions[piece - 1]
        ys, xs = np.where(owners[bottom:top, left:right] == piece)
        distance = (xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2
        point = distance.argmin()
        x, y = int(xs[point]) + left, int(ys[point]) + bottom
        number = f"{piece:02d}"
        half = 8 * len(number) + 5
        # Keep small or partially hidden objects legible by moving their badge to an open spot.
        candidates = [(x, y)] if np.ptp(xs) >= 2 * half + 8 and np.ptp(ys) >= 38 else []
        for radius in (36, 56, 88, 128):
            candidates.extend((
                (x + radius, y), (x - radius, y), (x, y + radius), (x, y - radius),
                (x + radius, y + radius), (x - radius, y + radius),
                (x + radius, y - radius), (x - radius, y - radius),
            ))
        for bx, by in candidates:
            if bx - half < 3 or bx + half >= WIDTH - 3 or by < 18 or by >= HEIGHT - 18:
                continue
            region = np.s_[by - 15:by + 16, bx - half:bx + half + 1]
            if reserved[region].any():
                continue
            if (bx, by) != (x, y):
                length = max(abs(bx - x), abs(by - y)) + 1
                ys = np.linspace(y, by, length).round().astype(int)
                xs = np.linspace(x, bx, length).round().astype(int)
                visible = ~reserved[ys, xs]
                ys, xs = ys[visible], xs[visible]
                pixels[ys, xs, :3] = (.85, .96, 1)
                reserved[ys, xs] = True
            pixels[region][:, :, :3] = (.76, .93, .97)
            pixels[by - 13:by + 14, bx - half + 2:bx + half - 1, :3] = BACKGROUND
            reserved[region] = True
            digit_x = bx - 8 * len(number) + 2
            for digit in number:
                for row, bits in enumerate(DIGITS[int(digit)]):
                    row_y = by + 6 - row * 4
                    for column in range(3):
                        if bits & (4 >> column):
                            start_x = digit_x + 4 * column
                            pixels[row_y:row_y + 4, start_x:start_x + 4, :3] = (.90, .99, 1)
                digit_x += 16
            break


def clearance(
    low: Vector, high: Vector, occupied: list[tuple[Vector, Vector]], axis: int, gap: float,
) -> float:
    other = 1 - axis
    intervals = sorted(
        (a[axis] - high[axis] - gap, b[axis] - low[axis] + gap)
        for a, b in occupied
        if low[other] < b[other] + gap and high[other] > a[other] - gap
    )
    start = end = -float("inf")
    for left, right in intervals:
        if left > end:
            if start < 0 < end:
                return min((start, end), key=abs)
            if left >= 0:
                return 0
            start = left
        end = max(end, right)
    return min((start, end), key=abs) if start < 0 < end else 0


def separate_connectors(
    surfaces: list[Surface], points: list[list[Vector]], horizontal: Vector, vertical: Vector,
) -> None:
    footprints = [bounds(corners) for corners in points]
    lower, upper = bounds(point for box in footprints for point in box)
    gap = (upper - lower).length * .025
    occupied = [box for surface, box in zip(surfaces, footprints, strict=True) if not surface.loose]
    for index, surface in enumerate(surfaces):
        if not surface.loose:
            continue
        low, high = footprints[index]
        # Move an occluded connector to the nearest clear edge in the drawing plane.
        dx, dy = clearance(low, high, occupied, 0, gap), clearance(low, high, occupied, 1, gap)
        if abs(dx) <= abs(dy):
            dy = 0
        else:
            dx = 0
        delta = Vector((dx, dy, 0))
        if delta.length_squared:
            surfaces[index] = replace(surface, offset=surface.offset + horizontal * dx + vertical * dy)
            points[index] = [point + delta for point in points[index]]
        occupied.append((low + delta, high + delta))


def draw_view(surfaces: list[Surface], filepath: Path, exploded: bool) -> None:
    back = Vector((1, -1.4, .85)).normalized()
    horizontal = Vector((0, 0, 1)).cross(back).normalized()
    vertical = back.cross(horizontal)
    reference = surfaces[0].corners[0]
    projected = [
        [Vector((horizontal.dot(point), vertical.dot(point), back.dot(point))) for point in (
            corner - reference + (surface.offset if exploded else Vector((0, 0, 0)))
            for corner in surface.corners
        )]
        for surface in surfaces
    ]
    if exploded:
        separate_connectors(surfaces, projected, horizontal, vertical)
    lower, upper = bounds(point for corners in projected for point in corners)
    size = upper - lower
    stride = max(size.x / (WIDTH - 112), size.y / (HEIGHT - 112), 1e-9)
    center = (lower + upper) / 2
    x_min, y_min = center.x - stride * WIDTH / 2, center.y - stride * HEIGHT / 2
    depth = upper.z + max(size.length * .1, stride * 10)
    origin = reference + back * depth + horizontal * x_min + vertical * y_min
    directions = (-back, horizontal * stride, vertical * stride)
    depths = np.full((HEIGHT, WIDTH), np.inf)
    owners = np.zeros((HEIGHT, WIDTH), dtype=np.int32)
    pixels = np.ones((HEIGHT, WIDTH, 4), dtype=np.float32)
    pixels[:, :, :3] = BACKGROUND
    light = (back * .8 + vertical * .6).normalized()
    regions = []
    for number, (surface, corners) in enumerate(zip(surfaces, projected, strict=True), 1):
        low, high = bounds(corners)
        region = (
            max(0, floor((low.x - x_min) / stride)), max(0, floor((low.y - y_min) / stride)),
            min(WIDTH, ceil((high.x - x_min) / stride) + 1), min(HEIGHT, ceil((high.y - y_min) / stride) + 1),
        )
        regions.append(region)
        left, bottom, right, top = region
        inverse = surface.inverse.to_3x3()
        direction, step_x, step_y = (inverse @ axis for axis in directions)
        ray = direction.normalized()
        factor = 1 / direction.length
        normal_matrix = inverse.transposed()
        start = surface.inverse @ (origin - surface.offset if exploded else origin)
        for y in range(bottom, top):
            row_start = start + y * step_y
            for x in range(left, right):
                _, normal, _, distance = surface.tree.ray_cast(row_start + x * step_x, ray)
                if distance is None or (hit := distance * factor) >= depths[y, x]:
                    continue
                depths[y, x] = hit
                owners[y, x] = number
                shade = .35 + .65 * max(0, (normal_matrix @ normal).normalized().dot(light))
                pixels[y, x, :3] = tuple(value * shade for value in surface.color)

    if not owners.any():
        raise MeshError("The assembly has no visible faces to render.")
    label_view(pixels, owners, regions)
    image = bpy.data.images.new("TNTMesh Guide", WIDTH, HEIGHT, alpha=False)
    try:
        image.pixels.foreach_set(pixels.ravel())
        image.file_format = "PNG"
        image.filepath_raw = str(filepath)
        image.save()
    finally:
        bpy.data.images.remove(image)


def render(
    context: bpy.types.Context, objects: list[bpy.types.Object], files: tuple[Path, Path],
    distance_mm: float,
) -> None:
    depsgraph = context.evaluated_depsgraph_get()
    if not distance_mm:
        lower, upper = bounds(obj.evaluated_get(depsgraph).matrix_world @ Vector(corner)
                              for obj in objects for corner in obj.evaluated_get(depsgraph).bound_box)
        distance = (upper - lower).length * .35
    else:
        distance = distance_mm / millimeters_per_unit(context.scene)
    offsets = explosion_offsets(objects, depsgraph, distance)
    surfaces = []
    for number, (obj, _, offset) in enumerate(offsets):
        evaluated = obj.evaluated_get(depsgraph)
        matrix = evaluated.matrix_world.copy()
        if not evaluated.data.polygons:
            raise MeshError("The assembly contains a piece with no faces.")
        loose = is_loose_connector(obj)
        if not offset.length_squared and loose:
            offset = Vector((0, 1, 0)) * distance
        surfaces.append(Surface(
            matrix.inverted(), BVHTree.FromObject(obj, depsgraph),
            tuple(matrix @ Vector(corner) for corner in evaluated.bound_box),
            offset, PALETTE[number % len(PALETTE)], loose,
        ))
    for filepath, exploded in zip(files, (False, True), strict=True):
        draw_view(surfaces, filepath, exploded)
