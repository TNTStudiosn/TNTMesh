# SPDX-License-Identifier: GPL-3.0-or-later
from array import array
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from math import isfinite

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from ..model import MeshError
from .coplanar import coplanar_faces
from .mesh import VOLUME_EPSILON, bounds
from .suction import Suction
from .suction import estimate as estimate_suction
from .wall import wall_samples

MAX_MARKS = 256
Marker = tuple[Vector, Vector]


@dataclass(frozen=True)
class Finding:
    kind: str
    count: int
    marks: tuple[Marker, ...]


@dataclass(frozen=True)
class Diagnostics:
    findings: tuple[Finding, ...]
    shells: int
    volume_mm3: float | None
    checked_intersections: bool
    wall_limit_mm: float = 0
    checked_walls: bool = False
    thinnest_wall_mm: float | None = None
    wall_map_mm: array | None = None
    suction: Suction | None = None


@dataclass(frozen=True)
class ClosedShell:
    faces: tuple[int, ...]
    point: Vector
    lower: Vector
    upper: Vector
    volume: float


RAY_DIRECTIONS = tuple(
    Vector(direction).normalized()
    for direction in ((1, .317, .197), (.237, 1, .459), (.387, .167, 1))
)


def ray_parity(tree: BVHTree, origin: Vector, direction: Vector, epsilon: float) -> bool | None:
    hits = 0
    start = origin
    for _ in range(512):
        point, _, _, _ = tree.ray_cast(start, direction)
        if point is None:
            return bool(hits % 2)
        start = point + direction * epsilon
        if start == point:
            return None
        hits += 1
    return None


def enclosing_shells(
    mesh: bpy.types.Mesh, coordinates: list[Vector], shells: list[ClosedShell],
    intersecting_faces: set[int],
) -> Iterator[tuple[ClosedShell, int, bool]]:
    face_shell = {face: index for index, shell in enumerate(shells) for face in shell.faces}
    blocked = {face_shell[face] for face in intersecting_faces}
    triangle_groups = [[] for _ in shells]
    for triangle in mesh.loop_triangles:
        triangle_groups[face_shell[triangle.polygon_index]].append(tuple(triangle.vertices))
    # Construct one tree at a time. Nested cases reuse it across all candidate children.
    nesting = [0] * len(shells)
    uncertain = blocked.copy()
    for parent_id, parent in enumerate(shells):
        candidates = []
        for index, child in enumerate(shells):
            if (index != parent_id and all(
                parent.lower[axis] < child.lower[axis] and child.upper[axis] < parent.upper[axis]
                for axis in range(3)
            )):
                candidates.append(index)
        if not candidates:
            continue
        if parent_id in blocked:
            uncertain.update(candidates)
            continue
        tree = BVHTree.FromPolygons(coordinates, triangle_groups[parent_id], all_triangles=True)
        epsilon = max(.000001, (parent.upper - parent.lower).length * 2e-7)
        for child_id in candidates:
            if child_id in blocked:
                continue
            parity = {ray_parity(tree, shells[child_id].point, ray, epsilon) for ray in RAY_DIRECTIONS}
            if parity == {True}:
                nesting[child_id] += 1
            elif parity != {False}:
                uncertain.add(child_id)
    for index, shell in enumerate(shells):
        yield shell, nesting[index], index not in uncertain


def nonadjacent_overlaps(mesh: bpy.types.Mesh) -> Iterator[tuple[int, int]]:
    mesh.calc_loop_triangles()
    triangles = [tuple(item.vertices) for item in mesh.loop_triangles]
    if not triangles:
        return
    tree = BVHTree.FromPolygons([vertex.co for vertex in mesh.vertices], triangles, all_triangles=True)
    for first, second in tree.overlap(tree):
        if first < second and set(triangles[first]).isdisjoint(triangles[second]):
            yield first, second


def face_shells(bm: bmesh.types.BMesh) -> Iterator[list[bmesh.types.BMFace]]:
    remaining = set(bm.faces)
    for first in bm.faces:
        if first not in remaining:
            continue
        remaining.remove(first)
        shell = [first]
        queue = deque(shell)
        while queue:
            for edge in queue.popleft().edges:
                for neighbor in edge.link_faces:
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
                        shell.append(neighbor)
        yield shell


def shell_volume(faces: list[bmesh.types.BMFace]) -> float:
    origin = faces[0].verts[0].co
    volume = 0.0
    for face in faces:
        points = [vertex.co - origin for vertex in face.verts]
        for first, second in zip(points[1:-1], points[2:], strict=True):
            volume += points[0].dot(first.cross(second))
    return volume / 6


def closed_shell(faces: list[bmesh.types.BMFace], volume: float) -> ClosedShell:
    lower, upper = bounds(vertex.co for face in faces for vertex in face.verts)
    return ClosedShell(tuple(face.index for face in faces), faces[0].calc_center_median(),
                       lower, upper, volume)


def scan(
    mesh: bpy.types.Mesh, weld_mm: float, fragment_mm3: float, *, intersections: bool, wall_mm: float = 0,
    wall_map: bool = False, print_direction: Vector | None = None, suction_step_mm: float = .6,
    suction_progress: Callable[[float], None] | None = None,
) -> Diagnostics:
    if not all(isfinite(number) and number >= 0 for number in (weld_mm, fragment_mm3, wall_mm)):
        raise MeshError("Choose nonnegative mesh tolerances.")
    intersections = intersections or print_direction is not None
    if not mesh.polygons:
        return Diagnostics((Finding("EMPTY", 1, ()),), 0, None, False, wall_mm)
    if any(not all(map(isfinite, vertex.co)) for vertex in mesh.vertices):
        return Diagnostics((Finding("INVALID", 1, ()),), 0, None, False, wall_mm)

    counts: dict[str, int] = defaultdict(int)
    markers: dict[str, list[Marker]] = defaultdict(list)

    def mark(kind: str, point: Vector, end: Vector | None = None) -> None:
        counts[kind] += 1
        if len(markers[kind]) < MAX_MARKS:
            markers[kind].append((point.copy(), point.copy() if end is None else end.copy()))

    bm = bmesh.new()
    shell_count = 0
    closed_shells = []
    try:
        bm.from_mesh(mesh)
        for edge in bm.edges:
            first, second = edge.verts
            if edge.is_boundary:
                mark("OPEN", first.co, second.co)
            elif not edge.is_manifold:
                mark("NON_MANIFOLD", first.co, second.co)
            elif not edge.is_contiguous:
                mark("WINDING", first.co, second.co)
            if edge.calc_length() <= 0:
                mark("ZERO_EDGE", first.co, second.co)
        for vertex in bm.verts:
            if not vertex.is_manifold and not vertex.is_boundary and (
                not vertex.link_edges or all(edge.is_manifold for edge in vertex.link_edges)
            ):
                mark("NON_MANIFOLD", vertex.co)
        topology_ok = not any(counts.get(kind) for kind in ("OPEN", "NON_MANIFOLD", "WINDING"))
        shells = list(face_shells(bm))
        shell_count = len(shells)
        volumes = [shell_volume(shell) for shell in shells] if topology_ok else []
        volume = sum(volumes) if topology_ok else None
        if volume is not None and volume <= VOLUME_EPSILON:
            mark("VOLUME", next(iter(bm.faces)).calc_center_median())
        if shell_count == 1 and volume is not None and volume < -VOLUME_EPSILON:
            mark("INVERTED", next(iter(bm.faces)).calc_center_median())
        if shell_count > 1:
            bm.faces.index_update()
            for index, shell in enumerate(shells):
                center = shell[0].calc_center_median()
                mark("SHELLS", center)
                if topology_ok and 0 < volumes[index] < fragment_mm3:
                    mark("FRAGMENT", center)
                if topology_ok and intersections:
                    closed_shells.append(closed_shell(shell, volumes[index]))
    finally:
        bm.free()

    coordinates = [vertex.co for vertex in mesh.vertices]
    if weld_mm > 0:
        tree = KDTree(len(coordinates))
        for index, point in enumerate(coordinates):
            tree.insert(point, index)
        tree.balance()
        for index, point in enumerate(coordinates):
            if any(other != index and distance <= weld_mm
                   for _, other, distance in tree.find_n(point, 2)):
                mark("DUP_VERT", point)

    exact_faces = set()
    for face in mesh.polygons:
        key = tuple(sorted(tuple(coordinates[index]) for index in face.vertices))
        if key in exact_faces:
            mark("DUP_FACE", face.center)
        exact_faces.add(key)
    mesh.calc_loop_triangles()
    for triangle in mesh.loop_triangles:
        first, second, third = (coordinates[index] for index in triangle.vertices)
        if (second - first).cross(third - first).length_squared <= 1e-20:
            mark("DEGENERATE", (first + second + third) / 3)
    if intersections:
        affected = set()
        for first, second in nonadjacent_overlaps(mesh):
            affected.add(mesh.loop_triangles[first].polygon_index)
            affected.add(mesh.loop_triangles[second].polygon_index)
        for index in sorted(affected):
            mark("INTERSECTION", mesh.polygons[index].center)
        overlapping = coplanar_faces(mesh, coordinates)
        for index in sorted(overlapping):
            mark("COPLANAR", mesh.polygons[index].center)
        if closed_shells:
            for shell, depth, certain in enclosing_shells(mesh, coordinates, closed_shells,
                                                         affected | overlapping):
                if not certain:
                    continue
                if depth % 2 and shell.volume < -VOLUME_EPSILON:
                    mark("CAVITY", shell.point)
                elif depth % 2 and shell.volume > VOLUME_EPSILON:
                    mark("INTERNAL", shell.point)
                elif shell.volume < -VOLUME_EPSILON:
                    mark("INVERTED", shell.point)

    wall_geometry_ok = topology_ok and not any(counts.get(kind) for kind in (
        "VOLUME", "DEGENERATE", "DUP_FACE", "INTERSECTION", "COPLANAR", "INVERTED", "INTERNAL",
    ))
    checked_walls = (wall_mm > 0 or wall_map) and wall_geometry_ok
    thinnest = None
    measures = None
    if checked_walls:
        if wall_map:
            measures = array("f", (-1.0,)) * len(mesh.loop_triangles)
        thin_faces = set()
        for sample in wall_samples(mesh, coordinates, wall_mm, detailed=wall_map):
            thickness = sample.thickness
            if measures is not None:
                measures[sample.triangle] = thickness
            if thickness >= wall_mm:
                continue
            if thinnest is None or thickness < thinnest:
                thinnest = thickness
            if sample.face not in thin_faces:
                thin_faces.add(sample.face)
                mark("THIN_WALL", sample.start, sample.end)

    report = None
    if print_direction is not None and wall_geometry_ok:
        report = estimate_suction(mesh, print_direction, suction_step_mm, MAX_MARKS, suction_progress)
        for pocket in report.pockets:
            mark("SUCTION", pocket.center)
        if report.count:
            counts["SUCTION"] = report.count
    findings = tuple(Finding(kind, count, tuple(markers[kind])) for kind, count in counts.items())
    return Diagnostics(findings, shell_count, volume, intersections, wall_mm, checked_walls, thinnest, measures, report)
