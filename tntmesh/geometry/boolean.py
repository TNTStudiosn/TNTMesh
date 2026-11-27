# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from mathutils import Matrix, Vector

from ..model import GeometryTransaction
from .mesh import BOOLEAN_VOLUME_NOISE, absolute_volume, primitive

MESH_FLOAT_EPSILON = 2 ** -23


class ExactBoolean:
    def __init__(self, context: bpy.types.Context, transaction: GeometryTransaction) -> None:
        self.context = context
        self.transaction = transaction

    def run(
        self, mesh: bpy.types.Mesh, cutter: bpy.types.Mesh, operation: str
    ) -> bpy.types.Mesh:
        collection = self.context.scene.collection
        target = self.transaction.object(collection, ".TNTMesh target", mesh)
        try:
            tool = self.transaction.object(collection, ".TNTMesh cutter", cutter)
            try:
                modifier = target.modifiers.new("TNTMesh Exact", "BOOLEAN")
                modifier.solver = "EXACT"
                modifier.operation = operation
                modifier.object = tool
                depsgraph = self.context.evaluated_depsgraph_get()
                return self.transaction.own_mesh(
                    bpy.data.meshes.new_from_object(
                        target.evaluated_get(depsgraph),
                        preserve_all_data_layers=True,
                        depsgraph=depsgraph,
                    )
                )
            finally:
                # Input meshes can also be used for other Boolean operations.
                self.transaction.remove_object(tool)
        finally:
            self.transaction.remove_object(target)


def measure_intersection(engine: ExactBoolean, first: bpy.types.Mesh, second: bpy.types.Mesh) -> float:
    intersection = engine.run(first, second, "INTERSECT")
    try:
        volume = absolute_volume(intersection)
        if volume <= BOOLEAN_VOLUME_NOISE:
            return 0.0
        scale = max(abs(coordinate) for vertex in intersection.vertices for coordinate in vertex.co)
        # Close contact can leave one coordinate ULP of volume in the Boolean output.
        roundoff = sum(face.area for face in intersection.polygons) * scale * MESH_FLOAT_EPSILON
        return volume if volume > roundoff else 0.0
    finally:
        engine.transaction.remove_mesh(intersection)


def half_box(
    transaction: GeometryTransaction, frame: Matrix, extent: float, boundary: float, side: int
) -> bpy.types.Mesh:
    near, far = sorted((boundary, side * extent))
    vertices = [
        frame @ Vector(point)
        for point in (
            (-extent, -extent, near), (extent, -extent, near),
            (extent, extent, near), (-extent, extent, near),
            (-extent, -extent, far), (extent, -extent, far),
            (extent, extent, far), (-extent, extent, far),
        )
    ]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7)]
    return primitive(transaction, ".TNTMesh half space", vertices, faces)
