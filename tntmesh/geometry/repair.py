# SPDX-License-Identifier: GPL-3.0-or-later
from math import isfinite

import bmesh
import bpy

from ..model import MeshError
from .mesh import Inspection, inspect


def repair_copy(mesh: bpy.types.Mesh, weld_mm: float, max_hole_edges: int) -> Inspection:
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
        if bm.faces and bm.calc_volume(signed=True) < 0 and all(
            edge.is_manifold and edge.is_contiguous for edge in bm.edges
        ):
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.to_mesh(mesh)
        mesh.update()
    finally:
        bm.free()
    return inspect(mesh)
