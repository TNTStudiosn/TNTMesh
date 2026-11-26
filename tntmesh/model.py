# SPDX-License-Identifier: GPL-3.0-or-later
from contextlib import AbstractContextManager
from uuid import uuid4

import bpy

ROLE = "tntmesh_role"
PART_ID = "tntmesh_part_id"
PROJECT_ID = "tntmesh_project_id"
SCHEMA_VERSION = "tntmesh_schema_version"
DRAFT_ID = "tntmesh_draft_id"
ASSEMBLY_DIRECTION = "tntmesh_assembly_direction"


class MeshError(Exception):
    """A geometry or workflow failure that can be shown to the user."""


def millimeters_per_unit(scene: bpy.types.Scene) -> float:
    units = scene.unit_settings
    return 1.0 if units.system == "NONE" else 1000.0 * units.scale_length


def owned_collection(scene: bpy.types.Scene, role: str) -> bpy.types.Collection:
    for collection in scene.collection.children:
        if collection.get(ROLE) == role and collection.library is None:
            return collection
    name = {
        "source": "TNTMesh · Imported models",
        "part": "TNTMesh · Parts",
        "calibration": "TNTMesh · Calibration Models",
    }[role]
    collection = bpy.data.collections.new(name)
    collection[ROLE] = role
    scene.collection.children.link(collection)
    return collection


class GeometryTransaction(AbstractContextManager):
    """Track only newly created data, disposing it unless it is published."""

    def __init__(self) -> None:
        self.objects: list[bpy.types.Object] = []
        self.meshes: list[bpy.types.Mesh] = []

    def own_mesh(self, mesh: bpy.types.Mesh) -> bpy.types.Mesh:
        self.meshes.append(mesh)
        return mesh

    def object(
        self, collection: bpy.types.Collection, name: str, mesh: bpy.types.Mesh
    ) -> bpy.types.Object:
        obj = bpy.data.objects.new(name, mesh)
        self.objects.append(obj)
        collection.objects.link(obj)
        return obj

    def publish(self, obj: bpy.types.Object) -> None:
        self.objects.remove(obj)

    def remove_object(self, obj: bpy.types.Object) -> None:
        self.objects.remove(obj)
        bpy.data.objects.remove(obj, do_unlink=True)

    def remove_mesh(self, mesh: bpy.types.Mesh) -> None:
        if mesh.users == 0:
            self.meshes.remove(mesh)
            bpy.data.meshes.remove(mesh)

    def __exit__(self, *exc: object) -> None:
        for obj in reversed(self.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in reversed(self.meshes):
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)


def identify_part(obj: bpy.types.Object, project_id: str, part_id: str | None = None) -> None:
    obj[ROLE] = "part"
    obj[PART_ID] = part_id or uuid4().hex
    obj[PROJECT_ID] = project_id
    obj[SCHEMA_VERSION] = 1
