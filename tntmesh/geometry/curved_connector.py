# SPDX-License-Identifier: GPL-3.0-or-later
from math import hypot

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean
from .connector import Connector, profile_loft, profile_prism
from .connector_profiles import translated_overlap
from .mesh import BOOLEAN_VOLUME_NOISE, VOLUME_EPSILON, absolute_volume, inspect
from .polygon import Point2
from .region import RegionTool

SEARCH_LIMIT = 16


def seam_candidates(tool: RegionTool) -> tuple[Vector, list[Vector]]:
    mesh = tool.mesh
    faces = [mesh.polygons[index] for index in tool.inner_faces]
    normal = -sum((face.normal * face.area for face in faces), Vector()).normalized()
    if normal.length_squared == 0:
        return normal, []
    faces = [face for face in faces if -face.normal.dot(normal) >= .8]
    if not faces:
        return normal, []
    center = sum((face.center * face.area for face in faces), Vector()) / sum(face.area for face in faces)
    faces.sort(key=lambda face: (face.center - center).length_squared)
    return normal, [face.center.copy() for face in faces]


def seam_range(
    tree: BVHTree, frame: Matrix, center: Vector, depth: float, travel: float, guard: tuple[Point2, ...],
) -> tuple[float, float] | None:
    normal = frame.col[2]
    hits = []
    for x, y in ((0., 0.), *guard):
        origin = frame @ Vector((center.x + x, center.y + y, depth - travel))
        point, facing, _, _ = tree.ray_cast(origin, normal, 2 * travel)
        if point is None or -facing.dot(normal) < .75:
            return None
        hits.append(normal.dot(point))
    return min(hits), max(hits)


def try_connector(
    engine: ExactBoolean, minus: bpy.types.Mesh, plus: bpy.types.Mesh, config: Connector,
    frame: Matrix, center: Vector, limits: tuple[float, float], guard: tuple[Point2, ...],
) -> tuple[bpy.types.Mesh, ...] | None:
    old_minus, old_plus = inspect(minus), inspect(plus)
    low, high = limits
    anchor = config.insertion if config.loose else config.anchor
    start = low - anchor
    end = high + config.insertion
    socket_start = start - (config.axial if config.loose else 0)
    socket_end = end + config.axial
    with GeometryTransaction() as temporary:
        boolean = ExactBoolean(engine.context, temporary)
        corridor = profile_prism(temporary, frame, center, socket_start - config.wall, socket_end + config.wall, guard)
        gap = boolean.run(boolean.run(corridor, minus, "DIFFERENCE"), plus, "DIFFERENCE")
        if absolute_volume(gap) > BOOLEAN_VOLUME_NOISE:
            return None
        trim = min(anchor, config.insertion, config.wall) * .5
        for body, bottom, top in (
            (minus, socket_start - config.wall, low - trim),
            (plus, high + trim, socket_end + config.wall),
        ):
            wall = profile_prism(temporary, frame, center, bottom, top, guard)
            if boolean.run(wall, body, "DIFFERENCE").polygons:
                return None

        pin = profile_loft(temporary, frame, center, config.sections(start, end, low, high))
        socket = profile_loft(temporary, frame, center,
                              config.sections(socket_start, socket_end, low, high, config.lateral))
        pin_volume = inspect(pin).volume_mm3
        expected_plus = absolute_volume(boolean.run(plus, socket, "INTERSECT"))
        if config.loose:
            expected_minus = absolute_volume(boolean.run(minus, socket, "INTERSECT"))
            new_minus = boolean.run(minus, socket, "DIFFERENCE")
        else:
            expected_minus = pin_volume - absolute_volume(boolean.run(minus, pin, "INTERSECT"))
            new_minus = boolean.run(minus, pin, "UNION")
        new_plus = boolean.run(plus, socket, "DIFFERENCE")
        try:
            valid_minus, valid_plus = inspect(new_minus), inspect(new_plus)
        except MeshError:
            return None
        changed_minus = (old_minus.volume_mm3 - valid_minus.volume_mm3 if config.loose
                         else valid_minus.volume_mm3 - old_minus.volume_mm3)
        changes = ((changed_minus, expected_minus), (old_plus.volume_mm3 - valid_plus.volume_mm3, expected_plus))
        if (valid_minus.shells != old_minus.shells or valid_plus.shells != old_plus.shells
                or any(expected <= VOLUME_EPSILON or abs(actual - expected) > expected * .01
                       for actual, expected in changes)):
            return None
        # Verify the local pin fit. Broad regions of mating surfaces can leave
        # coplanar artifacts if the complete bodies are intersected again.
        if any(absolute_volume(boolean.run(pin, body, "INTERSECT")) > BOOLEAN_VOLUME_NOISE
               for body in ((new_minus, new_plus) if config.loose else (new_plus,))):
            return None
        outputs = (new_minus, new_plus, pin) if config.loose else (new_minus, new_plus)
        return tuple(engine.transaction.own_mesh(mesh.copy()) for mesh in outputs)


def connect_curved(
    engine: ExactBoolean, remainder: bpy.types.Mesh, insert: bpy.types.Mesh, tool: RegionTool,
    config: Connector, guard: tuple[Point2, ...],
) -> tuple[bpy.types.Mesh, ...] | None:
    normal, candidates = seam_candidates(tool)
    if not candidates:
        return None
    mesh = tool.mesh
    mesh.calc_loop_triangles()
    tree = BVHTree.FromPolygons(
        [vertex.co for vertex in mesh.vertices],
        [tuple(face.vertices) for face in mesh.loop_triangles if face.polygon_index in tool.inner_faces],
        all_triangles=True,
    )
    envelope = max(hypot(*point) for point in guard)
    frame = normal.to_track_quat("Z", "Y").to_matrix()
    inverse = frame.transposed()
    accepted = []
    pins = []
    selected = 0
    minus, plus = remainder, insert
    for location in candidates:
        center = inverse @ location
        depth = center.z
        center.z = 0
        if any((center - other).length < 2 * envelope and (
            not config.uses_footprint or translated_overlap(guard, center.x - other.x, center.y - other.y, 1e-5)
        ) for other in accepted):
            continue
        limits = seam_range(tree, frame, center, depth, max(config.insertion, envelope), guard)
        if limits is None:
            continue
        selected += 1
        result = try_connector(engine, minus, plus, config, frame, center, limits, guard)
        if result is not None:
            if accepted:
                engine.transaction.remove_mesh(minus)
                engine.transaction.remove_mesh(plus)
            minus, plus, *new_pins = result
            accepted.append(center)
            pins.extend(new_pins)
            if len(accepted) == config.count:
                engine.transaction.remove_mesh(remainder)
                engine.transaction.remove_mesh(insert)
                return minus, plus, *pins
        if selected >= SEARCH_LIMIT:
            break
    if accepted:
        for mesh in (minus, plus, *pins):
            engine.transaction.remove_mesh(mesh)
    return None
