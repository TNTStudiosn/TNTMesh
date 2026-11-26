# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import isfinite

import bmesh
import bpy

from .geometry.coplanar import coplanar_faces
from .geometry.diagnostics import (
    closed_shell,
    enclosing_shells,
    face_shells,
    nonadjacent_overlaps,
    shell_volume,
)
from .geometry.mesh import evaluated_mm, inspect
from .localization import tr
from .model import GeometryTransaction, MeshError, millimeters_per_unit


@dataclass(frozen=True)
class Material:
    technology: str
    density: float
    price_per_kg: float
    currency: str
    wall_mm: float
    infill: float
    extra: float
    check_cavities: bool

    def validate(self) -> None:
        values = self.density, self.price_per_kg, self.wall_mm, self.infill, self.extra
        if (self.technology not in {"FDM", "RESIN"} or not all(map(isfinite, values))
                or self.density <= 0 or min(self.price_per_kg, self.wall_mm) < 0
                or not 0 <= self.infill <= 1 or not 0 <= self.extra <= 5
                or not self.currency or not self.currency.isalpha() or not self.currency.isascii()
                or len(self.currency) > 5):
            raise MeshError("Check the material, currency and estimate settings.")


@dataclass(frozen=True)
class PieceEstimate:
    name: str
    model_ml: float
    printed_ml: float
    extra_ml: float
    grams: float
    cost: float
    saved_ml: float | None


@dataclass(frozen=True)
class Estimate:
    entries: tuple[PieceEstimate, ...]
    total: PieceEstimate


def closed_cavity_volume(mesh: bpy.types.Mesh, model_mm3: float, shells: int) -> float | None:
    if shells == 1:
        return 0.0
    coordinates = [vertex.co for vertex in mesh.vertices]
    if next(nonadjacent_overlaps(mesh), None) is not None or coplanar_faces(mesh, coordinates):
        return None
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.index_update()
        surfaces = [closed_shell(faces, shell_volume(faces)) for faces in face_shells(bm)]
    finally:
        bm.free()
    outer = 0.0
    for shell, depth, certain in enclosing_shells(mesh, coordinates, surfaces, set()):
        if not certain or (shell.volume < 0) != bool(depth % 2):
            return None
        if depth == 0:
            outer += shell.volume
    return max(0.0, outer - model_mm3)


def piece_estimate(mesh: bpy.types.Mesh, name: str, material: Material) -> PieceEstimate:
    solid = inspect(mesh)
    volume = solid.volume_mm3
    saved = None
    if material.technology == "FDM":
        walls = min(volume, sum(face.area for face in mesh.polygons) * material.wall_mm)
        printed = walls + (volume - walls) * material.infill
    else:
        printed = volume
        if material.check_cavities:
            saved = closed_cavity_volume(mesh, volume, solid.shells)
    extra = printed * material.extra
    grams = (printed + extra) * material.density / 1000
    return PieceEstimate(name, volume / 1000, printed / 1000, extra / 1000, grams,
                         grams * material.price_per_kg / 1000, saved / 1000 if saved is not None else None)


def estimate(
    context: bpy.types.Context, objects: list[bpy.types.Object], material: Material,
) -> Estimate:
    if not objects:
        raise MeshError("Choose at least one mesh for the estimate.")
    material.validate()
    unit = millimeters_per_unit(context.scene)
    entries = []
    with GeometryTransaction() as transaction:
        for obj in objects:
            hidden = obj.hide_get()
            try:
                if hidden:
                    obj.hide_set(False)
                    context.view_layer.update()
                mesh, _ = evaluated_mm(context, obj, transaction, unit)
                entries.append(piece_estimate(mesh, obj.name, material))
                transaction.remove_mesh(mesh)
            except MeshError as error:
                message = tr("Cannot estimate {name} · {reason}").format(name=obj.name, reason=tr(str(error)))
                raise MeshError(message) from error
            finally:
                if hidden:
                    obj.hide_set(True)
    saved = sum(item.saved_ml for item in entries) if all(item.saved_ml is not None for item in entries) else None
    return Estimate(tuple(entries), PieceEstimate(
        "", sum(item.model_ml for item in entries), sum(item.printed_ml for item in entries),
        sum(item.extra_ml for item in entries), sum(item.grams for item in entries),
        sum(item.cost for item in entries), saved,
    ))
