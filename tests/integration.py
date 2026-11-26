# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import os
import sys
import tempfile
import unittest
from math import sin, tau
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import addon_utils
import bmesh
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

    def test_free_rotation_splits_at_the_requested_plane(self):
        self.cube()
        self.settings.axis = "FREE"
        self.settings.rotation = (0.29, 0.14, 0.0)
        self.settings.offset = 1.5
        self.settings.connector = "NONE"
        frame = self.addon.geometry.planar.axis_frame("FREE", tuple(self.settings.rotation))
        normal = frame.col[2]
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        minus, plus = self.parts()
        self.assertAlmostEqual(max(normal.dot(v.co) for v in minus.data.vertices), 1.5, places=4)
        self.assertAlmostEqual(min(normal.dot(v.co) for v in plus.data.vertices), 1.5, places=4)
        self.assertAlmostEqual(self.checked(minus) + self.checked(plus), 24**3, places=2)

    def test_bezier_split_preserves_volume_and_generates_a_nonplanar_seam(self):
        self.cube()
        self.settings.cut_kind = "BEZIER"
        self.settings.curve_controls = (8.0, -8.0)
        self.settings.curve_samples = 32
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        for part in self.parts():
            self.assertAlmostEqual(self.checked(part), 24**3 / 2, places=2)
            seam = [vertex.co.z for vertex in part.data.vertices if abs(vertex.co.z) < 11.9]
            self.assertGreater(max(seam), 2.0)
            self.assertLess(min(seam), -2.0)

    def test_rectangular_and_elliptical_extraction(self):
        source = self.cube()
        self.settings.offset = 10
        self.settings.profile_size = (8, 6, 8)
        for shape, area in (("RECTANGLE", 48), ("ELLIPSE", 64 * sin(tau / 64) * 4 * 3 / 2)):
            with self.subTest(shape=shape):
                self.settings.cut_kind = shape
                source.hide_set(False)
                for obj in bpy.context.selected_objects:
                    obj.select_set(False)
                source.select_set(True)
                bpy.context.view_layer.objects.active = source
                old = set(self.parts())
                self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
                outside, inside = sorted(set(self.parts()) - old, key=lambda obj: obj.name)
                self.assertAlmostEqual(self.checked(inside), area * 6, places=3)
                self.assertAlmostEqual(self.checked(outside) + self.checked(inside), 24**3, places=2)

    def test_cutter_object_remains_intact(self):
        source = self.cube()
        source.location = (25, 12, 8)
        cutter = self.cube(8)
        cutter.location = (25, 12, 19)
        self.settings.cut_kind = "OBJECT"
        self.settings.cutter = cutter
        cutter.select_set(False)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        bpy.context.view_layer.update()
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        outside, inside = self.parts()
        self.assertAlmostEqual(self.checked(inside), 8 * 8 * 5, places=3)
        self.assertAlmostEqual(self.checked(outside) + self.checked(inside), 24**3, places=2)
        self.assertAlmostEqual(self.checked(cutter), 8**3)

    def test_concave_custom_contour_in_a_draft(self):
        self.cube()
        self.settings.cut_kind = "POLYGON"
        self.settings.contour_depth = 8
        self.settings.offset = 10
        coordinates = [(-4, -4), (-4, 4), (0, 4), (0, 0), (4, 0), (4, -4)]
        for point in coordinates:
            self.settings.contour.add().position = point
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.settings.contour.clear()
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        outside, inside = self.parts()
        self.assertAlmostEqual(self.checked(inside), 48 * 6, places=3)
        self.assertAlmostEqual(self.checked(outside) + self.checked(inside), 24**3, places=2)

    def test_crossing_contour_is_rejected_before_publication(self):
        source = self.cube()
        self.settings.cut_kind = "POLYGON"
        for point in [(-4, -4), (4, 4), (-4, 4), (4, -4)]:
            self.settings.contour.add().position = point
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        self.assertFalse(source.hide_get())

    def test_multiple_fixed_connectors(self):
        self.cube(40)
        self.settings.connector = "HEX"
        self.settings.connector_count = 3
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        male, female = self.parts()
        pin_tips = [vertex for vertex in male.data.vertices if abs(vertex.co.z - 4.0) < 1e-5]
        recesses = [vertex for vertex in female.data.vertices if abs(vertex.co.z - 4.2) < 1e-5]
        self.assertEqual((len(pin_tips), len(recesses)), (18, 18))
        self.checked(male)
        self.checked(female)

    def test_custom_connector_fits_without_scaling_templates(self):
        source = self.cube()
        pin = self.cube(4)
        pin.location.x = -32
        socket = self.cube(4.4)
        socket.location.x = 32
        socket.scale.z = 1.1
        self.settings.connector = "CUSTOM"
        self.settings.pin_template = pin
        self.settings.socket_template = socket
        self.addon.operators.select_results(bpy.context, [source])
        bpy.context.view_layer.update()
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        male, female = self.parts()
        self.assertAlmostEqual(self.checked(male), 24**3 / 2 + 4 * 4 * 2, places=3)
        self.assertAlmostEqual(self.checked(female), 24**3 / 2 - 4.4**2 * 2.42, places=3)
        self.assertEqual((pin.location.x, socket.location.x), (-32, 32))

    def test_custom_connector_rejects_a_socket_that_is_too_small(self):
        source = self.cube()
        self.settings.connector = "CUSTOM"
        self.settings.pin_template = self.cube(4)
        self.settings.socket_template = self.cube(3.5)
        self.addon.operators.select_results(bpy.context, [source])
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])
        self.assertEqual(set(bpy.data.meshes.keys()), before)

    def test_independent_pins_are_watertight_and_exported(self):
        self.cube(40)
        self.settings.connector_count = 2
        self.settings.loose_pins = True
        self.settings.kerf = 0.5
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        pieces = self.parts()
        self.assertEqual(len(pieces), 4)
        for part in pieces[:2]:
            self.assertLess(self.checked(part), 40 * 40 * 19.75)
        pin_area = 64 * sin(tau / 64) * 2.5**2 / 2
        for pin in pieces[2:]:
            self.assertAlmostEqual(self.checked(pin), pin_area * 8.5, places=3)
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(self.directory)), {"FINISHED"})
        self.assertEqual(len(list(self.directory.glob("*.stl"))), 4)

    def test_obj_and_fbx_export_preserve_dimensions(self):
        bpy.context.scene.unit_settings.system = "METRIC"
        bpy.context.scene.unit_settings.scale_length = 0.001
        self.cube()
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        parts = self.parts()
        for format_id in ("OBJ", "FBX"):
            with self.subTest(format=format_id):
                self.addon.operators.select_results(bpy.context, parts)
                self.assertEqual(
                    bpy.ops.tntmesh.export_stl(directory=str(self.directory), file_format=format_id),
                    {"FINISHED"},
                )
                paths = sorted(self.directory.glob("*." + format_id.lower()))
                self.assertEqual(len(paths), 2)
                for path in paths:
                    count = len(bpy.context.scene.objects)
                    if format_id == "OBJ":
                        result = bpy.ops.wm.obj_import(
                            filepath=str(path), forward_axis="Y", up_axis="Z"
                        )
                    else:
                        result = bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False)
                    self.assertEqual(result, {"FINISHED"})
                    self.assertEqual(len(bpy.context.scene.objects), count + 1)
                    self.assertAlmostEqual(self.checked(bpy.context.active_object), 24**3 / 2, places=2)

    def test_3mf_preserves_multiple_build_objects_and_dimensions(self):
        self.cube()
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.parts()[0].name = "Pieza & <01>"
        self.assertEqual(bpy.ops.tntmesh.export_stl(
            directory=str(self.directory), file_format="3MF", grouped_3mf=True,
        ), {"FINISHED"})
        path, = list(self.directory.glob("*.3mf"))
        package_format = self.addon.operators.exporters
        model_io = importlib.import_module(f"{self.addon.__name__}.three_mf")
        with ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertIn("[Content_Types].xml", archive.namelist())
            self.assertIn(b"/3D/3dmodel.model", archive.read("_rels/.rels"))
            doc = ElementTree.fromstring(archive.read(model_io.MODEL_PATH))
        ns = {"m": model_io.CORE}
        self.assertEqual(doc.attrib["unit"], "millimeter")
        resources = doc.findall("m:resources/m:object", ns)
        self.assertEqual(len(resources), 2)
        self.assertTrue(any(obj.attrib["name"].startswith("Pieza &") for obj in resources))
        build = doc.findall("m:build/m:item", ns)
        self.assertEqual({obj.attrib["id"] for obj in resources},
                         {item.attrib["objectid"] for item in build})
        for index, obj in enumerate(resources):
            vertices = obj.findall(".//m:vertex", ns)
            triangles = obj.findall(".//m:triangle", ns)
            points = [tuple(float(v.get(axis)) for axis in "xyz") for v in vertices]
            faces = [tuple(int(t.get(key)) for key in ("v1", "v2", "v3")) for t in triangles]
            with package_format.GeometryTransaction() as transaction:
                mesh = transaction.own_mesh(bpy.data.meshes.new(f"3MF fixture {index}"))
                mesh.from_pydata(points, [], faces)
                self.assertAlmostEqual(package_format.inspect(mesh).volume_mm3, 24**3 / 2)

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

    def test_printer_profile_json_and_tolerance_copy(self):
        self.assertEqual(bpy.ops.tntmesh.printer_add(preset="MARS5"), {"FINISHED"})
        profiles = bpy.context.scene.tntmesh_printers
        entry = profiles[0]
        self.assertAlmostEqual(entry.build_mm.x, 153.36, places=3)
        self.assertEqual(entry.technology, "RESIN")
        entry.margin_mm = (1.5, 2.5, 3.5)
        entry.material = "Resina ABS-Like"
        entry.lateral_mm = 0.3
        self.assertEqual(bpy.ops.tntmesh.printer_edit(action="USE_TOLERANCE"), {"FINISHED"})
        self.assertAlmostEqual(self.settings.lateral, 0.3, places=5)
        path = self.directory / "profile.json"
        self.assertEqual(bpy.ops.tntmesh.printer_export(filepath=str(path)), {"FINISHED"})
        original = path.read_bytes()
        self.assertEqual(bpy.ops.tntmesh.printer_export(filepath=str(path)), {"CANCELLED"})
        self.assertEqual(original, path.read_bytes())
        self.assertEqual(bpy.ops.tntmesh.printer_import(filepath=str(path)), {"FINISHED"})
        self.assertEqual(profiles[1].data(), profiles[0].data())
        self.assertEqual(bpy.ops.tntmesh.printer_edit(action="DUPLICATE"), {"FINISHED"})
        self.assertEqual(len(profiles), 3)
        path.write_text('{"schema":1,"profile":{"build_mm":[0,0,0]}}', encoding="utf-8")
        self.assertEqual(bpy.ops.tntmesh.printer_import(filepath=str(path)), {"CANCELLED"})
        self.assertEqual(len(profiles), 3)

    def test_printer_fit_checks_margins_and_alternate_orientation(self):
        printing = self.addon.printer_ui
        profile = printing.PrinterProfile("", "Test", "FDM", (50, 30, 20), (1, 1, 1))
        fit = printing.fit
        self.assertEqual(fit((42, 27, 17), profile).exceeded, ())
        result = fit((26, 43, 16), profile)
        self.assertEqual(result.exceeded, ("Y",))
        self.assertEqual(result.alternative, "YXZ")
        self.assertIsNone(fit((51, 28, 19), profile).alternative)

    def test_split_to_fit_validates_each_piece_and_rolls_back_at_limit(self):
        source = self.cube(36)
        source.scale = (1.0, 20 / 36, 16 / 36)
        self.assertEqual(bpy.ops.tntmesh.printer_add(), {"FINISHED"})
        profile = bpy.context.scene.tntmesh_printers[0]
        profile.build_mm = (20, 15, 20)
        profile.margin_mm = (1, 1, 1)
        previous_meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.fit_grid(max_pieces=3), {"CANCELLED"})
        self.assertEqual(set(bpy.data.meshes.keys()), previous_meshes)
        self.assertFalse(source.hide_get())
        self.assertEqual(self.parts(), [])
        self.assertEqual(bpy.ops.tntmesh.fit_grid(max_pieces=4), {"FINISHED"})
        self.assertEqual(len(self.parts()), 4)
        self.assertTrue(source.hide_get())
        self.assertAlmostEqual(sum(self.checked(part) for part in self.parts()), 36 * 20 * 16, places=2)
        for part in self.parts():
            self.assertFalse(self.addon.printer_ui.fit(tuple(part.dimensions), profile.data()).exceeded)

    def test_calibration_produces_engraved_printable_socket_range(self):
        source = self.cube()
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = .01
        self.assertEqual(bpy.ops.tntmesh.calibrate_connectors(material="PLA"), {"FINISHED"})
        model = self.addon.calibration_ui
        pin, = [obj for obj in self.parts() if obj.get(model.CALIBRATION) == "PIN"]
        sockets = [obj for obj in self.parts() if obj.get(model.CALIBRATION) == "SOCKET"]
        self.assertEqual([obj[model.CLEARANCE] for obj in sockets],
                         [.05, .10, .15, .20, .25, .30, .35, .40])
        self.assertFalse(source.hide_get())
        self.assertEqual(len(source.data.polygons), 6)
        self.assertEqual(len({(obj.location.x, obj.location.y) for obj in [pin, *sockets]}), 9)
        self.assertAlmostEqual(pin.dimensions.z * 10, 5.4, places=5)
        for obj in sockets:
            self.checked(obj)
            self.assertEqual(obj[model.MATERIAL], "PLA")
            points = [v.co * 10 for v in obj.data.vertices]
            floor_x = [p.x for p in points if abs(p.z - 1.4) < 1e-5]
            expected = model.Connector(lateral=obj[model.CLEARANCE]).socket_radius * 2
            self.assertAlmostEqual(max(floor_x) - min(floor_x), expected, places=4)
            self.assertTrue(any(abs(p.z - (5.6 - .45)) < 1e-5 for p in points))
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(self.directory)), {"FINISHED"})
        self.assertEqual(len(list(self.directory.glob("*.stl"))), 9)
        self.assertEqual(bpy.ops.tntmesh.printer_add(preset="A1"), {"FINISHED"})
        self.addon.operators.select_results(bpy.context, [sockets[4]])
        self.assertEqual(bpy.ops.tntmesh.save_calibrated_clearance(), {"FINISHED"})
        self.assertAlmostEqual(scene.tntmesh_printers[0].lateral_mm, .25)

    def test_calibration_count_and_bad_range_leave_no_temporary_data(self):
        model = self.addon.calibration_ui
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.calibrate_connectors(start=.2, end=.1), {"CANCELLED"})
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        self.assertEqual(self.parts(), [])
        self.assertEqual(bpy.ops.tntmesh.calibrate_connectors(
            sampling="COUNT", count=3, start=.05, end=.24, shape="HEX", engraved=False,
        ), {"FINISHED"})
        sockets = [obj for obj in self.parts() if obj.get(model.CALIBRATION) == "SOCKET"]
        self.assertEqual([obj[model.CLEARANCE] for obj in sockets], [.05, .145, .24])
        for obj in sockets:
            self.checked(obj)

    def test_material_region_is_a_closed_solid_and_keeps_the_source(self):
        source = self.cube()
        mesh = source.data
        mesh.materials.append(bpy.data.materials.new("Body"))
        mesh.materials.append(bpy.data.materials.new("Top"))
        top = max(mesh.polygons, key=lambda face: face.normal.z)
        top.material_index = 1
        mesh.update()
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "MATERIAL"
        self.settings.region_slot = 2
        self.settings.region_depth = 3.0
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        remainder, extract = self.parts()
        self.assertAlmostEqual(extract.dimensions.z, 3, places=5)
        self.assertAlmostEqual(self.checked(extract), 24 * 24 * 3, places=3)
        self.assertAlmostEqual(self.checked(remainder) + self.checked(extract), 24**3, places=3)
        self.assertEqual(len(mesh.polygons), 6)
        self.assertEqual(top.material_index, 1)

    def test_region_wraps_two_adjacent_faces_without_leaving_an_open_corner(self):
        source = self.cube()
        for face in source.data.polygons:
            face.select = max(face.normal.x, face.normal.z) > .9
        source.data.update()
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "SELECTION"
        self.settings.region_depth = 2
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        remainder, extract = self.parts()
        self.assertAlmostEqual(self.checked(extract), 2 * 24 * 24 * 2 - 2 * 2 * 24,
                               places=3)
        self.assertAlmostEqual(self.checked(remainder) + self.checked(extract), 24**3, places=3)

    def test_color_selection_and_vertex_groups_share_the_same_closed_output(self):
        for method in ("COLOR", "VERTEX_GROUP", "FACE_MASK", "SELECTION"):
            with self.subTest(method=method):
                source = self.cube()
                mesh = source.data
                top = max(mesh.polygons, key=lambda face: face.normal.z)
                for face in mesh.polygons:
                    face.select = face.index == top.index
                mask = mesh.attributes.new(name="Top mask", type="BOOLEAN", domain="FACE")
                mask.data[top.index].value = True
                colors = mesh.color_attributes.new(name="Colors", type="FLOAT_COLOR", domain="CORNER")
                for i in range(len(colors.data)):
                    colors.data[i].color = (1, 0, 0, 1) if i in top.loop_indices else (0, 0, 1, 1)
                source.vertex_groups.new(name="Top region").add(tuple(top.vertices), 1, "REPLACE")
                mesh.update()
                self.settings.cut_kind = "REGION"
                self.settings.region_method = method
                self.settings.region_attribute = {
                    "COLOR": "Colors", "VERTEX_GROUP": "Top region", "FACE_MASK": "Top mask",
                }.get(method, "")
                previous = set(self.parts())
                self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
                parts = sorted(set(self.parts()) - previous, key=lambda obj: obj.name)
                self.assertAlmostEqual(self.checked(parts[1]), 24 * 24 * 2, places=3)

    def test_region_in_a_draft_can_rebuild_and_reject_a_fully_selected_patch(self):
        source = self.cube()
        mesh = source.data
        mask = mesh.attributes.new(name="Top mask", type="BOOLEAN", domain="FACE")
        top = max(mesh.polygons, key=lambda face: face.normal.z)
        mask.data[top.index].value = True
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "FACE_MASK"
        self.settings.region_attribute = "Top mask"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        parts = set(self.parts())
        before = set(bpy.data.meshes.keys())
        for value in mask.data:
            value.value = True
        mesh.update()
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"CANCELLED"})
        self.assertEqual(set(self.parts()), parts)
        self.assertEqual(set(bpy.data.meshes.keys()), before)

    def test_symmetric_cuts_place_separate_pins_at_reflected_coordinates(self):
        source = self.cube(48)
        self.settings.cut_kind = "SYMMETRY"
        self.settings.axis = "X"
        self.settings.offset = 11
        self.settings.symmetry_axis = "X"
        self.settings.symmetry_center = 2
        self.settings.connector = "HEX"
        self.settings.loose_pins = True
        self.settings.connector_count = 2
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        bodies, pins = self.parts()[:3], self.parts()[3:]
        self.assertEqual(len(pins), 4)
        self.assertTrue(all("Pin " in obj.name for obj in pins))
        self.assertTrue(all("Pin " not in obj.name for obj in bodies))
        for obj in [*bodies, *pins]:
            self.checked(obj)
        centers = [sum((vertex.co for vertex in obj.data.vertices), Vector()) /
                   len(obj.data.vertices) for obj in pins]
        for primary, mirrored in zip(centers[:2], centers[2:], strict=True):
            self.assertAlmostEqual(primary.x + mirrored.x, 4, places=5)
            self.assertAlmostEqual(primary.y, mirrored.y, places=5)
            self.assertAlmostEqual(primary.z, mirrored.z, places=5)
        self.assertTrue(source.hide_get())
        self.assertEqual(len(source.data.polygons), 6)

    def test_symmetric_draft_exposes_the_third_piece_and_can_shift_the_second_cut(self):
        self.cube(48)
        self.settings.cut_kind = "SYMMETRY"
        self.settings.axis = "X"
        self.settings.offset = 10
        self.settings.symmetry_secondary = 2
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        plan = self.addon.draft.active_plan(bpy.context.scene)
        keys = self.addon.draft.cut_outputs(plan.cuts[0])
        self.assertEqual(len(keys), 3)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 3)
        self.assertAlmostEqual(self.parts()[0].dimensions.x, 14)
        self.assertAlmostEqual(self.parts()[1].dimensions.x, 22)
        self.assertAlmostEqual(self.parts()[2].dimensions.x, 12)
        self.assertAlmostEqual(sum(self.checked(part) for part in self.parts()), 48**3)

    def test_coincident_symmetric_cuts_leave_no_parts(self):
        source = self.cube()
        self.settings.cut_kind = "SYMMETRY"
        self.settings.axis = "Z"
        self.settings.offset = 5
        self.settings.symmetry_axis = "X"
        self.settings.connector = "NONE"
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])
        self.assertFalse(source.hide_get())
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)

    def test_exploded_preview_does_not_change_original_transforms_or_exports(self):
        self.cube()
        self.settings.axis = "X"
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.assembly_project(), {"FINISHED"})
        pieces = self.parts()
        transforms = {obj: obj.matrix_world.copy() for obj in pieces}
        baseline = self.directory / "baseline"
        expanded = self.directory / "expanded"
        baseline.mkdir()
        expanded.mkdir()
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(baseline)), {"FINISHED"})
        state = bpy.context.scene.tntmesh_assembly
        state.distance = 8
        offsets = self.addon.assembly_view.offsets(bpy.context)
        self.assertEqual([tuple(offset) for _, _, offset in offsets], [(-8, 0, 0), (8, 0, 0)])
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(expanded)), {"FINISHED"})
        self.assertEqual({path.name: path.read_bytes() for path in baseline.glob("*.stl")},
                         {path.name: path.read_bytes() for path in expanded.glob("*.stl")})
        self.assertEqual({obj: obj.matrix_world for obj in pieces}, transforms)
        self.assertEqual(bpy.ops.tntmesh.assembly_action(action="RESET"), {"FINISHED"})
        self.assertEqual(state.distance, 0)

    def test_static_assembly_check_distinguishes_contact_from_interpenetration(self):
        self.cube()
        self.settings.axis = "X"
        self.settings.connector = "ROUND"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        first, second = self.parts()
        before = set(bpy.data.meshes.keys())
        self.assertEqual(self.addon.assembly.overlaps(bpy.context, [first, second]), [])
        first.location.x += 1
        bpy.context.view_layer.update()
        conflict, = self.addon.assembly.overlaps(bpy.context, [first, second])
        self.assertEqual(set(conflict[:2]), {first, second})
        self.assertGreater(conflict[2], 540)
        self.assertEqual(set(bpy.data.meshes.keys()), before)

    def test_assembly_visibility_and_copy_are_scoped_to_the_project(self):
        source = self.cube()
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        original = self.parts()
        self.assertEqual(bpy.ops.tntmesh.assembly_project(), {"FINISHED"})
        outside = self.cube(10)
        self.assertEqual(bpy.ops.tntmesh.assembly_action(action="ISOLATE"), {"FINISHED"})
        self.assertEqual(sum(obj.hide_get() for obj in original), 1)
        self.assertFalse(outside.hide_get())
        self.assertEqual(bpy.ops.tntmesh.assembly_action(action="SHOW_ALL"), {"FINISHED"})
        self.assertFalse(any(obj.hide_get() for obj in original))
        self.assertEqual(bpy.ops.tntmesh.assembly_action(action="DUPLICATE"), {"FINISHED"})
        copied, = set(self.parts()) - set(original)
        self.assertEqual(len({obj.get("tntmesh_part_id") for obj in self.parts()}), 3)
        self.assertTrue(all(copied.data != obj.data for obj in original))
        self.assertEqual(bpy.ops.tntmesh.assembly_action(action="DELETE"), {"FINISHED"})
        self.assertEqual(self.parts(), original)
        self.assertIn(source, bpy.data.objects.values())
        self.assertIn(outside, bpy.data.objects.values())

    def test_open_model_is_rejected(self):
        bpy.ops.mesh.primitive_plane_add(size=24)
        self.assertEqual(bpy.ops.tntmesh.validate(), {"CANCELLED"})
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])

    def test_repair_closes_a_small_hole_on_a_copy(self):
        source = self.cube()
        bm = bmesh.new()
        try:
            bm.from_mesh(source.data)
            bm.faces.remove(next(iter(bm.faces)))
            bm.to_mesh(source.data)
        finally:
            bm.free()
        source.data.update()
        before = set(bpy.data.objects.keys())
        self.assertEqual(bpy.ops.tntmesh.repair(), {"CANCELLED"})
        self.assertEqual(set(bpy.data.objects.keys()), before)
        self.settings.repair_holes = True
        self.assertEqual(bpy.ops.tntmesh.repair(), {"FINISHED"})
        result = bpy.context.active_object
        self.assertNotEqual(result, source)
        self.assertEqual(len(source.data.polygons), 5)
        self.assertAlmostEqual(self.checked(result), 24**3, places=3)

    def test_dependent_draft_saves_and_preserves_identity_on_rebuild(self):
        source = self.cube()
        source_mesh = source.data
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        draft = self.addon.draft.active_plan(bpy.context.scene)
        draft.cuts[1].settings.axis = "X"
        draft.cuts[1].name = "Second cut"
        cuts = [cut.uid for cut in draft.cuts]
        self.assertEqual(self.parts(), [])
        self.assertEqual(source.data, source_mesh)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        first_build = {obj["tntmesh_part_id"]: obj.name for obj in self.parts()}
        self.assertEqual(len(first_build), 3)
        self.assertAlmostEqual(sum(self.checked(part) for part in self.parts()), 24**3)

        path = self.directory / "saved-draft.blend"
        self.assertEqual(bpy.ops.wm.save_as_mainfile(filepath=str(path)), {"FINISHED"})
        self.assertEqual(bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False), {"FINISHED"})
        draft = self.addon.draft.active_plan(bpy.context.scene)
        self.assertEqual([cut.uid for cut in draft.cuts], cuts)
        self.assertEqual(draft.cuts[1].name, "Second cut")
        self.assertEqual(draft.cuts[1].settings.axis, "X")
        draft.cuts[1].settings.offset = 2.5
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        self.assertEqual({obj["tntmesh_part_id"]: obj.name for obj in self.parts()}, first_build)
        self.assertEqual(len(list(bpy.context.scene.objects)), 4)
        self.assertAlmostEqual(self.checked(draft.source), 24**3)

    def test_failed_draft_build_keeps_prior_meshes_and_selection(self):
        source = self.cube()
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="DUPLICATE"), {"FINISHED"})
        plan = self.addon.draft.active_plan(bpy.context.scene)
        original, duplicate = plan.cuts
        self.assertNotEqual(duplicate.uid, original.uid)
        self.assertFalse(duplicate.enabled)
        duplicate.enabled = True
        duplicate.settings.offset = 100.0
        prior = {obj.as_pointer(): obj.data.as_pointer() for obj in self.parts()}
        selected = {obj.as_pointer() for obj in bpy.context.selected_objects}
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"CANCELLED"})
        self.assertEqual(
            bpy.ops.tntmesh.draft_target(target=self.addon.draft.cut_outputs(original)[0]),
            {"FINISHED"},
        )
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"CANCELLED"})
        self.assertEqual({obj.as_pointer(): obj.data.as_pointer() for obj in self.parts()}, prior)
        self.assertEqual({obj.as_pointer() for obj in bpy.context.selected_objects}, selected)
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)
        self.assertTrue(source.hide_get())

    def test_rebuild_keeps_objects_duplicated_outside_draft_ownership(self):
        self.cube()
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        part = self.parts()[0]
        foreign_copy = part.copy()
        foreign_copy.data = part.data.copy()
        foreign_copy.name = "User copy"
        part.users_collection[0].objects.link(foreign_copy)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        self.assertIs(bpy.context.scene.objects["User copy"], foreign_copy)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise RuntimeError("TNTMesh integration tests failed")
