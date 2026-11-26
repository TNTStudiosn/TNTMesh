# SPDX-License-Identifier: GPL-3.0-or-later
from math import isfinite

import bmesh
import bpy

from ..model import MeshError
from .coplanar import coplanar_faces
from .diagnostics import (
    closed_shell,
    enclosing_shells,
    face_shells,
    nonadjacent_overlaps,
    shell_volume,
)
from .mesh import VOLUME_EPSILON, Inspection, inspect


def orient_solid(bm: bmesh.types.BMesh, mesh: bpy.types.Mesh) -> None:
    if (not bm.faces or any(not edge.is_manifold for edge in bm.edges)
            or any(not vertex.is_manifold for vertex in bm.verts)):
        raise MeshError("Close the mesh before correcting its face orientation.")
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.normal_update()
    if any(not edge.is_contiguous for edge in bm.edges):
        raise MeshError("The mesh has open edges or inconsistent face orientation.")

    bm.faces.index_update()
    bm.faces.ensure_lookup_table()
    shells = [closed_shell(faces, shell_volume(faces)) for faces in face_shells(bm)]
    if any(abs(shell.volume) <= VOLUME_EPSILON for shell in shells):
        raise MeshError("The mesh has no positive enclosed volume.")
    bm.to_mesh(mesh)
    mesh.update()
    coordinates = [vertex.co for vertex in mesh.vertices]
    if next(nonadjacent_overlaps(mesh), None) is not None or coplanar_faces(mesh, coordinates):
        raise MeshError("Fix intersecting surfaces before correcting face orientation.")
    flip = []
    for shell, depth, certain in enclosing_shells(mesh, coordinates, shells, set()):
        if not certain:
            raise MeshError("The mesh has ambiguous shell nesting.")
        if (shell.volume < 0) != bool(depth % 2):
            flip.extend(bm.faces[index] for index in shell.faces)
    if flip:
        bmesh.ops.reverse_faces(bm, faces=flip)


def repair_copy(
    mesh: bpy.types.Mesh, weld_mm: float, max_hole_edges: int, *, correct_orientation: bool = False,
) -> Inspection:
    if (not isfinite(weld_mm) or weld_mm < 0
            or (max_hole_edges != 0 and not 3 <= max_hole_edges <= 64)):
        raise MeshError("Check the repair limits.")
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        if any(not all(map(isfinite, vertex.co)) for vertex in bm.verts):
            raise MeshError("The mesh is empty or has invalid coordinates.")
        if weld_mm > 0:
            bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=weld_mm)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=min(weld_mm, 0.00001))
        if max_hole_edges:
            rim = [edge for edge in bm.edges if edge.is_boundary]
            bmesh.ops.holes_fill(bm, edges=rim, sides=max_hole_edges)
        bm.normal_update()
        if correct_orientation:
            orient_solid(bm, mesh)
        elif bm.faces and bm.calc_volume(signed=True) < 0 and all(
            edge.is_manifold and edge.is_contiguous for edge in bm.edges
        ):
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    return inspect(mesh)
