# SPDX-License-Identifier: GPL-3.0-or-later
from uuid import UUID, uuid5

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Matrix

from .geometry.mesh import evaluated_mm
from .geometry.planar import split
from .localization import tr
from .model import (
    DRAFT_ID,
    PART_ID,
    ROLE,
    GeometryTransaction,
    MeshError,
    identify_part,
    millimeters_per_unit,
    owned_collection,
)
from .settings import TNTMESH_PG_settings

SOURCE = "source"
SCHEMA = 1


class TNTMESH_PG_draft_cut(bpy.types.PropertyGroup):
    uid: StringProperty()
    target: StringProperty(default=SOURCE)
    enabled: BoolProperty(name="Run this cut", default=True)
    settings: PointerProperty(type=TNTMESH_PG_settings)


class TNTMESH_PG_draft_plan(bpy.types.PropertyGroup):
    uid: StringProperty()
    schema: IntProperty(default=SCHEMA)
    source: PointerProperty(type=bpy.types.Object)
    cuts: CollectionProperty(type=TNTMESH_PG_draft_cut)
    cut_index: IntProperty(min=0)


CLASSES = (TNTMESH_PG_draft_cut, TNTMESH_PG_draft_plan)


def active_plan(scene: bpy.types.Scene) -> TNTMESH_PG_draft_plan | None:
    return (
        scene.tntmesh_drafts[scene.tntmesh_draft_index]
        if scene.tntmesh_draft_index < len(scene.tntmesh_drafts)
        else None
    )


def active_cut(plan: TNTMESH_PG_draft_plan) -> TNTMESH_PG_draft_cut | None:
    return plan.cuts[plan.cut_index] if plan.cut_index < len(plan.cuts) else None


def cut_outputs(cut: TNTMESH_PG_draft_cut) -> tuple[str, str]:
    return cut.uid + ":1", cut.uid + ":2"


def target_label(plan: TNTMESH_PG_draft_plan, key: str) -> str:
    if key == SOURCE:
        return tr("Source model")
    for cut in plan.cuts:
        for index, output in enumerate(cut_outputs(cut), 1):
            if key == output:
                return f"{cut.name} · {index:02d}"
    return tr("Missing target")


def free_targets(plan: TNTMESH_PG_draft_plan, before: int) -> list[str]:
    available = {SOURCE: None}
    for index in range(before):
        cut = plan.cuts[index]
        if cut.enabled and cut.target in available:
            del available[cut.target]
            available.update(dict.fromkeys(cut_outputs(cut)))
    return list(available)


class DraftError(MeshError):
    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(operation, reason)
        self.operation = operation
        self.reason = reason

    def __str__(self) -> str:
        return tr("Cut “{name}” · {reason}").format(name=self.operation, reason=tr(self.reason))


def order(plan: TNTMESH_PG_draft_plan) -> list[TNTMESH_PG_draft_cut]:
    seen: set[str] = set()
    available = {SOURCE}
    operations = []
    for cut in plan.cuts:
        if not cut.uid or cut.uid in seen:
            raise MeshError("The draft contains invalid cut identifiers.")
        seen.add(cut.uid)
        if not cut.enabled:
            continue
        if cut.target not in available:
            raise DraftError(cut.name, "Choose an available input piece from an earlier cut.")
        available.remove(cut.target)
        available.update(cut_outputs(cut))
        operations.append(cut)
    if not operations:
        raise MeshError("Enable at least one cut in the draft.")
    return operations


def current_results(scene: bpy.types.Scene, plan: TNTMESH_PG_draft_plan) -> list[bpy.types.Object]:
    return [obj for obj in scene.objects if obj.get(DRAFT_ID) == plan.uid]


def rebuild(
    context: bpy.types.Context, plan: TNTMESH_PG_draft_plan
) -> list[bpy.types.Object]:
    if plan.schema != SCHEMA:
        raise MeshError("This draft uses an unsupported project schema.")
    source = plan.source
    if source is None or source.type != "MESH" or source.name not in context.view_layer.objects:
        raise MeshError("The draft source is missing from this view layer.")
    operations = order(plan)
    project = UUID(plan.uid)
    previous = current_results(context.scene, plan)
    names = {obj.get(PART_ID): obj.name for obj in previous if obj.get(ROLE) == "part"}
    created = []
    unit = millimeters_per_unit(context.scene)
    wm = context.window_manager
    wm.progress_begin(0, len(operations) + 1)
    try:
        with GeometryTransaction() as transaction:
            was_hidden = source.hide_get()
            try:
                if was_hidden:
                    source.hide_set(False)
                    context.view_layer.update()
                mesh, origin = evaluated_mm(context, source, transaction, unit)
            finally:
                if was_hidden:
                    source.hide_set(True)
            leaves = {SOURCE: mesh}
            for index, operation in enumerate(operations, 1):
                target = leaves.pop(operation.target)
                try:
                    pieces = split(context, transaction, target, operation.settings.config())
                except MeshError as error:
                    raise DraftError(operation.name, str(error)) from error
                transaction.remove_mesh(target)
                leaves.update(zip(cut_outputs(operation), pieces, strict=True))
                wm.progress_update(index)

            collection = owned_collection(context.scene, "part")
            for index, (key, mesh) in enumerate(leaves.items(), 1):
                mesh.transform(Matrix.Scale(1.0 / unit, 4))
                mesh.update()
                part_id = uuid5(project, key).hex
                name = names.get(part_id, f"{plan.name} · {index:02d}")
                obj = transaction.object(collection, name, mesh)
                obj.location = origin
                identify_part(obj, plan.uid, part_id)
                obj[DRAFT_ID] = plan.uid
                created.append((obj, name))
            for obj, _ in created:
                transaction.publish(obj)

        # The old generation stays available until every operation has succeeded.
        # Unlink only generated draft objects exclusively owned by this scene.
        for obj in previous:
            if (len(obj.users_scene) != 1 or len(obj.users_collection) != 1
                    or obj.users_collection[0] != collection):
                obj[ROLE] = "superseded"
                continue
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
        for obj, name in created:
            obj.name = name
        wm.progress_update(len(operations) + 1)
        return [obj for obj, _ in created]
    finally:
        wm.progress_end()
        context.view_layer.update()
