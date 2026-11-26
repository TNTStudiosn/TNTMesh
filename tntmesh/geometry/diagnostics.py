# SPDX-License-Identifier: GPL-3.0-or-later
from collections import defaultdict, deque
from collections.abc import Iterator
from dataclasses import dataclass
from math import isfinite

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from ..model import MeshError
from .mesh import VOLUME_EPSILON

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


def scan(
    mesh: bpy.types.Mesh, weld_mm: float, fragment_mm3: float, *, intersections: bool,
) -> Diagnostics:
    if not all(isfinite(number) and number >= 0 for number in (weld_mm, fragment_mm3)):
        raise MeshError("Choose nonnegative mesh tolerances.")
    if not mesh.polygons:
        return Diagnostics((Finding("EMPTY", 1, ()),), 0, None, False)
    if any(not all(map(isfinite, vertex.co)) for vertex in mesh.vertices):
        return Diagnostics((Finding("INVALID", 1, ()),), 0, None, False)

    counts: dict[str, int] = defaultdict(int)
    markers: dict[str, list[Marker]] = defaultdict(list)

    def mark(kind: str, point: Vector, end: Vector | None = None) -> None:
        counts[kind] += 1
        if len(markers[kind]) < MAX_MARKS:
            markers[kind].append((point.copy(), point.copy() if end is None else end.copy()))

    bm = bmesh.new()
    shells = []
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
        volume = sum(map(shell_volume, shells)) if topology_ok else None
        if volume is not None and volume <= VOLUME_EPSILON:
            mark("VOLUME", next(iter(bm.faces)).calc_center_median())
        if len(shells) > 1:
            for shell in shells:
                center = shell[0].calc_center_median()
                mark("SHELLS", center)
                if topology_ok and 0 < shell_volume(shell) < fragment_mm3:
                    mark("FRAGMENT", center)
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

    findings = tuple(Finding(kind, count, tuple(markers[kind])) for kind, count in counts.items())
    return Diagnostics(findings, len(shells), volume, intersections)
