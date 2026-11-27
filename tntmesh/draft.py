# SPDX-License-Identifier: GPL-3.0-or-later
from uuid import UUID, uuid5

import bpy
from bpy.props import BoolProperty, CollectionProperty, IntProperty, PointerProperty, StringProperty
from mathutils import Vector

from . import assembly_history
from .geometry.mesh import evaluated_mm
from .geometry.planar import PlanarCut, axis_frame
from .geometry.volume import apply_cut, structural_parts
from .localization import tr
from .model import (
    ASSEMBLY_DIRECTION,
    DRAFT_ID,
    PART_ID,
    PART_KIND,
    ROLE,
    GeometryTransaction,
    MeshError,
    identify_part,
    millimeters_per_unit,
    owned_collection,
    restore_scene_units,
)
from .settings import TNTMESH_PG_settings

SOURCE = "source"
SCHEMA = 1


class TNTMESH_PG_draft_cut(bpy.types.PropertyGroup):
    uid: StringProperty()
    target: StringProperty(default=SOURCE)
    enabled: BoolProperty(name="Run this cut", default=True)
    settings: PointerProperty(type=TNTMESH_PG_settings)


class TNTMESH_PG_draft_output(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object)


class TNTMESH_PG_draft_plan(bpy.types.PropertyGroup):
    uid: StringProperty()
    schema: IntProperty(default=SCHEMA)
    source: PointerProperty(type=bpy.types.Object)
    cuts: CollectionProperty(type=TNTMESH_PG_draft_cut)
    results: CollectionProperty(type=TNTMESH_PG_draft_output)
    cut_index: IntProperty(min=0)


CLASSES = (TNTMESH_PG_draft_cut, TNTMESH_PG_draft_output, TNTMESH_PG_draft_plan)


def active_plan(scene: bpy.types.Scene) -> TNTMESH_PG_draft_plan | None:
    return (
        scene.tntmesh_drafts[scene.tntmesh_draft_index]
        if scene.tntmesh_draft_index < len(scene.tntmesh_drafts)
        else None
    )


def active_cut(plan: TNTMESH_PG_draft_plan) -> TNTMESH_PG_draft_cut | None:
    return plan.cuts[plan.cut_index] if plan.cut_index < len(plan.cuts) else None


def cut_outputs(cut: TNTMESH_PG_draft_cut) -> tuple[str, ...]:
    quantity = structural_parts(cut.settings.cut_kind)
    return tuple(f"{cut.uid}:{number}" for number in range(1, quantity + 1))


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


def current_results(plan: TNTMESH_PG_draft_plan) -> list[bpy.types.Object]:
    return list(dict.fromkeys(
        result.obj for result in plan.results
        if result.obj is not None and result.obj.get(DRAFT_ID) == plan.uid
    ))


def track_followups(
    scene: bpy.types.Scene, source: bpy.types.Object, parts: list[bpy.types.Object]
) -> None:
    draft_id = source.get(DRAFT_ID)
    if draft_id is None:
        return
    for plan in scene.tntmesh_drafts:
        if plan.uid == draft_id and source in current_results(plan):
            for part in parts:
                part[DRAFT_ID] = draft_id
                plan.results.add().obj = part
            return


def target_mesh(
    context: bpy.types.Context, transaction: GeometryTransaction, plan: TNTMESH_PG_draft_plan,
    index: int, unit: float,
) -> bpy.types.Mesh:
    source = plan.source
    if source is None or source.type != "MESH" or source.name not in context.view_layer.objects:
        raise MeshError("The draft source is missing from this view layer.")
    target = plan.cuts[index].target
    if target not in free_targets(plan, index):
        raise MeshError("Choose an available input piece from an earlier cut.")
    chain = []
    for previous in reversed(list(plan.cuts)[:index]):
        if target == SOURCE:
            break
        keys = cut_outputs(previous)
        if previous.enabled and target in keys:
            chain.append((previous, keys.index(target)))
            target = previous.target
    if target != SOURCE:
        raise MeshError("Choose an available input piece from an earlier cut.")
    hidden = source.hide_get()
    try:
        if hidden:
            source.hide_set(False)
            context.view_layer.update()
        mesh, origin = evaluated_mm(context, source, transaction, unit)
        for previous, branch in reversed(chain):
            config = previous.settings.config(source)
            try:
                pieces = apply_cut(context, transaction, mesh, config, origin, unit, source)
            except MeshError as error:
                raise DraftError(previous.name, str(error)) from error
            transaction.remove_mesh(mesh)
            mesh = pieces[branch]
            for piece in pieces:
                if piece != mesh:
                    transaction.remove_mesh(piece)
        return mesh
    finally:
        if hidden:
            source.hide_set(True)


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
    previous = current_results(plan)
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
            directions = {SOURCE: Vector((0, 0, 0))}
            paths = {SOURCE: ()}
            pins = {}
            for index, operation in enumerate(operations, 1):
                target = leaves.pop(operation.target)
                inherited = directions.pop(operation.target)
                try:
                    config = operation.settings.config(source)
                    pieces = apply_cut(
                        context, transaction, target, config, origin, unit, source,
                    )
                except MeshError as error:
                    raise DraftError(operation.name, str(error)) from error
                transaction.remove_mesh(target)
                keys = cut_outputs(operation)
                leaves.update(zip(keys, pieces[:len(keys)], strict=True))
                inherited_path = paths.pop(operation.target)
                stock, connector = assembly_history.connection_details(config)
                for branch, key in enumerate(keys, 1):
                    paths[key] = inherited_path + (
                        assembly_history.Branch(operation.uid, branch, len(keys), stock, connector),
                    )
                if isinstance(config, PlanarCut):
                    normal = axis_frame(config.axis, config.rotation).col[2]
                    directions[keys[0]] = inherited - normal
                    directions[keys[1]] = inherited + normal
                else:
                    for key in keys:
                        directions[key] = inherited.copy()
                for number, pin in enumerate(pieces[len(keys):], 1):
                    key = f"{operation.uid}:pin:{number}"
                    pins[key] = pin
                    paths[key] = inherited_path + (assembly_history.Branch(operation.uid, 0, len(keys),
                                                                         connector=connector),)
                wm.progress_update(index)

            collection = owned_collection(context.scene, "part")
            for index, (key, mesh) in enumerate((leaves | pins).items(), 1):
                restore_scene_units(mesh, unit)
                part_id = uuid5(project, key).hex
                label = tr("Pin {number}").format(number=index - len(leaves)) if key in pins else f"{index:02d}"
                name = names.get(part_id, f"{plan.name} · {label}")
                obj = transaction.object(collection, name, mesh)
                obj.location = origin
                identify_part(obj, plan.uid, part_id)
                obj[DRAFT_ID] = plan.uid
                obj[PART_KIND] = "pin" if key in pins else "body"
                assembly_history.set_path(obj, paths[key])
                if key in directions and directions[key].length_squared:
                    obj[ASSEMBLY_DIRECTION] = tuple(directions[key])
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
        plan.results.clear()
        for obj, name in created:
            obj.name = name
            plan.results.add().obj = obj
        wm.progress_update(len(operations) + 1)
        return [obj for obj, _ in created]
    finally:
        wm.progress_end()
        context.view_layer.update()
