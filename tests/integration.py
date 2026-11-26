# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

import addon_utils
import bpy
from mathutils import Vector


def load_addon():
    package = os.environ.get("TNTMESH_TEST_PACKAGE", "tntmesh")
    if package == "tntmesh" and str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    return importlib.import_module(package)


def enable(addon):
    if addon.__name__.startswith("bl_ext."):
        if addon_utils.enable(addon.__name__, default_set=True) is None:
            raise RuntimeError("Could not enable the installed TNTMesh extension")
    else:
        addon.register()


def disable(addon):
    if addon.__name__.startswith("bl_ext."):
        addon_utils.disable(addon.__name__, default_set=True)
    else:
        addon.unregister()


class RegistrationTests(unittest.TestCase):
    def test_register_unregister_register(self):
        addon = load_addon()
        for _ in range(2):
            enable(addon)
            try:
                self.assertTrue(hasattr(bpy.types, "TNTMESH_PT_main"))
            finally:
                disable(addon)
            self.assertFalse(hasattr(bpy.types, "TNTMESH_PT_main"))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.addon = load_addon()
        enable(self.addon)
        self.addCleanup(disable, self.addon)
        bpy.context.scene.unit_settings.system = "NONE"
        self.settings = bpy.context.scene.tntmesh_settings
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.directory = Path(scratch.name)

    def parts(self):
        return self.addon.operators.managed_parts(bpy.context, "ALL")

    def cube(self, size=24):
        bpy.ops.mesh.primitive_cube_add(size=size)
        return bpy.context.active_object

    def checked(self, obj):
        model = self.addon.operators
        with model.GeometryTransaction() as transaction:
            mesh, _ = model.evaluated_mm(
                bpy.context, obj, transaction, model.millimeters_per_unit(bpy.context.scene)
            )
            self.assertEqual(model.inspect(mesh).shells, 1)
            return model.inspect(mesh).volume_mm3

    def test_stl_split_connector_export_round_trip(self):
        bpy.context.scene.unit_settings.system = "METRIC"
        bpy.context.scene.unit_settings.scale_length = 0.01
        cube = self.cube()
        input_path = self.directory / "input.stl"
        with input_path.open("wb") as output:
            self.addon.operators.stl.write_binary(cube.data, output)
        bpy.data.objects.remove(cube, do_unlink=True)

        self.assertEqual(bpy.ops.tntmesh.import_stl(filepath=str(input_path)), {"FINISHED"})
        source = bpy.context.active_object
        source_mesh = source.data
        before = tuple(tuple(vertex.co) for vertex in source_mesh.vertices)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        parts = self.parts()
        self.assertEqual(len(parts), 2)
        self.assertTrue(source.hide_get())
        self.assertEqual(source.data, source_mesh)
        self.assertEqual(tuple(tuple(vertex.co) for vertex in source_mesh.vertices), before)
        male, female = parts
        self.assertGreater(self.checked(male), 24**3 / 2)
        self.assertLess(self.checked(female), 24**3 / 2)

        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(self.directory)), {"FINISHED"})
        files = sorted(self.directory.glob("0*.stl"))
        self.assertEqual(len(files), 2)
        snapshots = [path.read_bytes() for path in files]
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(self.directory)), {"FINISHED"})
        self.assertEqual(len(list(self.directory.glob("0*.stl"))), 4)
        self.assertEqual(snapshots, [path.read_bytes() for path in files])
        for path, diameter, depth in zip(files, (5.0, 5.3), (4.0, 4.2), strict=True):
            self.assertEqual(bpy.ops.tntmesh.import_stl(filepath=str(path)), {"FINISHED"})
            restored = bpy.context.active_object
            points = [vertex.co for vertex in restored.data.vertices]
            feature = [point for point in points if abs(point.z - depth) < 1e-5]
            self.assertEqual(len(feature), 64)
            self.assertAlmostEqual(max(point.x for point in feature) -
                                   min(point.x for point in feature), diameter, places=3)
            self.assertAlmostEqual(max(point.y for point in points) -
                                   min(point.y for point in points), 24.0, places=5)
            self.checked(restored)

    def test_negative_nonuniform_transform_kerf_and_consecutive_split(self):
        source = self.cube()
        source.scale = (-2, 0.8, 0.75)
        source.rotation_euler.z = 0.33
        source.location = Vector((12, 22, 32))
        bpy.context.view_layer.update()
        self.settings.connector = "NONE"
        self.settings.kerf = 1.0
        original_volume = self.checked(source)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        parts = self.parts()
        self.assertEqual(len(parts), 2)
        expected = original_volume * (17.0 / 18.0)
        self.assertAlmostEqual(sum(self.checked(part) for part in parts), expected, places=2)
        self.assertEqual(tuple(source.scale), (-2.0, source.scale.y, 0.75))
        self.settings.kerf = 0
        self.settings.axis = "X"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 3)
        self.assertTrue(parts[0].hide_get())
        self.assertAlmostEqual(sum(self.checked(part) for part in self.parts()), expected, places=2)

    def test_hexagonal_clearance(self):
        self.cube()
        self.settings.connector = "HEX"
        self.settings.kerf = 0.6
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        male, female = self.parts()
        for piece, depth, expected in [(male, 4.3, 2.5), (female, 4.5, 2.673205)]:
            radii = [vertex.co.xy.length for vertex in piece.data.vertices
                     if abs(vertex.co.z - depth) < 1e-5]
            self.assertEqual(len(radii), 6)
            for radius in radii:
                self.assertAlmostEqual(radius, expected, places=4)
            self.checked(piece)

    def test_unsafe_connector_and_tangent_leave_no_geometry(self):
        source = self.cube()
        before_objects = set(bpy.data.objects.keys())
        before_meshes = set(bpy.data.meshes.keys())
        self.settings.diameter = 50
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.settings.offset = 12
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(set(bpy.data.objects.keys()), before_objects)
        self.assertEqual(set(bpy.data.meshes.keys()), before_meshes)
        self.assertFalse(source.hide_get())
        self.assertIsNone(source.get("tntmesh_role"))

    def test_torus_cut_through_a_seam_with_a_hole(self):
        bpy.ops.mesh.primitive_torus_add(
            major_radius=10, minor_radius=2, major_segments=48, minor_segments=16
        )
        obj = bpy.context.active_object
        initial = self.checked(obj)
        self.settings.connector = "NONE"
        self.settings.offset = 0.21
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2)
        self.assertAlmostEqual(sum(self.checked(part) for part in self.parts()), initial, places=2)

    def test_nested_shell_preserves_wall_and_volume(self):
        source = self.cube()
        inside = self.cube(12)
        inside.data.flip_normals()
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.join()
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2)
        for part in self.parts():
            self.assertAlmostEqual(self.checked(part), (24**3 - 12**3) / 2, places=3)

    def test_scaled_copy_leaves_input_data_intact(self):
        source = self.cube()
        self.settings.target_size = 36.0
        self.settings.scale_axis = "X"
        self.assertEqual(bpy.ops.tntmesh.resize(), {"FINISHED"})
        resized = bpy.context.active_object
        self.assertNotEqual(resized.data, source.data)
        self.assertAlmostEqual(resized.dimensions.x, 36.0, places=5)
        self.assertAlmostEqual(source.dimensions.x, 24.0, places=5)

    def test_open_model_is_rejected(self):
        bpy.ops.mesh.primitive_plane_add(size=24)
        self.assertEqual(bpy.ops.tntmesh.validate(), {"CANCELLED"})
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise RuntimeError("TNTMesh integration tests failed")
