# SPDX-License-Identifier: GPL-3.0-or-later
import re
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from shutil import copyfileobj
from tempfile import TemporaryDirectory
from typing import BinaryIO

import bpy

from . import stl
from .geometry.mesh import evaluated_mm, inspect, triangulate
from .model import GeometryTransaction, MeshError, millimeters_per_unit
from .three_mf import write_3mf

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def write_obj(mesh: bpy.types.Mesh, output: BinaryIO) -> None:
    output.write(b"# TNTMesh OBJ | millimeters\n")
    for vertex in mesh.vertices:
        x, y, z = vertex.co
        output.write(f"v {x:.9g} {y:.9g} {z:.9g}\n".encode("ascii"))
    for face in mesh.polygons:
        indices = " ".join(str(index + 1) for index in face.vertices)
        output.write(f"f {indices}\n".encode("ascii"))


def write_fbx(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    name: str, output: BinaryIO,
) -> None:
    try:
        bpy.ops.export_scene.fbx.get_rna_type()
    except (AttributeError, KeyError, RuntimeError) as error:
        raise MeshError("Enable Blender's FBX add-on to export FBX.") from error

    obj = transaction.object(context.scene.collection, name, mesh)
    try:
        with TemporaryDirectory(prefix="tntmesh-fbx-") as directory:
            filepath = Path(directory) / "part.fbx"
            with context.temp_override(selected_objects=[obj]):
                status = bpy.ops.export_scene.fbx(
                    filepath=str(filepath), use_selection=True, object_types={"MESH"},
                    apply_unit_scale=False, global_scale=0.001, apply_scale_options="FBX_SCALE_ALL",
                    axis_forward="Y", axis_up="Z", use_mesh_modifiers=False, bake_anim=False,
                    path_mode="STRIP", use_metadata=False,
                )
            if "FINISHED" not in status or not filepath.is_file() or filepath.stat().st_size == 0:
                raise MeshError("Blender could not export the FBX.")
            with filepath.open("rb") as source:
                copyfileobj(source, output)
    finally:
        transaction.remove_object(obj)
        context.view_layer.update()


def export_parts(
    context: bpy.types.Context, parts: list[bpy.types.Object], directory: Path, format_id: str,
    *, grouped: bool = False,
) -> list[Path]:
    extension = format_id.lower()
    if extension not in {"stl", "obj", "fbx", "3mf"}:
        raise MeshError("Choose STL, OBJ, FBX or 3MF for export.")
    created: list[Path] = []
    combined = grouped and extension == "3mf"
    groups = [parts] if combined else [[part] for part in parts]
    try:
        for index, group in enumerate(groups, 1):
            name = _INVALID_FILENAME.sub("_", group[0].name).strip(" .")[:80].rstrip(" .")
            stem = "TNTMesh_Assembly" if combined else f"{index:02d}_{name or 'Part'}"
            suffix = 1
            while True:
                variant = stem if suffix == 1 else f"{stem}_{suffix}"
                path = directory / f"{variant}.{extension}"
                try:
                    output = path.open("xb")
                except FileExistsError:
                    suffix += 1
                else:
                    break
            created.append(path)
            with output:
                if extension == "3mf":
                    with closing(three_mf_parts(context, group)) as packets:
                        write_3mf(packets, output)
                    continue
                with GeometryTransaction() as transaction:
                    mesh = prepared_mesh(context, transaction, group[0], extension == "stl")
                    if extension == "stl":
                        stl.write_binary(mesh, output)
                    elif extension == "obj":
                        write_obj(mesh, output)
                    else:
                        write_fbx(context, transaction, mesh, name, output)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return created


def prepared_mesh(
    context: bpy.types.Context, transaction: GeometryTransaction, obj: bpy.types.Object,
    triangles: bool,
) -> bpy.types.Mesh:
    mesh, _ = evaluated_mm(
        context, obj, transaction, millimeters_per_unit(context.scene), centered=False
    )
    if triangles:
        triangulate(mesh)
    inspect(mesh)
    return mesh


def three_mf_parts(
    context: bpy.types.Context, parts: list[bpy.types.Object],
) -> Iterator[tuple[str, bpy.types.Mesh]]:
    for obj in parts:
        with GeometryTransaction() as transaction:
            mesh = prepared_mesh(context, transaction, obj, triangles=True)
            yield _INVALID_FILENAME.sub("_", obj.name), mesh
