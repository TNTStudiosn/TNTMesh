# SPDX-License-Identifier: GPL-3.0-or-later
from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError

VOLUME_EPSILON = 1e-10
BOOLEAN_VOLUME_NOISE = 1e-5


@dataclass(frozen=True)
class Inspection:
    volume_mm3: float
    shells: int


def absolute_volume(mesh: bpy.types.Mesh) -> float:
    if not mesh.polygons:
        return 0.0
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        return abs(bm.calc_volume(signed=True))
    finally:
        bm.free()


def inspect(mesh: bpy.types.Mesh) -> Inspection:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        if not bm.faces or any(not all(map(isfinite, vertex.co)) for vertex in bm.verts):
            raise MeshError("The mesh is empty or has invalid coordinates.")
        if any(not edge.is_manifold or not edge.is_contiguous for edge in bm.edges):
            raise MeshError("The mesh has open edges or inconsistent face orientation.")
        if any(not vertex.is_manifold for vertex in bm.verts):
            raise MeshError("The mesh has non-manifold vertices.")
        if any(face.calc_area() <= 0.0 for face in bm.faces):
            raise MeshError("The mesh has degenerate faces.")
        volume = bm.calc_volume(signed=True)
        if not isfinite(volume) or volume <= VOLUME_EPSILON:
            raise MeshError("The mesh has no positive enclosed volume.")
        remaining = set(bm.faces)
        shells = 0
        while remaining:
            shells += 1
            pending = [remaining.pop()]
            while pending:
                for edge in pending.pop().edges:
                    for neighbor in edge.link_faces:
                        if neighbor in remaining:
                            remaining.remove(neighbor)
                            pending.append(neighbor)
        return Inspection(volume, shells)
    finally:
        bm.free()


def bounds(coordinates: Iterable[Vector]) -> tuple[Vector, Vector]:
    points = iter(coordinates)
    try:
        first = next(points)
    except StopIteration:
        raise MeshError("The mesh is empty or has invalid coordinates.") from None
    lower, upper = first.copy(), first.copy()
    for point in points:
        for axis in range(3):
            lower[axis] = min(lower[axis], point[axis])
            upper[axis] = max(upper[axis], point[axis])
    return lower, upper


def weld_collapsed_edges(mesh: bpy.types.Mesh) -> None:
    # Exact Booleans can put adjacent vertices at the same float coordinate.
    # Only weld edges on collapsed faces to preserve nearby source detail.
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


def evaluated_mm(
    context: bpy.types.Context,
    source: bpy.types.Object,
    transaction: GeometryTransaction,
    mm_per_unit: float,
    *,
    centered: bool = True,
) -> tuple[bpy.types.Mesh, Vector]:
    depsgraph = context.evaluated_depsgraph_get()
    evaluated = source.evaluated_get(depsgraph)
    world = evaluated.matrix_world.copy()
    determinant = world.to_3x3().determinant()
    if not isfinite(determinant) or determinant == 0.0:
        raise MeshError("The object transform is singular.")
    mesh = transaction.own_mesh(
        bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
    )
    if not mesh.vertices:
        raise MeshError("The mesh is empty or has invalid coordinates.")
    origin = world.translation.copy()
    if centered:
        local_lower, local_upper = bounds(vertex.co for vertex in mesh.vertices)
        local_center = (local_lower + local_upper) * 0.5
        origin = world @ local_center
        # Apply the linear transform around the local center to retain small model detail.
        transform = world.to_3x3().to_4x4() @ Matrix.Translation(-local_center)
    else:
        transform = world
        origin.zero()
    mesh.transform(Matrix.Scale(mm_per_unit, 4) @ transform)
    if determinant < 0.0:
        mesh.flip_normals()
    mesh.update()
    return mesh, origin


def primitive(
    transaction: GeometryTransaction, name: str, vertices: list, faces: list
) -> bpy.types.Mesh:
    mesh = transaction.own_mesh(bpy.data.meshes.new(name))
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def triangulate(mesh: bpy.types.Mesh) -> None:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
