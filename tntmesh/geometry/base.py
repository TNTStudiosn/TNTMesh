# SPDX-License-Identifier: GPL-3.0-or-later
from collections import defaultdict
from dataclasses import dataclass, replace
from math import isfinite

import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction, MeshError
from .boolean import ExactBoolean, half_box
from .connector import Connector, add_connector
from .connector_profiles import DIAMETER_SHAPES
from .mesh import bounds, inspect, primitive
from .polygon import closed_outline, signed_turn
from .region import edge_map
from .repair import repair_copy

EPS = 0.001
MIN_UPWARD = 0.5


@dataclass(frozen=True)
class ContactOverride:
    center: tuple[float, float, float]
    shift: float
    connector: bool
    diameter: float


@dataclass(frozen=True)
class BaseCut:
    band: float = 0.0
    area: float = 0.5
    margin: float = 0.05
    adjustment: float = 0.0
    connector: Connector | None = None
    overrides: tuple[ContactOverride, ...] = ()

    def for_contact(self, contact: "Contact") -> "BaseCut":
        for override in self.overrides:
            if (Vector(override.center) - contact.center).length <= .025:
                connector = self.connector if override.connector else None
                if connector is not None and override.diameter:
                    size = "diameter" if connector.shape in DIAMETER_SHAPES else "width"
                    connector = replace(connector, **{size: override.diameter})
                return replace(self, adjustment=self.adjustment + override.shift, connector=connector)
        return self


@dataclass(frozen=True)
class Contact:
    points: tuple[Vector, ...]
    center: Vector
    support_normal: Vector
    area: float


@dataclass(frozen=True)
class BaseAnalysis:
    contacts: tuple[Contact, ...]
    ceiling: float
    extent: float


def rising_reach(
    start: int, neighbors: dict[int, list[int]], upward: set[int],
    high: list[float], ceiling: float, reach: dict[int, bool],
) -> bool:
    if start in reach:
        return reach[start]
    visited = {start}
    pending = [start]
    while pending:
        face = pending.pop()
        for neighbor in neighbors[face]:
            if neighbor not in upward and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    result = any(high[index] > ceiling + EPS for index in visited)
    reach.update(dict.fromkeys(visited, result))
    return result


def ordered_rings(edges: dict[tuple[int, int], Vector]) -> list[list[int]]:
    adjacency = defaultdict(set)
    for start, end in edges:
        adjacency[start].add(end)
        adjacency[end].add(start)
    todo = set(adjacency)
    rings = []
    while todo:
        start = min(todo)
        component = {start}
        stack = [start]
        while stack:
            for node in adjacency[stack.pop()] - component:
                component.add(node)
                stack.append(node)
        todo.difference_update(component)
        if any(len(adjacency[node]) != 2 for node in component):
            continue
        ring = [start]
        previous, current = start, min(adjacency[start])
        while current != start:
            ring.append(current)
            previous, current = current, next(iter(adjacency[current] - {previous}))
        rings.append(ring)
    return rings


def analyze_base(mesh: bpy.types.Mesh, config: BaseCut) -> BaseAnalysis:
    if not all(isfinite(number) for number in (config.band, config.area, config.margin, config.adjustment)) or (
        min(config.band, config.area, config.margin) < 0
    ):
        raise MeshError("Check the base scan height, minimum contact area and margin.")
    lower, upper = bounds(vertex.co for vertex in mesh.vertices)
    span = upper.z - lower.z
    ceiling = lower.z + (config.band or span * 0.22)
    if ceiling >= upper.z - EPS:
        raise MeshError("Set the base search height below the top of the model.")
    uses = edge_map(mesh)
    high = [max(mesh.vertices[index].co.z for index in face.vertices) for face in mesh.polygons]
    upward = {face.index for face in mesh.polygons if face.normal.z >= MIN_UPWARD}
    neighbors = defaultdict(list)
    for adjacent in uses.values():
        if len(adjacent) == 2:
            first, second = adjacent[0][0], adjacent[1][0]
            neighbors[first].append(second)
            neighbors[second].append(first)

    edges = {}
    reach: dict[int, bool] = {}
    for (a, b), adjacent in uses.items():
        if len(adjacent) != 2:
            continue
        support, wall = adjacent[0][0], adjacent[1][0]
        if wall in upward:
            support, wall = wall, support
        if support not in upward or wall in upward:
            continue
        vertex_a, vertex_b = mesh.vertices[a].co, mesh.vertices[b].co
        if max(vertex_a.z, vertex_b.z) >= ceiling - EPS:
            continue
        normal = mesh.polygons[support].normal
        if max(normal.dot(mesh.vertices[index].co - vertex_a)
               for index in mesh.polygons[wall].vertices) <= EPS:
            continue
        if rising_reach(wall, neighbors, upward, high, ceiling, reach):
            edges[a, b] = normal.copy()

    contacts = []
    for ring in ordered_rings(edges):
        points = [mesh.vertices[index].co.copy() for index in ring]
        xy = [tuple(point.xy) for point in points]
        try:
            plane = closed_outline(xy)
        except MeshError:
            continue
        if xy != plane:
            points.reverse()
        area = abs(sum(signed_turn(plane[0], plane[i], plane[i + 1])
                       for i in range(1, len(plane) - 1))) / 2
        if area < config.area:
            continue
        center = sum(points, Vector((0, 0, 0))) / len(points)
        normal = Vector((0, 0, 0))
        for a, b in zip(ring, ring[1:] + ring[:1], strict=True):
            normal += edges[min(a, b), max(a, b)]
        contacts.append(Contact(tuple(points), center, normal.normalized(), area))
    contacts.sort(key=lambda item: (item.center.x, item.center.y, item.center.z))
    extent = max(lower.length, upper.length) * 2.0
    return BaseAnalysis(tuple(contacts), ceiling, extent)


def contact_outline(contact: Contact, config: BaseCut) -> list[Vector]:
    points = []
    for source in contact.points:
        tangent = (source.xy - contact.center.xy).normalized() * config.margin
        slope = -(contact.support_normal.x * tangent.x + contact.support_normal.y * tangent.y)
        slope /= contact.support_normal.z
        points.append(Vector((source.x + tangent.x, source.y + tangent.y,
                              source.z + slope + config.adjustment)))
    closed_outline([tuple(point.xy) for point in points])
    return points


def core_cutter(
    transaction: GeometryTransaction, contact: Contact, config: BaseCut, ceiling: float,
) -> bpy.types.Mesh:
    points = contact_outline(contact, config)
    if max(point.z for point in points) >= ceiling - EPS:
        raise MeshError("A contact is above the base search height after adjustment.")
    count = len(points)
    top = [Vector((point.x, point.y, ceiling + 0.15)) for point in points]
    faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
    faces.extend((i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count))
    return primitive(transaction, ".TNTMesh base contact cutter", points + top, faces)


def split_base(
    context: bpy.types.Context, transaction: GeometryTransaction, mesh: bpy.types.Mesh,
    config: BaseCut,
) -> tuple[bpy.types.Mesh, ...]:
    before = inspect(mesh).volume_mm3
    analysis = analyze_base(mesh, config)
    if not analysis.contacts:
        raise MeshError("No closed base contacts were found. Adjust the search height.")
    engine = ExactBoolean(context, transaction)
    cutter = half_box(transaction, Matrix.Identity(3), analysis.extent, analysis.ceiling, 1)
    for contact in analysis.contacts:
        local = core_cutter(transaction, contact, config.for_contact(contact), analysis.ceiling)
        inspect(local)
        combined = engine.run(cutter, local, "UNION")
        transaction.remove_mesh(cutter)
        transaction.remove_mesh(local)
        cutter = combined
    inspect(cutter)
    base = engine.run(mesh, cutter, "DIFFERENCE")
    figure = engine.run(mesh, cutter, "INTERSECT")
    volumes = []
    for piece in (base, figure):
        try:
            result = inspect(piece)
        except MeshError:
            # Coincident base faces can produce vertices separated by float rounding.
            # Weld only output geometry, at one hundredth of a micrometer.
            result = repair_copy(piece, weld_mm=.00001, max_hole_edges=0)
        volumes.append(result.volume_mm3)
    after = sum(volumes)
    if abs(after - before) > before * .001:
        raise MeshError("The split did not preserve the expected volume.")

    pins = []
    if config.connector is not None:
        for contact in analysis.contacts:
            local_config = config.for_contact(contact)
            if local_config.connector is None:
                continue
            frame = contact.support_normal.to_track_quat("Z", "Y").to_matrix()
            local = frame.transposed() @ (contact.center + Vector((0, 0, local_config.adjustment)))
            planarity = max(abs(contact.support_normal.dot(point - contact.center))
                            for point in contact.points)
            if planarity > .02:
                raise MeshError("A contact is too irregular for a straight pin. Disable connectors.")
            result = add_connector(engine, base, figure, frame, local.z, 0, local_config.connector,
                                   EPS, requested=(Vector((local.x, local.y, 0)),),
                                   requested_error="A base contact does not have room for a connector.")
            base, figure = result.meshes[:2]
            pins.extend(result.meshes[2:])
    return base, figure, *pins
