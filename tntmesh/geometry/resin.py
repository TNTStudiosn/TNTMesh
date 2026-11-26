# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass
from math import ceil, isfinite, sqrt

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import prism
from .diagnostics import RAY_DIRECTIONS, face_shells, nonadjacent_overlaps, ray_parity, shell_volume
from .mesh import BOOLEAN_VOLUME_NOISE, bounds, inspect, triangulate

MAX_ACTIVE_VOXELS = 32_000_000


@dataclass(frozen=True)
class Drain:
    center: Vector
    inward: Vector
    diameter_mm: float
    depth_mm: float


def checked_mesh(mesh: bpy.types.Mesh) -> None:
    inspect(mesh)
    if next(nonadjacent_overlaps(mesh), None) is not None:
        raise MeshError("Use a closed resin mesh without intersecting faces.")


def surface_trees(mesh: bpy.types.Mesh) -> tuple[BVHTree, list[BVHTree], list[BVHTree]]:
    mesh.calc_loop_triangles()
    triangles = [tuple(face.vertices) for face in mesh.loop_triangles]
    points = [vertex.co.copy() for vertex in mesh.vertices]
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bm.faces.index_update()
        groups = {}
        for index, faces in enumerate(face_shells(bm)):
            group = index, shell_volume(faces) < 0
            groups.update((face.index, group) for face in faces)
    finally:
        bm.free()
    shells: dict[tuple[int, bool], list[tuple[int, int, int]]] = {}
    for face, triangle in zip(mesh.loop_triangles, triangles, strict=True):
        shells.setdefault(groups[face.polygon_index], []).append(triangle)
    outer, inner = [], []
    for (_, enclosed), faces in shells.items():
        (inner if enclosed else outer).append(BVHTree.FromPolygons(points, faces, all_triangles=True))
    return BVHTree.FromPolygons(points, triangles, all_triangles=True), outer, inner


def offset_volume(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    inset_mm: float, voxel_mm: float,
) -> bpy.types.Mesh:
    band = ceil(abs(inset_mm) / voxel_mm) + 3
    estimated = sum(face.area for face in mesh.polygons) / voxel_mm**2 * band * 2
    if estimated > MAX_ACTIVE_VOXELS:
        raise MeshError("Increase the voxel size to reduce the resin grid's memory use.")
    group = bpy.data.node_groups.new(".TNTMesh resin grid", "GeometryNodeTree")
    try:
        group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
        incoming = group.nodes.new("NodeGroupInput")
        outgoing = group.nodes.new("NodeGroupOutput")
        grid = group.nodes.new("GeometryNodeMeshToSDFGrid")
        surface = group.nodes.new("GeometryNodeGridToMesh")
        grid.inputs["Voxel Size"].default_value = voxel_mm
        grid.inputs["Band Width"].default_value = band
        surface.inputs["Threshold"].default_value = -inset_mm
        group.links.new(incoming.outputs["Geometry"], grid.inputs["Mesh"])
        group.links.new(grid.outputs["SDF Grid"], surface.inputs["Grid"])
        group.links.new(surface.outputs["Mesh"], outgoing.inputs["Geometry"])
        obj = transaction.object(context.scene.collection, ".TNTMesh resin surface", mesh)
        try:
            modifier = obj.modifiers.new("TNTMesh Resin", "NODES")
            modifier.node_group = group
            depsgraph = context.evaluated_depsgraph_get()
            result = transaction.own_mesh(bpy.data.meshes.new_from_object(
                obj.evaluated_get(depsgraph), depsgraph=depsgraph,
            ))
        finally:
            transaction.remove_object(obj)
    finally:
        bpy.data.node_groups.remove(group)
    return result


def hollow(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    wall_mm: float, minimum_mm: float, voxel_mm: float,
    protection: bpy.types.Mesh | None = None, reinforcement_mm: float = 0,
) -> tuple[bpy.types.Mesh, float]:
    values = wall_mm, minimum_mm, voxel_mm, reinforcement_mm
    if not all(map(isfinite, values)) or min(values[:3]) <= 0 or reinforcement_mm < 0:
        raise MeshError("Check the wall thickness and resin voxel size.")
    checked_mesh(mesh)
    original = inspect(mesh)
    # Keep the requested minimum outside the half-diagonal sampling error of the voxel grid.
    inset = max(wall_mm, minimum_mm + voxel_mm * sqrt(3) / 2)
    lower, upper = bounds(vertex.co for vertex in mesh.vertices)
    if min(upper - lower) <= 2 * inset:
        raise MeshError("No room for a cavity at this wall thickness and voxel size.")
    cavity = offset_volume(context, transaction, mesh, inset, voxel_mm)
    if not cavity.polygons:
        raise MeshError("No room for a cavity at this wall thickness and voxel size.")
    checked_mesh(cavity)
    engine = ExactBoolean(context, transaction)
    if protection is not None:
        checked_mesh(protection)
        if reinforcement_mm:
            protection = offset_volume(context, transaction, protection, -reinforcement_mm, voxel_mm)
            checked_mesh(protection)
        cavity = engine.run(cavity, protection, "DIFFERENCE")
        if not cavity.polygons:
            raise MeshError("The protected region leaves no room for a cavity.")
        checked_mesh(cavity)
    removed = inspect(cavity)
    body = engine.run(mesh, cavity, "DIFFERENCE")
    checked_mesh(body)
    final = inspect(body)
    tolerance = max(BOOLEAN_VOLUME_NOISE, original.volume_mm3 * 2e-6)
    if (final.shells != original.shells + removed.shells
            or abs(original.volume_mm3 - final.volume_mm3 - removed.volume_mm3) > tolerance):
        raise MeshError("The cavity intersects the surface. Adjust the wall or voxel size.")
    if protection is not None and len(surface_trees(body)[1]) != len(surface_trees(mesh)[1]):
        raise MeshError("The protected region must connect to a wall of the model.")
    return body, removed.volume_mm3


def drain_frame(inward: Vector) -> Matrix:
    x = inward.orthogonal().normalized()
    return Matrix((x, inward.cross(x), inward)).transposed()


def drain_tool(
    transaction: GeometryTransaction, drain: Drain, surface: BVHTree, bodies: list[BVHTree],
    cavities: list[BVHTree], custom: bpy.types.Mesh | None,
) -> bpy.types.Mesh:
    inward = drain.inward.normalized()
    frame = drain_frame(inward)
    eps = max(1e-5, drain.diameter_mm * 1e-5)
    start = drain.center - inward * max(.1, drain.diameter_mm / 2)
    entry, normal, _, _ = surface.ray_cast(start, inward, (drain.center - start).length + eps)
    if (entry is None or normal.dot(inward) >= 0 or (entry - drain.center).length > eps
            or any(ray_parity(tree, start, ray, eps) is not False for tree in bodies for ray in RAY_DIRECTIONS)):
        raise MeshError("Place the drain on the outside surface with its direction pointing inward.")
    if custom is None:
        cutter = prism(transaction, frame, (frame.transposed() @ drain.center).xy,
                       (frame.transposed() @ start).z, (frame.transposed() @ drain.center).z + drain.depth_mm,
                       drain.diameter_mm / 2, 32)
        reaches_cavity = any(tree.ray_cast(entry, inward, drain.depth_mm)[0] is not None for tree in cavities)
    else:
        checked_mesh(custom)
        if inspect(custom).shells != 1:
            raise MeshError("Use a single closed mesh for the custom drain.")
        custom_tree, _, _ = surface_trees(custom)
        outside = entry - inward * (eps * 4)
        if any(ray_parity(custom_tree, outside, ray, eps) is not True for ray in RAY_DIRECTIONS):
            raise MeshError("The custom drain must enclose the entry point and extend outside the surface.")
        cutter = custom
        reaches_cavity = any(tree.overlap(custom_tree) for tree in cavities)
    if not reaches_cavity:
        raise MeshError("The drain did not open a cavity to the outside. Check its placement and depth.")
    return cutter


def cut_drain(engine: ExactBoolean, mesh: bpy.types.Mesh, cutter: bpy.types.Mesh) -> bpy.types.Mesh:
    body = engine.run(mesh, cutter, "DIFFERENCE")
    bm = bmesh.new()
    try:
        bm.from_mesh(body)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-4)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=1e-4)
        bm.to_mesh(body)
    finally:
        bm.free()
    body.update()
    triangulate(body)
    checked_mesh(body)
    return body


def drill(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh, drain: Drain,
    custom: bpy.types.Mesh | None = None, *, reference: bpy.types.Mesh | None = None,
) -> bpy.types.Mesh:
    if (not all(map(isfinite, (*drain.center, *drain.inward, drain.diameter_mm, drain.depth_mm)))
            or not drain.inward.length or min(drain.depth_mm, drain.diameter_mm) <= 0):
        raise MeshError("Check the drain diameter, direction and depth.")
    original = reference if reference is not None else mesh
    checked_mesh(original)
    surface, bodies, cavities = surface_trees(original)
    if not cavities:
        raise MeshError("No closed cavity is available to drain.")
    cutter = drain_tool(transaction, drain, surface, bodies, cavities, custom)
    engine = ExactBoolean(context, transaction)
    body = cut_drain(engine, original, cutter)
    _, final_bodies, final_cavities = surface_trees(body)
    if len(final_bodies) != len(bodies) or len(final_cavities) >= len(cavities):
        raise MeshError("The drain did not open a cavity to the outside. Check its placement and depth.")
    if reference is None:
        return body
    # Recheck the new channel against the original cavity without consuming earlier drains.
    checked_mesh(mesh)
    removed = inspect(original).volume_mm3 - inspect(body).volume_mm3
    next_body = cut_drain(engine, mesh, cutter)
    before, after = inspect(mesh), inspect(next_body)
    # Tessellating the two cavity seams can differ by a fraction of the cut volume.
    if (after.shells > before.shells or abs(before.volume_mm3 - after.volume_mm3 - removed)
            > max(BOOLEAN_VOLUME_NOISE, removed * .001)):
        raise MeshError("The new drain overlaps an existing opening or modified wall. Move it to intact material.")
    return next_body


def plug(
    transaction: GeometryTransaction, body: bpy.types.Mesh, original: bpy.types.Mesh, drain: Drain,
    clearance: float,
) -> bpy.types.Mesh:
    radius = drain.diameter_mm / 2 - clearance
    if not isfinite(clearance) or clearance < 0 or radius <= 0:
        raise MeshError("Plug clearance must be smaller than the drain radius.")
    _, _, cavities = surface_trees(original)
    inward = drain.inward.normalized()
    depth = min(distance for cavity in cavities
                for point, _, _, distance in (cavity.ray_cast(drain.center, inward, drain.depth_mm),)
                if point is not None)
    lower, upper = bounds(vertex.co for vertex in body.vertices)
    center = Vector((upper.x + radius + 2, (lower.y + upper.y) / 2))
    return prism(transaction, Matrix.Identity(3), center, lower.z, lower.z + depth, radius, 32)


def suggest(
    mesh: bpy.types.Mesh, inward: Vector, diameter_mm: float, depth_mm: float,
    *, drilled: bpy.types.Mesh | None = None,
) -> Drain | None:
    checked_mesh(mesh)
    surface, _, cavities = surface_trees(mesh)
    if not cavities or not inward.length:
        return None
    current_surface = surface_trees(drilled)[0] if drilled is not None else None
    inward = inward.normalized()
    frame = drain_frame(inward)
    inverse = frame.transposed()
    lower, upper = bounds(inverse @ vertex.co for vertex in mesh.vertices)
    margin = diameter_mm / 2 + .1
    if min((upper - lower).xy) <= 2 * margin:
        return None
    options = []
    # Keep the ray off the projected boundary and test the perimeter before offering a placement.
    steps = (0, .25, -.25, .375, -.375)
    samples = (Vector(), *(frame @ Vector((x * margin, y * margin, 0))
                           for x, y in ((1, 0), (-1, 0), (0, 1), (0, -1))))
    midpoint = (lower + upper) / 2
    for x in steps:
        for y in steps:
            start = frame @ Vector((midpoint.x + x * (upper.x - lower.x),
                                    midpoint.y + y * (upper.y - lower.y), lower.z - margin))
            point, normal, _, _ = surface.ray_cast(start, inward)
            if point is None or normal.dot(inward) > -.5:
                continue
            if current_surface is not None:
                distances = [tree.ray_cast(start + offset, inward)[3]
                             for offset in samples for tree in (surface, current_surface)]
                if any(a is None or b is None or abs(a - b) > 1e-4
                       for a, b in zip(distances[::2], distances[1::2], strict=True)):
                    continue
            if not all(any(cavity.ray_cast(point + offset, inward, depth_mm)[0] is not None
                           for cavity in cavities) for offset in samples):
                continue
            options.append((point.dot(inward), x*x + y*y, point))
    return Drain(min(options, key=lambda item: item[:2])[2], inward, diameter_mm, depth_mm) if options else None
