# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import isfinite

import bpy

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import Connector
from .mesh import inspect
from .region import RegionCut, RegionTool, clean_region_result, cutter_for_region, edge_map
from .region_connector import connect_region


@dataclass(frozen=True)
class MaterialPiece:
    mesh: bpy.types.Mesh
    slot: int
    name: str
    pin: int = 0


def split_materials(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    source: bpy.types.Object, keep_slot: int, depth: float, *,
    smoothing: int = 0, connector: Connector | None = None,
) -> list[MaterialPiece]:
    if not isfinite(depth) or depth <= 0:
        raise MeshError("Choose a positive extraction depth.")
    if not 1 <= keep_slot <= len(mesh.materials):
        raise MeshError("Choose a material slot on the input mesh.")
    slots = {
        face.material_index + 1 for face in mesh.polygons
        if face.material_index < len(mesh.materials)
    }
    if keep_slot not in slots or len(slots) < 2:
        raise MeshError("Assign faces to the retained slot and at least one other material slot.")
    original = inspect(mesh).volume_mm3
    uses = edge_map(mesh)
    engine = ExactBoolean(context, transaction)
    remainder = mesh
    remaining_volume = original
    pieces = []
    tools: dict[int, RegionTool] = {}
    for slot in sorted(slots - {keep_slot}):
        tool = cutter_for_region(
            transaction, mesh, source, RegionCut("MATERIAL", depth, slot, smoothing=smoothing), uses=uses,
        )
        cutter = tool.mesh
        extracted = engine.run(remainder, cutter, "INTERSECT")
        leftover = engine.run(remainder, cutter, "DIFFERENCE")
        clean_region_result(extracted)
        clean_region_result(leftover)
        if connector is None:
            transaction.remove_mesh(cutter)
        else:
            tools[slot] = tool
        if not extracted.polygons or not leftover.polygons:
            raise MeshError("A material cut consumed all remaining geometry or produced no piece.")
        taken_volume = inspect(extracted).volume_mm3
        next_volume = inspect(leftover).volume_mm3
        if abs(taken_volume + next_volume - remaining_volume) > remaining_volume * .001:
            raise MeshError("The split did not preserve the expected volume.")
        if remainder != mesh:
            transaction.remove_mesh(remainder)
        remainder, remaining_volume = leftover, next_volume
        pieces.append(MaterialPiece(extracted, slot, material_label(mesh, slot)))

    if connector is not None:
        joined = []
        for piece in pieces:
            remainder, insert, *pins = connect_region(
                engine, remainder, piece.mesh, tools[piece.slot], connector,
            )
            transaction.remove_mesh(tools[piece.slot].mesh)
            joined.append(MaterialPiece(insert, piece.slot, piece.name))
            joined.extend(MaterialPiece(pin, piece.slot, piece.name, number)
                          for number, pin in enumerate(pins, 1))
        pieces = joined

    return [MaterialPiece(remainder, keep_slot, material_label(mesh, keep_slot)), *pieces]


def material_label(mesh: bpy.types.Mesh, slot: int) -> str:
    material = mesh.materials[slot - 1]
    return material.name if material is not None else ""
