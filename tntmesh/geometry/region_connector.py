# SPDX-License-Identifier: GPL-3.0-or-later
from dataclasses import dataclass, field
from math import cos, sin, tau

import bpy
from mathutils import Vector

from ..model import MeshError
from .boolean import ExactBoolean
from .connector import Connector, ConnectorPlacementError, add_connector
from .region import RegionTool

PLANE_TOLERANCE_MM = .0001
SEARCH_LIMIT = 12


@dataclass
class Surface:
    normal: Vector
    position: float
    area: float = 0
    weighted_center: Vector = field(default_factory=Vector)


def inner_surfaces(tool: RegionTool, minimum_area: float) -> list[Surface]:
    mesh = tool.mesh
    mesh.calc_loop_triangles()
    groups: dict[tuple[tuple[float, ...], float], Surface] = {}
    for triangle in mesh.loop_triangles:
        if triangle.polygon_index not in tool.inner_faces or triangle.area <= 0:
            continue
        normal = -triangle.normal
        center = sum((mesh.vertices[index].co for index in triangle.vertices), Vector()) / 3
        distance = normal.dot(center)
        key = (tuple(round(axis, 5) for axis in normal), round(distance, 4))
        if key not in groups:
            groups[key] = Surface(normal, distance)
        surface = groups[key]
        surface.area += triangle.area
        surface.weighted_center += center * triangle.area
    surfaces = sorted((surface for surface in groups.values() if surface.area >= minimum_area),
                      key=lambda surface: -surface.area)
    return surfaces[:SEARCH_LIMIT]


def connect_region(
    engine: ExactBoolean, remainder: bpy.types.Mesh, insert: bpy.types.Mesh, tool: RegionTool,
    connector: Connector,
) -> tuple[bpy.types.Mesh, ...]:
    connector.validate()
    envelope = connector.socket_radius + connector.wall / cos(tau / (2 * connector.sides))
    footprint = connector.sides * envelope**2 * sin(tau / connector.sides) / 2
    for surface in inner_surfaces(tool, footprint * connector.count):
        frame = surface.normal.to_track_quat("Z", "Y").to_matrix()
        center = frame.transposed() @ (surface.weighted_center / surface.area)
        try:
            return add_connector(
                engine, remainder, insert, frame, surface.position, 0, connector,
                PLANE_TOLERANCE_MM, preferred=(Vector((center.x, center.y, 0)),),
            ).meshes
        except ConnectorPlacementError:
            continue
    raise MeshError("No planar region seam can fit the requested connectors.")
