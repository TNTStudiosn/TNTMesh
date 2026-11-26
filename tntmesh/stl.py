# SPDX-License-Identifier: GPL-3.0-or-later
import struct
from math import isfinite
from pathlib import Path
from typing import BinaryIO

import bmesh
import bpy

from .model import MeshError, millimeters_per_unit

_HEADER = b"TNTMesh | millimeters".ljust(80, b"\0")
_COUNT = struct.Struct("<I")
_TRIANGLE = struct.Struct("<12fH")


def import_model(
    context: bpy.types.Context, path: Path, source_scale: float
) -> bpy.types.Object:
    before = set(context.scene.objects)
    try:
        status = bpy.ops.wm.stl_import(
            filepath=str(path),
            global_scale=1.0,
            use_scene_unit=False,
            use_mesh_validate=True,
        )
        imported = set(context.scene.objects) - before
        if len(imported) != 1 or "FINISHED" not in status:
            raise MeshError("Blender could not import the STL.")
        obj = imported.pop()
        if (obj.type != "MESH" or not obj.data.polygons
                or any(not all(map(isfinite, vertex.co)) for vertex in obj.data.vertices)):
            raise MeshError("The STL has no faces or contains invalid coordinates.")
    except Exception:
        for imported_obj in set(context.scene.objects) - before:
            data = imported_obj.data
            bpy.data.objects.remove(imported_obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
        raise
    scale = source_scale / millimeters_per_unit(context.scene)
    obj.scale *= scale
    return obj


def write_binary(mesh: bpy.types.Mesh, output: BinaryIO) -> None:
    mesh.calc_loop_triangles()
    output.write(_HEADER)
    output.write(_COUNT.pack(len(mesh.loop_triangles)))
    for triangle in mesh.loop_triangles:
        points = [mesh.vertices[index].co for index in triangle.vertices]
        normal = (points[1] - points[0]).cross(points[2] - points[0]).normalized()
        output.write(_TRIANGLE.pack(*normal, *points[0], *points[1], *points[2], 0))


def triangulate_for_stl(mesh: bpy.types.Mesh) -> None:
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.triangulate(bm, faces=list(bm.faces), quad_method="BEAUTY", ngon_method="BEAUTY")
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update()
