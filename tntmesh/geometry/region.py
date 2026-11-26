# SPDX-License-Identifier: GPL-3.0-or-later
from collections import defaultdict
from dataclasses import dataclass
from math import isfinite

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from ..model import GeometryTransaction, MeshError
from .mesh import inspect, primitive


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


def edge_map(mesh: bpy.types.Mesh) -> dict[tuple[int, int], list[tuple[int, int, int]]]:
    uses = defaultdict(list)
    for face in mesh.polygons:
        points = tuple(face.vertices)
        for start, end in zip(points, points[1:] + points[:1], strict=True):
            uses[min(start, end), max(start, end)].append((face.index, start, end))
    return uses


def grow_selection(
    selected: set[int], uses: dict[tuple[int, int], list[tuple[int, int, int]]], steps: int,
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


def reject_self_intersections(mesh: bpy.types.Mesh) -> None:
    mesh.calc_loop_triangles()
    triangles = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
    points = [vertex.co for vertex in mesh.vertices]
    tree = BVHTree.FromPolygons(points, triangles, all_triangles=True)
    for first, second in tree.overlap(tree):
        if first < second and set(triangles[first]).isdisjoint(triangles[second]):
            raise MeshError("The region cutter folds into itself. Reduce the depth or change the region.")


def cutter_for_region(
    transaction: GeometryTransaction, mesh: bpy.types.Mesh, source: bpy.types.Object,
    config: RegionCut,
) -> bpy.types.Mesh:
    if not isfinite(config.depth) or config.depth <= 0:
        raise MeshError("Choose a positive extraction depth.")
    selected = matching(mesh, source, config)
    uses = edge_map(mesh)
    if config.grow:
        selected = grow_selection(selected, uses, config.grow)
    if not selected:
        raise MeshError("The region has no matching faces.")
    if len(selected) == len(mesh.polygons):
        raise MeshError("Choose a region smaller than the entire model.")
    boundary = []
    for faces in uses.values():
        selected_uses = [edge for edge in faces if edge[0] in selected]
        if len(selected_uses) == 1:
            _, start, end = selected_uses[0]
            boundary.append((start, end))

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
        point = mesh.vertices[vertex].co
        outer.append(point + normal * (lift / alignment))
        inner.append(point - normal * (config.depth / alignment))
    count = len(outer)
    top = [tuple(index[v] for v in mesh.polygons[face].vertices) for face in sorted(selected)]
    bottom = [tuple(vertex + count for vertex in reversed(face)) for face in top]
    walls = [(index[b], index[a], index[a] + count, index[b] + count) for a, b in boundary]
    cutter = primitive(transaction, ".TNTMesh surface region", outer + inner, top + bottom + walls)
    inspect(cutter)
    reject_self_intersections(cutter)
    return cutter
