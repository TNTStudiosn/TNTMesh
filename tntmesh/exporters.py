# SPDX-License-Identifier: GPL-3.0-or-later
import re
from collections.abc import Iterator
from contextlib import closing, suppress
from dataclasses import dataclass
from itertools import count
from math import ceil, sqrt
from pathlib import Path
from shutil import copyfileobj
from struct import Struct
from tempfile import TemporaryDirectory
from typing import BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

import bpy
from mathutils import Euler, Vector

from . import stl
from .geometry.mesh import bounds, evaluated_mm, inspect, triangulate
from .model import PART_KIND, GeometryTransaction, MeshError, millimeters_per_unit
from .printing import PrinterProfile
from .three_mf import write_3mf

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f-\x9f\ufffe\uffff]')
_RESERVED_FILENAME = re.compile(r"^(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.I)
_LEGACY_PIN = re.compile(r" · (?:Pin|Pasador) [0-9]+(?:\.[0-9]+)?$", re.I)
_PLY_VERTEX = Struct("<fff")
_PLY_TRIANGLE = Struct("<Biii")


@dataclass(frozen=True)
class ExportOptions:
    as_zip: bool = False
    subfolder: bool = False
    prefix: str = ""
    numbered: bool = True
    on_bed: bool = False
    rotation: tuple[float, float, float] = (0, 0, 0)
    spacing_mm: float = 3
    printer: PrinterProfile | None = None


DEFAULT_OPTIONS = ExportOptions()


def is_loose_connector(obj: bpy.types.Object) -> bool:
    kind = obj.get(PART_KIND)
    return kind == "pin" if kind is not None else bool(_LEGACY_PIN.search(obj.name))


def file_stem(name: str, limit: int = 160) -> str:
    name = _INVALID_FILENAME.sub("_", name).strip(" .")
    if _RESERVED_FILENAME.match(name):
        name = "_" + name
    return name.encode("utf-8")[:limit].decode("utf-8", "ignore").rstrip(" .")


def variants(stem: str) -> Iterator[str]:
    yield stem
    for number in count(2):
        yield f"{stem}_{number}"


class Bed:
    """Place parts in rows using their rotated footprints and the usable build volume."""

    def __init__(self, options: ExportOptions, total: int):
        self.spacing = options.spacing_mm
        self.columns = ceil(sqrt(total))
        self.printer = options.printer
        self.x = self.y = self.row_depth = 0.0
        self.column = 0

    def reserve(self, size: Vector) -> Vector:
        printer = self.printer
        limits = printer.limits if printer else None
        same_row = self.x + size.x <= limits[0] + 0.0001 if limits else self.column < self.columns
        if self.column and not same_row:
            self.x = self.column = 0
            self.y += self.row_depth + self.spacing
            self.row_depth = 0
        if limits and any(value > limit + 0.0001 for value, limit in zip(
            (self.x + size.x, self.y + size.y, size.z), limits, strict=True
        )):
            raise MeshError("The pieces do not fit on one build plate with these settings.")
        margin_x, margin_y = printer.margin_mm[:2] if printer else (0, 0)
        location = Vector((self.x + margin_x, self.y + margin_y, 0))
        self.x += size.x + self.spacing
        self.row_depth = max(self.row_depth, size.y)
        self.column += 1
        return location


def write_obj(mesh: bpy.types.Mesh, output: BinaryIO) -> None:
    output.write(b"# TNTMesh OBJ | millimeters\n")
    for vertex in mesh.vertices:
        x, y, z = vertex.co
        output.write(f"v {x:.9g} {y:.9g} {z:.9g}\n".encode("ascii"))
    for face in mesh.polygons:
        indices = " ".join(str(index + 1) for index in face.vertices)
        output.write(f"f {indices}\n".encode("ascii"))


def write_ply(mesh: bpy.types.Mesh, output: BinaryIO) -> None:
    mesh.calc_loop_triangles()
    output.write((
        "ply\nformat binary_little_endian 1.0\ncomment TNTMesh coordinates in millimeters\n"
        f"element vertex {len(mesh.vertices)}\nproperty float x\nproperty float y\nproperty float z\n"
        f"element face {len(mesh.loop_triangles)}\nproperty list uchar int vertex_indices\nend_header\n"
    ).encode("ascii"))
    for vertex in mesh.vertices:
        output.write(_PLY_VERTEX.pack(*vertex.co))
    for triangle in mesh.loop_triangles:
        output.write(_PLY_TRIANGLE.pack(3, *triangle.vertices))


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
    *, grouped: bool = False, options: ExportOptions = DEFAULT_OPTIONS,
) -> list[Path]:
    if not parts:
        raise MeshError("Select generated pieces to export.")
    extension = format_id.lower()
    if extension not in {"stl", "obj", "fbx", "ply", "3mf"}:
        raise MeshError("Choose STL, OBJ, FBX, PLY or 3MF for export.")
    prefix = file_stem(options.prefix, 64)
    bundle = prefix or "TNTMesh"
    if options.printer and options.on_bed:
        options.printer.validate()
    combined = grouped and extension == "3mf"
    groups = [parts] if combined else [[part] for part in parts]
    with TemporaryDirectory(prefix="tntmesh-export-") as temporary:
        staging = Path(temporary)
        staged = []
        names = set()
        for index, group in enumerate(groups, 1):
            name = file_stem(group[0].name) or "Part"
            stem = (prefix or "TNTMesh_Assembly") if combined else (
                (f"{prefix}_" if prefix else "") +
                (f"{index:02d}_" if options.numbered else "") + name
            )
            for variant in variants(stem):
                if variant.casefold() not in names:
                    names.add(variant.casefold())
                    break
            path = staging / f"{variant}.{extension}"
            with path.open("xb") as output:
                write_group(context, group, name, extension, output, options, combined)
            staged.append(path)
        if options.as_zip:
            archive_path = staging / f"{bundle}.zip"
            with ZipFile(archive_path, mode="x", compression=ZIP_DEFLATED) as archive:
                for path in staged:
                    member = f"{bundle}/{path.name}" if options.subfolder else path.name
                    archive.write(path, member)
            staged = [archive_path]
        return publish_files(staged, directory, bundle if options.subfolder and not options.as_zip else "")


def publish_files(staged: list[Path], directory: Path, folder: str) -> list[Path]:
    created: list[Path] = []
    subfolder = None
    if folder:
        for variant in variants(folder):
            subfolder = directory / variant
            try:
                subfolder.mkdir()
            except FileExistsError:
                continue
            directory = subfolder
            break
    try:
        for source in staged:
            for variant in variants(source.stem):
                path = directory / f"{variant}{source.suffix}"
                try:
                    output = path.open("xb")
                except FileExistsError:
                    continue
                created.append(path)
                with output, source.open("rb") as stream:
                    copyfileobj(stream, output)
                break
    except Exception:
        for path in created:
            with suppress(OSError):
                path.unlink(missing_ok=True)
        if subfolder is not None:
            with suppress(OSError):
                subfolder.rmdir()
        raise
    return created


def write_group(
    context: bpy.types.Context, group: list[bpy.types.Object], name: str, extension: str,
    output: BinaryIO, options: ExportOptions, combined: bool,
) -> None:
    if extension == "3mf":
        with closing(three_mf_parts(context, group, options, combined)) as packets:
            write_3mf(packets, output)
        return
    with GeometryTransaction() as transaction:
        mesh = prepared_mesh(context, transaction, group[0], extension in {"stl", "ply"}, options)
        if extension == "stl":
            stl.write_binary(mesh, output)
        elif extension == "obj":
            write_obj(mesh, output)
        elif extension == "ply":
            write_ply(mesh, output)
        else:
            write_fbx(context, transaction, mesh, name, output)


def prepared_mesh(
    context: bpy.types.Context, transaction: GeometryTransaction, obj: bpy.types.Object,
    triangles: bool, options: ExportOptions, bed: Bed | None = None,
) -> bpy.types.Mesh:
    mesh, _ = evaluated_mm(
        context, obj, transaction, millimeters_per_unit(context.scene), centered=options.on_bed
    )
    if triangles:
        triangulate(mesh)
    inspect(mesh)
    if options.on_bed:
        mesh.transform(Euler(options.rotation, "XYZ").to_matrix().to_4x4())
        minimum, maximum = bounds(vertex.co for vertex in mesh.vertices)
        size = maximum - minimum
        location = bed.reserve(size) if bed else Vector((-size.x / 2, -size.y / 2, 0))
        displacement = location - minimum
        for vertex in mesh.vertices:
            vertex.co += displacement
        mesh.update()
    return mesh


def three_mf_parts(
    context: bpy.types.Context, parts: list[bpy.types.Object],
    options: ExportOptions, combined: bool,
) -> Iterator[tuple[str, bpy.types.Mesh]]:
    bed = Bed(options, len(parts)) if options.on_bed and combined else None
    for obj in parts:
        with GeometryTransaction() as transaction:
            mesh = prepared_mesh(context, transaction, obj, True, options, bed)
            yield file_stem(obj.name) or "Part", mesh
