# SPDX-License-Identifier: GPL-3.0-or-later
from collections import defaultdict
from dataclasses import dataclass
from math import isfinite

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..model import GeometryTransaction, MeshError
from .connector import Connector
from .diagnostics import nonadjacent_overlaps
from .mesh import inspect, primitive

EdgeUses = dict[tuple[int, int], list[tuple[int, int, int]]]


@dataclass(frozen=True)
class RegionCut:
    method: str = "SELECTION"
    depth: float = 2.0
    slot: int = 1
    attribute: str = ""
    color: tuple[float, float, float] = (1.0, 0.0, 0.0)
    tolerance: float = 0.05
    weight: float = 0.5
    grow: int = 0
    smoothing: int = 0
    connector: Connector | None = None


@dataclass(frozen=True)
class RegionTool:
    mesh: bpy.types.Mesh
    inner_faces: range


def matching(
    mesh: bpy.types.Mesh, source: bpy.types.Object, config: RegionCut,
) -> set[int]:
    if config.method == "SELECTION":
        return {face.index for face in mesh.polygons if face.select}
    if config.method == "MATERIAL":
        # A slot with no material still identifies a region explicitly assigned to it.
        if not 1 <= config.slot <= len(mesh.materials):
            raise MeshError("Choose a material slot on the input mesh.")
        return {face.index for face in mesh.polygons if face.material_index == config.slot - 1}
    if config.method == "FACE_MASK":
        attribute = mesh.attributes.get(config.attribute)
        if attribute is None or attribute.data_type != "BOOLEAN" or attribute.domain != "FACE":
            raise MeshError("Choose a Boolean attribute on the face domain.")
        return {face.index for face in mesh.polygons if attribute.data[face.index].value}
    if config.method == "VERTEX_GROUP":
        group = source.vertex_groups.get(config.attribute)
        if group is None:
            raise MeshError("Choose a vertex group on the input object.")
        selected = {
            vertex.index for vertex in mesh.vertices if any(
                member.group == group.index and member.weight >= config.weight
                for member in vertex.groups
            )
        }
        return {face.index for face in mesh.polygons if selected.issuperset(face.vertices)}
    if config.method == "COLOR":
        attribute = mesh.color_attributes.get(config.attribute)
        if attribute is None or attribute.domain not in {"POINT", "CORNER", "FACE"}:
            raise MeshError("Choose a color attribute on the input mesh.")
        channels = {index for index, value in enumerate(attribute.data) if sum(
            (value.color[channel] - config.color[channel]) ** 2 for channel in range(3)
        ) <= config.tolerance**2}
        indices = {
            "POINT": lambda face: face.vertices,
            "CORNER": lambda face: face.loop_indices,
            "FACE": lambda face: (face.index,),
        }[attribute.domain]
        return {face.index for face in mesh.polygons if channels.issuperset(indices(face))}
    raise MeshError("Choose a region source.")


def edge_map(mesh: bpy.types.Mesh) -> EdgeUses:
    uses = defaultdict(list)
    for face in mesh.polygons:
        points = tuple(face.vertices)
        for start, end in zip(points, points[1:] + points[:1], strict=True):
            uses[min(start, end), max(start, end)].append((face.index, start, end))
    return uses


def grow_selection(
    selected: set[int], uses: EdgeUses, steps: int,
) -> set[int]:
    neighbors = [(faces[0][0], faces[1][0]) for faces in uses.values() if len(faces) == 2]
    for _ in range(abs(steps)):
        add = set()
        remove = set()
        for first, second in neighbors:
            has_first, has_second = first in selected, second in selected
            if has_first != has_second:
                add.add(second if has_first else first)
                remove.add(first if has_first else second)
        updated = selected | add if steps > 0 else selected - remove
        if updated == selected:
            break
        selected = updated
    return selected


def region_faces(mesh: bpy.types.Mesh, source: bpy.types.Object, config: RegionCut) -> set[int]:
    selected = matching(mesh, source, config)
    return grow_selection(selected, edge_map(mesh), config.grow) if config.grow else selected


def boundary_edges(selected: set[int], uses: EdgeUses) -> list[tuple[int, int]]:
    boundary = []
    for faces in uses.values():
        selected_uses = [edge for edge in faces if edge[0] in selected]
        if len(selected_uses) == 1:
            _, start, end = selected_uses[0]
            boundary.append((start, end))
    return boundary


def smooth_boundary(
    mesh: bpy.types.Mesh, positions: list[Vector], boundary: list[tuple[int, int]], passes: int,
) -> dict[int, Vector]:
    if not passes or not boundary:
        return {}
    if not 1 <= passes <= 12:
        raise MeshError("Choose between zero and twelve smoothing passes.")
    neighbors = defaultdict(set)
    for start, end in boundary:
        neighbors[start].add(end)
        neighbors[end].add(start)
    mesh.calc_loop_triangles()
    # Restrict projection to the immediate surface around the original boundary.
    # This prevents a contour from snapping onto another nearby sheet.
    local = [tuple(triangle.vertices) for triangle in mesh.loop_triangles
             if any(index in neighbors for index in triangle.vertices)]
    if not local:
        return {}
    tree = BVHTree.FromPolygons(positions, local, all_triangles=True)
    limits = {
        index: min((positions[index] - positions[neighbor]).length for neighbor in adjacent) * .45
        for index, adjacent in neighbors.items()
    }
    positions_by_index = {index: positions[index] for index in neighbors}
    for _ in range(passes):
        updated = positions_by_index.copy()
        for index, adjacent in neighbors.items():
            if len(adjacent) != 2 or limits[index] == 0:
                continue
            first, second = sorted(adjacent)
            origin = positions[index]
            target = (positions_by_index[first] + positions_by_index[second]) / 2
            candidate = positions_by_index[index].lerp(target, .35)
            delta = candidate - origin
            limit = limits[index]
            if delta.length > limit:
                candidate = origin + delta.normalized() * limit
            projected, _, face, _ = tree.find_nearest(candidate, limit)
            if (projected is not None and index in local[face]
                    and (projected - origin).length <= limit + limit * 1e-5):
                updated[index] = projected
        positions_by_index = updated
    return positions_by_index


def reject_self_intersections(mesh: bpy.types.Mesh) -> None:
    if next(nonadjacent_overlaps(mesh), None) is not None:
        raise MeshError("The region cutter folds into itself. Reduce the depth or change the region.")


def clean_region_result(mesh: bpy.types.Mesh) -> None:
    # The exact solver can introduce coincident float coordinates where the
    # cutter follows source edges. Limit the weld to vertices of zero-area faces.
    epsilon = .00001
    if not any(face.area <= 0 for face in mesh.polygons):
        return
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        for _ in range(3):
            affected = {
                vertex for face in bm.faces if face.calc_area() <= 0
                for edge in face.edges if edge.calc_length() <= epsilon
                for vertex in edge.verts
            }
            if not affected:
                break
            bmesh.ops.remove_doubles(bm, verts=list(affected), dist=epsilon)
            bm.normal_update()
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()


def cutter_for_region(
    transaction: GeometryTransaction, mesh: bpy.types.Mesh, source: bpy.types.Object,
    config: RegionCut, *, uses: EdgeUses | None = None,
) -> RegionTool:
    if not isfinite(config.depth) or config.depth <= 0:
        raise MeshError("Choose a positive extraction depth.")
    selected = matching(mesh, source, config)
    if uses is None:
        uses = edge_map(mesh)
    if config.grow:
        selected = grow_selection(selected, uses, config.grow)
    if not selected:
        raise MeshError("The region has no matching faces.")
    if len(selected) == len(mesh.polygons):
        raise MeshError("Choose a region smaller than the entire model.")
    boundary = boundary_edges(selected, uses)
    smoothed = (
        smooth_boundary(mesh, [vertex.co for vertex in mesh.vertices], boundary, config.smoothing)
        if config.smoothing else {}
    )

    incident = defaultdict(list)
    for face_id in sorted(selected):
        face = mesh.polygons[face_id]
        for vertex in face.vertices:
            incident[vertex].append(face)
    index = {vertex: i for i, vertex in enumerate(sorted(incident))}
    outer, inner = [], []
    lift = min(0.02, config.depth * 0.1)
    for vertex in index:
        faces = incident[vertex]
        normal = sum((face.normal * face.area for face in faces), Vector((0, 0, 0))).normalized()
        alignment = min(normal.dot(face.normal) for face in faces)
        if alignment < 0.18:
            raise MeshError("The region has a sharp fold. Select a smaller patch.")
        point = smoothed.get(vertex, mesh.vertices[vertex].co)
        outer.append(point + normal * (lift / alignment))
        inner.append(point - normal * (config.depth / alignment))
    count = len(outer)
    top = [tuple(index[v] for v in mesh.polygons[face].vertices) for face in sorted(selected)]
    bottom = [tuple(vertex + count for vertex in reversed(face)) for face in top]
    walls = [(index[b], index[a], index[a] + count, index[b] + count) for a, b in boundary]
    cutter = primitive(transaction, ".TNTMesh surface region", outer + inner, top + bottom + walls)
    inspect(cutter)
    reject_self_intersections(cutter)
    return RegionTool(cutter, range(len(top), len(top) + len(bottom)))
