# SPDX-License-Identifier: GPL-3.0-or-later
import importlib
import os
import sys
import tempfile
import unittest
from math import cos, pi, sin, sqrt, tau
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


def stepped_base_fixture(model, *, single=False):
    context = bpy.context
    factory = model.operators.GeometryTransaction
    volume = importlib.import_module(f"{model.__name__}.geometry.volume")
    boolean = importlib.import_module(f"{model.__name__}.geometry.boolean")
    matrix = model.operators.Matrix.Identity(3)
    if single:
        boxes = ((0, 0, 0, 3, 40, 24), (0, 0, 2.5, 21, 6, 6))
    else:
        boxes = (
            (0, 0, 0, 3, 40, 24), (10, 0, 2.5, 5, 10, 10),
            (-9, 0, 2.5, 18, 6, 6), (10, 0, 4.5, 18, 6, 6),
            (0, 0, 15, 21, 34, 9),
        )
    with factory() as transaction:
        engine = boolean.ExactBoolean(context, transaction)
        slab = None
        for x, y, low, high, width, length in boxes:
            outline = volume.outline("RECTANGLE", width, length)
            box = volume.extruded_volume(
                transaction, matrix, Vector((x, y, (low + high) / 2)), outline, high - low,
            )
            slab = box if slab is None else engine.run(slab, box, "UNION")
        source = transaction.object(context.scene.collection, "Stepped base fixture", slab)
        transaction.publish(source)
    context.view_layer.update()
    model.operators.select_results(context, [source])
    return source


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

    def checked(self, obj, *, shells=1):
        model = self.addon.operators
        with model.GeometryTransaction() as transaction:
            mesh, _ = model.evaluated_mm(
                bpy.context, obj, transaction, model.millimeters_per_unit(bpy.context.scene)
            )
            result = model.inspect(mesh)
            self.assertEqual(result.shells, shells)
            return result.volume_mm3

    def test_dovetail_rails_slide_out_and_hold_against_normal_pull(self):
        from mathutils.bvhtree import BVHTree

        context = bpy.context
        source = self.cube(36)
        self.settings.connector = "DOVETAIL"
        self.settings.kerf = .2
        for x in (-8, 8):
            self.settings.connector_points.add().position = (x, 3)
        original = source.data
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        male, female = self.parts()
        self.assertEqual(source.data, original)
        expected = 36 * 36 * 17.9 + 2 * (3 * 5 + .2 * 4) * 7
        self.assertAlmostEqual(self.checked(male), expected, delta=.03)
        self.assertLess(self.checked(female), 36 * 36 * 17.9 - 400)
        socket = BVHTree.FromPolygons([v.co for v in female.data.vertices],
                                      [tuple(p.vertices) for p in female.data.polygons])
        start = Vector((-8, 3, 1.6))
        point, _, _, _ = socket.ray_cast(start, Vector((1, 0, 0)))
        self.assertAlmostEqual(point.x - start.x, 2 + 1.5 / 3 + .15 * sqrt(1 + (1 / 3)**2), places=4)
        point, _, _, _ = socket.ray_cast(start, Vector((0, 0, 1)))
        self.assertAlmostEqual(point.z, .1 + 3.15, places=4)
        point, _, _, _ = socket.ray_cast(start, Vector((0, -1, 0)))
        self.assertAlmostEqual(point.y, -.7, places=4)
        assembly = self.addon.assembly
        axis = assembly.slide_direction(male, context.evaluated_depsgraph_get())
        self.assertEqual(tuple(axis), (0, 1, 0))
        travel = assembly.slide_travel(context, male, [male, female], axis)
        self.assertAlmostEqual(travel, 37)
        self.assertEqual(assembly.overlaps(context, [male, female]), [])
        self.assertIsNone(assembly.insertion_hit(context, male, [female], axis, travel))
        hit = assembly.insertion_hit(context, male, [female], Vector((0, 0, -1)), 7)
        self.assertIsNotNone(hit)
        self.assertGreater(hit.volume_mm3, .00001)
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(self.directory)), {"FINISHED"})
        self.assertEqual(len(list(self.directory.glob("*.stl"))), 2)

    def test_connector_profiles_build_closed_integrated_and_loose_parts(self):
        shapes = importlib.import_module(f"{self.addon.__name__}.geometry.connector_profiles")
        context = bpy.context
        assembly = self.addon.assembly
        for index, (shape, _, _) in enumerate(shapes.PROFILE_ITEMS):
            with self.subTest(shape=shape):
                source = self.cube(30)
                source.location.x = index * 40
                settings = self.settings
                settings.connector = shape
                settings.connector_angle = .29
                settings.loose_pins = index % 2 == 0
                settings.kerf = .2
                settings.connector_points.clear()
                settings.connector_points.add().position = (2, 3)
                context.view_layer.update()
                self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
                result = list(context.selected_objects)
                self.assertEqual(len(result), 3 if settings.loose_pins else 2)
                for obj in result:
                    self.checked(obj)
                self.assertEqual(assembly.overlaps(context, result), [])
                self.assertEqual(len(source.data.polygons), 6)

    def test_tapered_pin_has_the_configured_normal_clearance(self):
        from mathutils.bvhtree import BVHTree

        self.cube(30)
        settings = self.settings
        settings.connector = "TAPER"
        settings.diameter = 6
        settings.insertion = 4
        settings.lateral = .2
        settings.axial = .3
        settings.connector_taper = 50
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        male, socket = self.parts()
        theta = pi / 64
        side_direction = Vector((cos(theta), sin(theta), 0))
        hits = []
        for piece in (male, socket):
            tree = BVHTree.FromPolygons([v.co for v in piece.data.vertices], [p.vertices[:] for p in piece.data.polygons])
            _, _, _, distance = tree.ray_cast(Vector((0, 0, 2)), side_direction)
            hits.append(distance)
        self.assertAlmostEqual(hits[0], 2.25 * cos(theta), places=4)
        self.assertAlmostEqual((hits[1] - hits[0]) / sqrt(1 + (1.5 / 4 * cos(theta))**2), .2, places=4)
        self.assertAlmostEqual(max(v.co.x for v in male.data.vertices if abs(v.co.z - 4) < 1e-5), 1.5, places=4)

    def test_elongated_profile_uses_its_actual_footprint_for_clearance_and_spacing(self):
        from mathutils.bvhtree import BVHTree

        self.cube(26)
        settings = self.settings
        settings.connector = "RECTANGLE"
        settings.connector_width, settings.connector_height = 10, 2
        settings.lateral, settings.wall = .2, .5
        for y in (-2.1, 2.1):
            settings.connector_points.add().position = (0, y)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        male, female = self.parts()
        self.assertAlmostEqual(self.checked(male), 26**3 / 2 + 160, places=3)
        tree = BVHTree.FromPolygons([v.co for v in female.data.vertices], [p.vertices[:] for p in female.data.polygons])
        start = Vector((0, -2.1, 2))
        for axis, expected in (((1, 0, 0), 5.2), ((0, 1, 0), 1.2)):
            self.assertAlmostEqual(tree.ray_cast(start, Vector(axis))[3], expected, places=5)
        invalid = self.cube(26)
        settings.connector_points[0].position = (0, 0)
        settings.connector_points[1].position = (0, 2)
        data = tuple(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(bpy.context.active_object, invalid)
        self.assertEqual(tuple(bpy.data.meshes.keys()), data)

    def test_keyed_profile_keeps_orientation_on_the_positive_pin_side_and_in_clipboard(self):
        self.cube(28)
        settings = self.settings
        settings.connector = "D"
        settings.connector_angle = .37
        settings.pin_positive = True
        self.assertEqual(bpy.ops.tntmesh.suggest_connectors(), {"FINISHED"})
        position, = (tuple(p.position) for p in settings.connector_points)
        ui = self.addon.connector_ui
        design = settings.standard_connector("D", 1)
        self.assertEqual(ui.decode(ui.encode(design, (position,), True)), (design, (position,), True))
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        female, male = self.parts()
        tip = [v.co for v in male.data.vertices if abs(v.co.z + design.insertion) < 1e-5]
        self.assertTrue(tip)
        for x, y in design.profile():
            expected = Vector((x + position[0], y + position[1], -design.insertion))
            self.assertLess(min((p - expected).length for p in tip), 1e-5)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, [male, female]))

    def test_symmetric_cut_reflects_a_rotated_keyed_profile(self):
        self.cube(40)
        settings = self.settings
        settings.cut_kind = "SYMMETRY"
        settings.symmetry_axis = settings.axis = "X"
        settings.offset = -8
        settings.connector = "D"
        settings.insertion = 3
        settings.connector_angle = .37
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        left, center, right = self.parts()
        left_tip = [v.co for v in left.data.vertices if abs(v.co.x + 5) < 1e-5]
        right_tip = [v.co for v in right.data.vertices if abs(v.co.x - 5) < 1e-5]
        self.assertEqual(len(left_tip), len(right_tip))
        self.assertGreater(len(left_tip), 12)
        for point in left_tip:
            mirror = Vector((-point.x, point.y, point.z))
            self.assertLess(min((other - mirror).length for other in right_tip), 1e-5)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, [left, center, right]))

    def test_taper_calibration_has_a_full_width_entry_and_a_narrower_floor(self):
        self.assertEqual(bpy.ops.tntmesh.calibrate_connectors(
            shape="TAPER", diameter=6, connector_taper=40, start=.25, end=.25, engraved=False,
        ), {"FINISHED"})
        state = self.addon.calibration_ui
        socket, = [obj for obj in self.parts() if obj.get(state.CALIBRATION) == "SOCKET"]
        self.checked(socket)
        floor = [v.co.x for v in socket.data.vertices if abs(v.co.z - 1.4) < 1e-5]
        mouth = [v.co.x for v in socket.data.vertices if abs(v.co.z - 5.6) < 1e-5 and abs(v.co.x) < 3.4]
        self.assertAlmostEqual(max(mouth) - min(mouth) - (max(floor) - min(floor)), 2.4, places=4)

    def test_dovetail_suggestion_clipboard_and_positive_side_keep_the_exit_direction(self):
        self.cube(34)
        settings = self.settings
        settings.connector = "DOVETAIL"
        settings.dovetail_angle = tau / 4
        settings.pin_positive = True
        settings.loose_pins = True
        settings.connector_count = 2
        self.assertEqual(bpy.ops.tntmesh.suggest_connectors(), {"FINISHED"})
        positions = [tuple(point.position) for point in settings.connector_points]
        self.assertEqual(len(positions), 2)
        ui = self.addon.connector_ui
        design = settings.dovetail_config(len(positions))
        payload = ui.encode(design, tuple(positions), settings.pin_positive)
        settings.connector = "ROUND"
        settings.dovetail_angle = 0
        settings.connector_points.clear()
        design, copied_positions, positive = ui.decode(payload)
        ui.check_positions(bpy.context, settings, design, copied_positions, positive)
        ui.apply_setup(settings, design, copied_positions, positive)
        self.assertEqual(settings.connector, "DOVETAIL")
        self.assertEqual([tuple(point.position) for point in settings.connector_points], positions)
        self.assertTrue(settings.pin_positive)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        female, male = self.parts()
        self.assertGreater(self.checked(male), 34**3 / 2 + 200)
        self.assertLess(self.checked(female), 34**3 / 2 - 300)
        axis = self.addon.assembly.slide_direction(male, bpy.context.evaluated_depsgraph_get())
        self.assertAlmostEqual(axis.x, -1, places=5)
        self.assertAlmostEqual(axis.y, 0, places=5)

    def test_dovetail_draft_checks_wall_before_replacing_the_previous_build(self):
        self.cube(24)
        self.settings.connector = "DOVETAIL"
        self.settings.dovetail_height = 4.2
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        plan = bpy.context.scene.tntmesh_drafts[0]
        cut = plan.cuts[0].settings
        self.assertAlmostEqual(cut.dovetail_height, 4.2, places=5)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        previous = self.parts()
        meshes = tuple(bpy.data.meshes.keys())
        cut.lateral = 2
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"CANCELLED"})
        cut.lateral = .15
        cut.wall = 14
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"CANCELLED"})
        self.assertEqual(self.parts(), previous)
        self.assertEqual(tuple(bpy.data.meshes.keys()), meshes)

    def test_dovetail_symmetric_cut_preserves_both_sliding_joints(self):
        self.cube(32)
        self.settings.connector = "DOVETAIL"
        self.settings.cut_kind = "SYMMETRY"
        self.settings.axis = "X"
        self.settings.symmetry_axis = "X"
        self.settings.offset = -8
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        left, middle, right = self.parts()
        self.assertAlmostEqual(self.checked(left), self.checked(right), delta=.02)
        self.assertGreater(self.checked(left), 32 * 32 * 8)
        self.assertLess(self.checked(middle), 32 * 32 * 16)
        self.assertEqual(self.addon.assembly.overlaps(bpy.context, self.parts()), [])
        for moving in (left, right):
            axis = self.addon.assembly.slide_direction(moving, bpy.context.evaluated_depsgraph_get())
            self.assertIsNotNone(axis)
            self.assertIsNone(self.addon.assembly.insertion_hit(bpy.context, moving, self.parts(), axis, 33))

    def test_dovetail_rejects_a_channel_that_reaches_a_disconnected_body(self):
        source = self.cube(24)
        obstruction = self.cube(4)
        obstruction.location = (0, 18, 3)
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.join()
        self.settings.connector = "DOVETAIL"
        self.settings.kerf = .2
        self.settings.connector_points.add().position = (0, 0)
        meshes = tuple(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])
        self.assertEqual(tuple(bpy.data.meshes.keys()), meshes)
        self.assertEqual(bpy.context.active_object.data, source.data)

    def test_resin_hollow_preserves_source_and_suggested_drain_exports_a_plug(self):
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = .01
        source = self.cube(2.4)
        source.location = (3, -4, 5)
        original = source.data
        settings = scene.tntmesh_resin
        self.assertEqual(bpy.ops.tntmesh.hollow_resin(), {"FINISHED"})
        hollow = bpy.context.active_object
        self.assertEqual(source.data, original)
        self.assertAlmostEqual(self.checked(source), 24**3, delta=.01)
        hollow_volume = self.checked(hollow, shells=2)
        self.assertAlmostEqual(hollow_volume, 24**3 - 20**3, delta=30)
        self.assertEqual(tuple(hollow.location), (3, -4, 5))
        settings.print_axis = (1, 0, 0)
        settings.make_plug = True
        self.assertEqual(bpy.ops.tntmesh.drain_resin(suggested=True), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2)
        drained = bpy.context.active_object
        self.assertAlmostEqual(hollow_volume - self.checked(drained), 25, delta=.5)
        plug = next(obj for obj in self.parts() if obj != drained)
        self.assertAlmostEqual(self.checked(plug), 21.5, delta=.5)
        self.assertEqual(bpy.ops.tntmesh.export_stl(directory=str(self.directory)), {"FINISHED"})
        self.assertEqual(len(list(self.directory.glob("*.stl"))), 2)

    def test_resin_protects_a_region_and_rejects_blind_drain_without_changes(self):
        source = self.cube()
        protection = self.cube(6)
        protection.location = (0, 0, -10)
        protection.hide_set(True)
        protection_mesh = protection.data
        settings = bpy.context.scene.tntmesh_resin
        settings.protection = protection
        settings.reinforcement_mm = 1
        self.addon.operators.select_results(bpy.context, [source])
        self.assertEqual(bpy.ops.tntmesh.hollow_resin(), {"FINISHED"})
        hollow = bpy.context.active_object
        self.assertGreater(self.checked(hollow, shells=2), 24**3 - 20**3 + 150)
        self.assertTrue(protection.hide_get())
        self.assertEqual(protection.data, protection_mesh)
        settings.depth_mm = 3
        names = tuple(bpy.data.objects.keys())
        meshes = tuple(bpy.data.meshes.keys())
        for point, normal in (((0, 0, -12), (0, 0, -1)), ((0, 0, -10), (0, 0, -1))):
            self.assertEqual(bpy.ops.tntmesh.drain_resin(point=point, normal=normal), {"CANCELLED"})
        self.assertEqual(tuple(bpy.data.objects.keys()), names)
        self.assertEqual(tuple(bpy.data.meshes.keys()), meshes)
        self.assertEqual(bpy.context.active_object, hollow)
        self.assertFalse(bpy.data.node_groups)

    def test_resin_custom_drain_preserves_its_cutter(self):
        self.cube()
        self.assertEqual(bpy.ops.tntmesh.hollow_resin(), {"FINISHED"})
        hollow = bpy.context.active_object
        cutter = self.cube(4)
        cutter.scale.x = .5
        cutter.location.z = -11
        original = cutter.data
        settings = bpy.context.scene.tntmesh_resin
        settings.shape = "CUSTOM"
        settings.cutter = cutter
        self.addon.operators.select_results(bpy.context, [hollow])
        self.assertEqual(bpy.ops.tntmesh.drain_resin(point=(0, 0, -12)), {"FINISHED"})
        self.assertAlmostEqual(self.checked(hollow, shells=2) - self.checked(bpy.context.active_object),
                               16, delta=.02)
        self.assertEqual(cutter.data, original)
        self.assertEqual(tuple(cutter.location), (0, 0, -11))

    def test_resin_adds_a_second_drain_after_save_and_translation(self):
        self.cube()
        self.assertEqual(bpy.ops.tntmesh.hollow_resin(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.drain_resin(suggested=True), {"FINISHED"})
        part = bpy.context.active_object
        part.location = (10, 20, -5)
        one_drain = self.checked(part)
        filepath = str(self.directory / "resin.blend")
        bpy.ops.wm.save_as_mainfile(filepath=filepath)
        bpy.ops.wm.open_mainfile(filepath=filepath)
        current = bpy.context.active_object
        self.assertIsInstance(current[self.addon.resin_ui.RESIN_REFERENCE], bpy.types.Mesh)
        self.assertEqual(bpy.ops.tntmesh.drain_resin(point=(10, 20, -17)), {"CANCELLED"})
        self.assertEqual(bpy.context.active_object, current)
        self.assertEqual(bpy.ops.tntmesh.drain_resin(suggested=True), {"FINISHED"})
        self.assertAlmostEqual(one_drain - self.checked(bpy.context.active_object), 25, delta=.5)

    def test_resin_no_room_preserves_the_selected_mesh(self):
        source = self.cube(3)
        self.assertEqual(bpy.ops.tntmesh.hollow_resin(), {"CANCELLED"})
        self.assertEqual(bpy.context.active_object, source)
        self.assertEqual(self.parts(), [])
        self.assertFalse(bpy.data.node_groups)

    def resin_cup(self, vent_z=None):
        addon, context = self.addon, bpy.context
        volume = importlib.import_module(f"{addon.__name__}.geometry.volume")
        boolean = importlib.import_module(f"{addon.__name__}.geometry.boolean")
        original = self.cube()
        with addon.operators.GeometryTransaction() as transaction:
            engine = boolean.ExactBoolean(context, transaction)
            frame = addon.operators.Matrix.Identity(3)
            pocket = volume.extruded_volume(transaction, frame, Vector((0, 0, 4)),
                                           volume.outline("RECTANGLE", 18, 18), 24)
            body = engine.run(original.data, pocket, "DIFFERENCE")
            if vent_z is not None:
                vent = volume.extruded_volume(transaction, frame, Vector((10.5, 0, vent_z)),
                                             volume.outline("RECTANGLE", 7, 4), 5)
                body = engine.run(body, vent, "DIFFERENCE")
            result = transaction.object(context.scene.collection, "Cup fixture", body)
            transaction.publish(result)
        original.hide_set(True)
        context.view_layer.update()
        addon.operators.select_results(context, [result])
        return result

    def test_resin_suction_depends_on_layer_order_and_world_orientation(self):
        from mathutils import Euler

        part = self.resin_cup()
        part.location = (10, -4, 8)
        part.rotation_euler = Euler((0, .41, 0))
        bpy.context.view_layer.update()
        settings = bpy.context.scene.tntmesh_resin
        direction = part.rotation_euler.to_matrix() @ Vector((0, 0, 1))
        settings.print_axis = direction
        ui = self.addon.diagnostics_ui
        original = part.data
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        report = ui.current(bpy.context).result
        self.assertEqual(report.suction.count, 1)
        self.assertEqual(report.suction.uncertain_rows, 0)
        self.assertNotIn("CAVITY", {finding.kind for finding in report.findings})
        self.assertAlmostEqual(report.suction.pockets[0].area_mm2, 18**2, delta=25)
        point, _ = ui.current(bpy.context).marks["SUCTION"][0]
        local = part.matrix_world.inverted() @ point
        self.assertTrue(abs(local.x) < 9 and abs(local.y) < 9 and -8 < local.z < 12)
        settings.print_axis = -direction
        self.assertIsNone(ui.current(bpy.context))
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        self.assertEqual(ui.current(bpy.context).result.suction.count, 0)
        self.assertEqual(part.data, original)

    def test_resin_suction_distinguishes_an_early_vent_from_a_late_opening(self):
        late = self.resin_cup(vent_z=0)
        ui = self.addon.diagnostics_ui
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        pocket, = ui.current(bpy.context).result.suction.pockets
        self.assertLess(pocket.center.z, -2)
        self.assertNotIn("CAVITY", {item.kind for item in ui.current(bpy.context).result.findings})
        late.hide_set(True)
        self.resin_cup(vent_z=-8.5)
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        self.assertEqual(ui.current(bpy.context).result.suction.count, 0)

    def test_resin_trap_scan_detects_closed_cavity_and_handles_invalid_input(self):
        self.cube()
        self.assertEqual(bpy.ops.tntmesh.hollow_resin(), {"FINISHED"})
        ui = self.addon.diagnostics_ui
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        results = ui.current(bpy.context).result
        self.assertEqual({item.kind: item.count for item in results.findings if item.kind in {"CAVITY", "SUCTION"}},
                         {"CAVITY": 1, "SUCTION": 1})
        settings = bpy.context.scene.tntmesh_resin
        settings.print_axis = (0, 0, 0)
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"CANCELLED"})
        self.assertIsNone(ui.current(bpy.context))
        settings.print_axis = (0, 0, 1)
        bpy.ops.mesh.primitive_plane_add(size=24)
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        invalid = ui.current(bpy.context).result
        self.assertIsNone(invalid.suction)
        self.assertIn("OPEN", {item.kind for item in invalid.findings})

    def test_resin_suction_keeps_independent_cups_separate(self):
        first = self.resin_cup()
        second = self.resin_cup()
        first.location.x, second.location.x = -16, 16
        first.select_set(True)
        bpy.context.view_layer.update()
        bpy.ops.object.join()
        self.assertEqual(bpy.ops.tntmesh.check_resin(), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result.suction
        self.assertEqual(result.count, 2)
        self.assertEqual(len(result.pockets), 2)
        self.assertAlmostEqual(abs(result.pockets[0].center.x - result.pockets[1].center.x), 32, delta=.6)

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

    def test_manual_path_splits_a_solid_with_a_smoothed_seam(self):
        source = self.cube()
        self.settings.cut_kind = "PATH"
        self.settings.contour_depth = 30
        self.settings.path_smoothing = 1
        for point in ((-8, -3), (0, 5), (8, -1)):
            self.settings.contour.add().position = point
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        first, second = self.parts()
        self.assertAlmostEqual(self.checked(first) + self.checked(second), 24**3, delta=.025)
        self.assertTrue(any(abs(vertex.co.x) < .0001 and abs(vertex.co.y - 1.5) < .0001
                            for vertex in first.data.vertices))
        self.assertEqual(len(source.data.polygons), 6)

    def test_manual_path_rejects_a_crossing_and_supports_draft_point_removal(self):
        self.cube()
        self.settings.cut_kind = "PATH"
        self.settings.contour_depth = 30
        for point in ((-8, -8), (8, 8), (-8, 8), (8, -8)):
            self.settings.contour.add().position = point
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.settings.mode = "DRAFT"
        self.assertEqual(bpy.ops.tntmesh.remove_cut_point(point_index=1), {"FINISHED"})
        self.assertEqual(len(self.settings.contour), 4)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        self.assertAlmostEqual(sum(map(self.checked, self.parts())), 24**3, delta=.025)

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

    def test_connector_suggestion_resizes_and_uses_the_thicker_side_for_the_socket(self):
        source = self.cube()
        source.scale.x = 5.2 / 24
        source.location = (31, -14, 9)
        bpy.context.view_layer.update()
        self.settings.offset = 9.9
        self.settings.wall = .45
        self.settings.lateral = .12
        self.settings.axial = .23
        self.settings.diameter = 7
        original = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.suggest_connectors(), {"FINISHED"})
        self.assertEqual(set(bpy.data.meshes.keys()), original)
        self.assertTrue(self.settings.pin_positive)
        self.assertLess(self.settings.diameter, 5.2)
        self.assertGreaterEqual(self.settings.insertion, 1.8)
        self.assertAlmostEqual(self.settings.lateral, .12)
        self.assertAlmostEqual(self.settings.axial, .23)
        positions = [point.position[:] for point in self.settings.connector_points]
        self.assertTrue(positions)
        self.settings.connector_points[0].position = (500, 500)
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(set(bpy.data.meshes.keys()), original)
        self.assertFalse(source.hide_get())
        self.settings.connector_points[0].position = positions[0]
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        lower, upper = self.parts()
        self.assertGreater(upper.dimensions.z, 3.9)
        self.assertTrue(self.checked(lower) > self.checked(upper))
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_connector_suggestion_finds_multiple_positions_around_a_cavity(self):
        exterior = self.cube(40)
        interior = self.cube(27)
        interior.data.flip_normals()
        exterior.select_set(True)
        bpy.context.view_layer.objects.active = exterior
        bpy.ops.object.join()
        self.settings.loose_pins = True
        self.settings.kerf = .2
        self.assertEqual(bpy.ops.tntmesh.suggest_connectors(), {"FINISHED"})
        self.assertGreaterEqual(len(self.settings.connector_points), 2)
        self.assertEqual(self.settings.connector_count, len(self.settings.connector_points))
        self.assertTrue(all(max(map(abs, point.position)) > 13.5
                            for point in self.settings.connector_points))
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2 + self.settings.connector_count)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_connector_suggestion_for_dependent_draft_preserves_previous_outputs_on_failure(self):
        source = self.cube(36)
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        plan = self.addon.draft.active_plan(bpy.context.scene)
        operation = plan.cuts[1]
        operation.settings.axis = "X"
        self.settings.mode = "DRAFT"
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        prior = set(self.parts())
        meshes = set(bpy.data.meshes.keys())
        self.assertTrue(source.hide_get())
        operation.settings.wall = 30
        self.assertEqual(bpy.ops.tntmesh.suggest_connectors(), {"CANCELLED"})
        self.assertFalse(operation.settings.connector_points)
        self.assertEqual(set(self.parts()), prior)
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)
        self.assertTrue(source.hide_get())
        operation.settings.wall = 1
        self.assertEqual(bpy.ops.tntmesh.suggest_connectors(), {"FINISHED"})
        self.assertTrue(operation.settings.connector_points)
        self.assertFalse(self.settings.connector_points)
        self.assertEqual(set(self.parts()), prior)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 3)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_connector_patterns_validate_and_leave_the_current_layout_on_failure(self):
        source = self.cube(48)
        self.settings.connector = "HEX"
        self.settings.diameter = 4
        self.settings.loose_pins = True
        self.settings.kerf = .4
        self.assertEqual(bpy.ops.tntmesh.connector_pattern(pattern="CONTOUR", count=4, setback=5), {"FINISHED"})
        for item in self.settings.connector_points:
            self.assertAlmostEqual(max(map(abs, item.position)), 19)
        self.assertEqual(bpy.ops.tntmesh.connector_point(action="CLEAR"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.connector_pattern(pattern="LINE", count=3, spacing=8, angle=tau / 4),
                         {"FINISHED"})
        for point, y in zip(self.settings.connector_points, (-8, 0, 8), strict=True):
            self.assertAlmostEqual(point.position.x, 0, places=5)
            self.assertAlmostEqual(point.position.y, y, places=5)
        self.assertEqual(bpy.ops.tntmesh.connector_pattern(pattern="CIRCLE", count=4, spacing=8), {"FINISHED"})
        ring = [Vector(point.position) for point in self.settings.connector_points]
        self.assertTrue(all(abs((ring[i - 1] - point).length - 8) < .001 for i, point in enumerate(ring)))
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.connector_pattern(pattern="GRID", count=4, spacing=1), {"CANCELLED"})
        self.assertEqual([point.position[:] for point in self.settings.connector_points],
                         [tuple(point) for point in ring])
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)
        self.assertFalse(source.hide_get())
        self.assertEqual(bpy.ops.tntmesh.connector_pattern(pattern="GRID", count=4, spacing=8), {"FINISHED"})
        self.assertEqual({tuple(point.position) for point in self.settings.connector_points},
                         {(x, y) for x in (-4, 4) for y in (-4, 4)})
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 6)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_connector_layout_reflection_deduplicates_and_clipboard_round_trips(self):
        self.cube(48)
        self.settings.connector = "HEX"
        self.settings.pin_positive = True
        self.settings.diameter = 3
        self.settings.connector_points.add().position = (7, 5)
        for action in ("MIRROR_X", "MIRROR_X", "MIRROR_Y"):
            self.assertEqual(bpy.ops.tntmesh.connector_transfer(action=action), {"FINISHED"})
        points = tuple(tuple(item.position) for item in self.settings.connector_points)
        self.assertEqual(set(points), {(x, y) for x in (-7, 7) for y in (-5, 5)})
        self.assertEqual(len(points), 4)
        clipboard = importlib.import_module(f"{self.addon.__name__}.geometry.connector_clipboard")
        design = self.settings.standard_connector("HEX", 4)
        self.assertEqual(clipboard.decode(clipboard.encode(design, points, True)), (design, points, True))
        with self.assertRaises(self.addon.model.MeshError):
            clipboard.decode('{"tntmesh_connector":true}')
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_magnet_pockets_match_disc_dimensions_and_export_components(self):
        source = self.cube()
        self.settings.connector = "MAGNET"
        self.assertEqual(bpy.ops.tntmesh.magnet_library(action="PRESET", preset="DISC_6"), {"FINISHED"})
        self.settings.magnet_inset = .2
        self.settings.magnet_adhesive = .3
        self.settings.lateral = .1
        self.settings.kerf = .4
        for x in (-6, 6):
            self.settings.connector_points.add().position = (x, 0)
        expected_depth = 3.5
        path = self.directory / "magnets.txt"
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.export_magnet_report(filepath=str(path)), {"FINISHED"})
        text = path.read_text(encoding="utf-8")
        self.assertIn("Magnets required · 4", text)
        self.assertIn("Pocket depth · 3.50 mm", text)
        self.assertIn("Gap between installed faces · 0.80 mm", text)
        self.assertEqual(bpy.ops.tntmesh.export_magnet_report(filepath=str(path)), {"CANCELLED"})
        self.assertEqual(path.read_text(encoding="utf-8"), text)
        self.assertEqual(self.parts(), [])
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        self.assertFalse(source.hide_get())
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2)
        polygon_radius = 3.1 / cos(tau / 128)
        cavity_volume = 64 * sin(tau / 64) * polygon_radius**2 * expected_depth / 2
        for piece in self.parts():
            self.assertAlmostEqual(self.checked(piece), 24**2 * 11.8 - 2 * cavity_volume, delta=.003)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_magnet_library_edits_sizes_and_symmetric_cut_mirrors_block_pockets(self):
        source = self.cube(40)
        self.settings.cut_kind = "SYMMETRY"
        self.settings.connector = "MAGNET"
        self.settings.axis = "X"
        self.settings.offset = 9
        self.assertEqual(bpy.ops.tntmesh.magnet_library(action="PRESET", preset="BLOCK_8"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.magnet_library(action="SAVE"), {"FINISHED"})
        library = bpy.context.scene.tntmesh_magnet_library
        library[0].name = "Edited rectangular magnet"
        library[0].thickness = 2
        library[0].width = 7
        self.assertEqual(bpy.ops.tntmesh.magnet_library(action="USE"), {"FINISHED"})
        self.assertEqual(self.settings.magnet_shape, "BLOCK")
        self.assertEqual(self.settings.magnet_width, 7)
        self.assertEqual(self.settings.magnet_thickness, 2)
        self.settings.magnet_angle = .31
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.settings.mode = "DRAFT"
        path = self.directory / "symmetric magnets.txt"
        self.assertEqual(bpy.ops.tntmesh.export_magnet_report(filepath=str(path)), {"FINISHED"})
        self.assertIn("Magnets required · 4", path.read_text(encoding="utf-8"))
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        upper, middle, lower = self.parts()
        self.assertAlmostEqual(self.checked(upper), self.checked(lower), delta=.002)
        right = [vertex.co for vertex in middle.data.vertices if 5 < vertex.co.x < 8.9]
        left = [vertex.co for vertex in middle.data.vertices if -8.9 < vertex.co.x < -5]
        self.assertEqual(len(right), 4)
        self.assertEqual(sorted((round(-p.x, 4), round(p.y, 4), round(p.z, 4)) for p in right),
                         sorted(tuple(round(c, 4) for c in p) for p in left))
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))
        self.assertTrue(source.hide_get())

    def test_magnet_rejects_through_holes_without_exporting_or_publishing(self):
        source = self.cube(20)
        self.settings.connector = "MAGNET"
        self.settings.offset = 7.5
        self.settings.magnet_thickness = 3
        path = self.directory / "invalid magnets.txt"
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.export_magnet_report(filepath=str(path)), {"CANCELLED"})
        self.assertFalse(path.exists())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertEqual(self.parts(), [])
        self.assertFalse(source.hide_get())
        self.assertEqual(set(bpy.data.meshes.keys()), before)

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

    def test_fdm_estimate_uses_scene_units_and_invalidation(self):
        source = self.cube(1)
        units = bpy.context.scene.unit_settings
        units.system = "METRIC"
        units.scale_length = .01
        settings = bpy.context.scene.tntmesh_estimate
        settings.density = 1.25
        settings.price = 200
        settings.currency = "MXN"
        settings.wall_mm = .5
        settings.infill = 25
        settings.extra = 10
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.estimate_material(), {"FINISHED"})
        result = self.addon.estimate_ui.current(bpy.context)
        self.assertEqual(len(result.entries), 1)
        self.assertAlmostEqual(result.total.model_ml, 1)
        self.assertAlmostEqual(result.total.printed_ml, .475)
        self.assertAlmostEqual(result.total.extra_ml, .0475)
        self.assertAlmostEqual(result.total.grams, .653125)
        self.assertAlmostEqual(result.total.cost, .130625)
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)
        settings.infill = 100
        self.assertIsNone(self.addon.estimate_ui.current(bpy.context))
        self.assertEqual(bpy.ops.tntmesh.estimate_material(), {"FINISHED"})
        self.assertAlmostEqual(self.addon.estimate_ui.current(bpy.context).total.printed_ml, 1)
        source.scale.x = 2
        bpy.context.view_layer.update()
        self.assertIsNone(self.addon.estimate_ui.current(bpy.context))

    def test_resin_assembly_estimate_reports_per_piece_cost_and_cavity_savings(self):
        outside = self.cube(20)
        inside = self.cube(10)
        inside.data.flip_normals()
        outside.select_set(True)
        bpy.context.view_layer.objects.active = outside
        bpy.ops.object.join()
        pin = self.cube(10)
        pin.location.x = 27
        unrelated = self.cube(80)
        for piece in (outside, pin):
            self.addon.model.identify_part(piece, "estimate-fixture")
        bpy.context.scene.tntmesh_assembly.project = "estimate-fixture"
        pin.hide_set(True)
        self.assertEqual(bpy.ops.tntmesh.printer_add(preset="MARS5"), {"FINISHED"})
        printer = bpy.context.scene.tntmesh_printers[0]
        printer.density_g_cm3 = 1.25
        printer.price_per_kg = 200
        self.assertEqual(bpy.ops.tntmesh.use_estimate_profile(), {"FINISHED"})
        settings = bpy.context.scene.tntmesh_estimate
        self.assertEqual(settings.technology, "RESIN")
        settings.scope = "ASSEMBLY"
        settings.extra = 20
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.estimate_material(), {"FINISHED"})
        report = self.addon.estimate_ui.current(bpy.context)
        self.assertEqual({piece.name for piece in report.entries}, {outside.name, pin.name})
        self.assertNotIn(unrelated.name, {piece.name for piece in report.entries})
        self.assertAlmostEqual(report.total.model_ml, 8)
        self.assertAlmostEqual(report.total.printed_ml, 8)
        self.assertAlmostEqual(report.total.extra_ml, 1.6)
        self.assertAlmostEqual(report.total.grams, 12)
        self.assertAlmostEqual(report.total.cost, 2.4)
        self.assertAlmostEqual(report.total.saved_ml, 1)
        self.assertAlmostEqual(sum(piece.cost for piece in report.entries), report.total.cost)
        self.assertTrue(pin.hide_get())
        self.assertEqual(set(bpy.data.meshes.keys()), before)

    def test_estimate_rejects_an_open_mesh_and_clears_old_totals(self):
        self.cube()
        self.assertEqual(bpy.ops.tntmesh.estimate_material(), {"FINISHED"})
        bpy.ops.mesh.primitive_plane_add(size=5)
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.estimate_material(), {"CANCELLED"})
        self.assertIsNone(self.addon.estimate_ui.current(bpy.context))
        self.assertEqual(set(bpy.data.meshes.keys()), before)

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

    def test_region_smoothing_builds_a_smaller_closed_cut_on_the_original_surface(self):
        source = self.cube()
        mesh = source.data
        for face in mesh.polygons:
            face.select = face.normal.z > .9
        mesh.update()
        before = [vertex.co.copy() for vertex in mesh.vertices]
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "SELECTION"
        self.settings.region_depth = 2
        self.settings.region_smoothing = 2
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        remainder, extract = self.parts()
        self.assertLess(extract.dimensions.x, 23)
        self.assertLess(extract.dimensions.y, 23)
        self.assertAlmostEqual(extract.dimensions.z, 2)
        self.assertAlmostEqual(self.checked(remainder) + self.checked(extract), 24**3, places=3)
        self.assertEqual([vertex.co for vertex in mesh.vertices], before)

    def test_region_connectors_fit_both_parts_and_respect_shell_depth(self):
        source = self.cube()
        for face in source.data.polygons:
            face.select = face.normal.z > .9
        source.data.update()
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "SELECTION"
        self.settings.region_depth = 1
        self.settings.region_connector = "HEX"
        self.settings.connector_count = 2
        self.settings.loose_pins = True
        self.settings.insertion = 1.5
        self.settings.diameter = 3
        self.settings.axial = .2
        self.settings.wall = .5
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertFalse(source.hide_get())
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        self.assertEqual(self.parts(), [])

        self.settings.region_depth = 4
        self.settings.region_smoothing = 1
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        body, patch, *pins = self.parts()
        self.assertEqual(len(pins), 2)
        self.checked(body)
        self.checked(patch)
        for pin in pins:
            self.assertAlmostEqual(pin.dimensions.z, 3, places=5)
            self.assertAlmostEqual(self.checked(pin), 6 * sin(tau / 6) * 1.5**2 * 3 / 2, places=4)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, self.parts()))

    def test_region_extraction_cleans_degenerate_edges_on_a_spherical_seam(self):
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=20)
        source = bpy.context.active_object
        volume = self.checked(source)
        original = [tuple(vertex.co) for vertex in source.data.vertices]
        for face in source.data.polygons:
            face.select = face.center.z > 15
        source.data.update()
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "SELECTION"
        self.settings.region_depth = 6.135
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        self.assertEqual(len(self.parts()), 2)
        self.assertAlmostEqual(sum(map(self.checked, self.parts())), volume, delta=volume * .0001)
        self.assertEqual([tuple(vertex.co) for vertex in source.data.vertices], original)

    def test_region_connector_can_join_a_curved_shell_patch(self):
        profile = [(-12, -8), (12, -8), (12, 0), (6, 3), (0, 4), (-6, 3), (-12, 0)]
        count = len(profile)
        vertices = [(x, y, z) for y in (10, -10) for x, z in profile]
        faces = [tuple(reversed(range(count))), tuple(range(count, 2 * count))]
        faces.extend((i, (i + 1) % count, (i + 1) % count + count, i + count) for i in range(count))
        original = bpy.data.meshes.new("Cambered shell")
        original.from_pydata(vertices, [], faces)
        original.update()
        source = bpy.data.objects.new(original.name, original)
        bpy.context.collection.objects.link(source)
        bpy.context.view_layer.objects.active = source
        for face in original.polygons:
            face.select = face.normal.z > .5
        original.update()
        self.settings.cut_kind = "REGION"
        self.settings.region_method = "SELECTION"
        self.settings.region_depth = 4.3
        self.settings.region_connector = "HEX"
        self.settings.diameter = 7
        self.settings.insertion = 1.4
        self.settings.wall = .45
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        remainder, patch = self.parts()
        self.assertGreater(self.checked(remainder), 3050)
        self.assertLess(self.checked(patch), 1990)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, [remainder, patch]))
        self.assertEqual(source.data, original)
        self.assertEqual(len(original.vertices), 14)
        source.hide_set(False)
        self.addon.operators.select_results(bpy.context, [source])
        self.settings.region_connector = "TONGUE"
        self.settings.connector_width, self.settings.connector_height = 7, 4
        self.settings.connector_angle = .23
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        shaped = list(bpy.context.selected_objects)
        self.assertEqual(len(shaped), 2)
        for part in shaped:
            self.checked(part)
        self.assertEqual(self.addon.assembly.overlaps(bpy.context, shaped), [])

    def test_diagnostics_report_open_edges_without_changing_the_mesh(self):
        bpy.ops.mesh.primitive_plane_add(size=20)
        obj = bpy.context.active_object
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        ui = self.addon.diagnostics_ui
        result = ui.current(bpy.context).result
        self.assertEqual({item.kind: item.count for item in result.findings}, {"OPEN": 4})
        self.assertIsNone(result.volume_mm3)
        self.assertEqual(bpy.ops.tntmesh.diagnostic_view(kind="OPEN"), {"FINISHED"})
        self.assertEqual(ui.current(bpy.context).kind, "OPEN")
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        obj.location.x += 2
        bpy.context.view_layer.update()
        self.assertIsNone(ui.current(bpy.context))

    def test_diagnostics_separates_intersections_from_legitimate_nested_shells(self):
        outer = self.cube(12)
        inner = self.cube(4)
        inner.data.flip_normals()
        outer.select_set(True)
        bpy.context.view_layer.objects.active = outer
        bpy.ops.object.join()
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result
        self.assertEqual({item.kind: item.count for item in result.findings},
                         {"SHELLS": 2, "CAVITY": 1})
        self.assertAlmostEqual(result.volume_mm3, 12**3 - 4**3, places=3)
        crossing = self.cube(5)
        crossing.location = (5, 1.25, 1.5)
        outer.select_set(True)
        bpy.context.view_layer.objects.active = outer
        bpy.ops.object.join()
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result
        counts = {item.kind: item.count for item in result.findings}
        self.assertGreater(counts["INTERSECTION"], 0)
        self.assertEqual(counts["SHELLS"], 3)
        self.assertTrue(result.checked_intersections)
        self.assertEqual(bpy.ops.tntmesh.diagnose(intersections=False), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result
        self.assertFalse(result.checked_intersections)
        self.assertNotIn("INTERSECTION", {item.kind for item in result.findings})
        self.assertNotIn("CAVITY", {item.kind for item in result.findings})

    def test_diagnostics_reports_inverted_exterior_and_miswound_internal_shell(self):
        outer = self.cube(12)
        inner = self.cube(4)
        distant = self.cube(3)
        distant.location.x = 10
        distant.data.flip_normals()
        inner.select_set(True)
        outer.select_set(True)
        bpy.context.view_layer.objects.active = outer
        bpy.ops.object.join()
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result
        findings = {item.kind: item.count for item in result.findings}
        self.assertEqual(findings, {"SHELLS": 3, "INTERNAL": 1, "INVERTED": 1})

    def test_diagnostics_marks_hollow_walls_with_a_measured_thickness(self):
        outer = self.cube(10)
        inner = self.cube(8.8)
        inner.data.flip_normals()
        outer.select_set(True)
        bpy.context.view_layer.objects.active = outer
        bpy.ops.object.join()
        geometry = self.addon.diagnostics_ui
        self.assertEqual(bpy.ops.tntmesh.diagnose(wall_mm=.55), {"FINISHED"})
        report = geometry.current(bpy.context).result
        self.assertTrue(report.checked_walls)
        self.assertIsNone(report.thinnest_wall_mm)
        self.assertEqual(bpy.ops.tntmesh.diagnose(wall_mm=.8), {"FINISHED"})
        preview = geometry.current(bpy.context)
        thin, = (finding for finding in preview.result.findings if finding.kind == "THIN_WALL")
        self.assertEqual(thin.count, 12)
        self.assertAlmostEqual(preview.result.thinnest_wall_mm, .6, places=5)
        for first, second in preview.marks["THIN_WALL"]:
            self.assertAlmostEqual((first - second).length, .6, places=5)
        self.assertEqual(bpy.ops.tntmesh.diagnostic_view(kind="THIN_WALL"), {"FINISHED"})
        self.assertEqual(preview.kind, "THIN_WALL")

    def test_diagnostics_reports_when_thickness_cannot_be_measured_on_an_open_sheet(self):
        bpy.ops.mesh.primitive_plane_add(size=5)
        self.assertEqual(bpy.ops.tntmesh.diagnose(wall_mm=1), {"FINISHED"})
        report = self.addon.diagnostics_ui.current(bpy.context).result
        self.assertEqual(report.wall_limit_mm, 1)
        self.assertFalse(report.checked_walls)
        self.assertIsNone(report.thinnest_wall_mm)
        self.assertNotIn("THIN_WALL", {finding.kind for finding in report.findings})

    def test_wall_map_distinguishes_wall_thickness_and_clears_when_the_model_changes(self):
        outer = self.cube(10)
        inner = self.cube(8)
        inner.location.x = .6
        inner.data.flip_normals()
        outer.select_set(True)
        bpy.context.view_layer.objects.active = outer
        bpy.ops.object.join()
        data = outer.data
        ui = self.addon.diagnostics_ui
        self.assertEqual(bpy.ops.tntmesh.diagnose(wall_mm=1, wall_map=True), {"FINISHED"})
        preview = ui.current(bpy.context)
        self.assertEqual(len(preview.result.wall_map_mm), len(data.loop_triangles))
        self.assertAlmostEqual(preview.overlay.limits[0], .4, places=5)
        self.assertAlmostEqual(preview.overlay.limits[1], 1.6, places=5)
        values = preview.result.wall_map_mm
        palette = preview.overlay.colors[::3]
        self.assertTrue(all(palette[index, 0] > palette[index, 2] for index, mm in enumerate(values) if 0 < mm < .5))
        self.assertTrue(all(palette[index, 0] < palette[index, 2] for index, mm in enumerate(values) if mm > 1.5))
        self.assertEqual(bpy.ops.tntmesh.diagnostic_view(kind="MAP"), {"FINISHED"})
        self.assertFalse(preview.show_wall_map)
        self.assertEqual(bpy.ops.tntmesh.diagnostic_view(kind="MAP"), {"FINISHED"})
        self.assertTrue(preview.show_wall_map)
        self.assertEqual(outer.data, data)
        outer.location.y += 1
        bpy.context.view_layer.update()
        self.assertIsNone(ui.current(bpy.context))

    def test_wall_map_detects_the_thin_strip_between_socket_and_exterior(self):
        from mathutils import Matrix

        addon, context = self.addon, bpy.context
        boolean = importlib.import_module(f"{addon.__name__}.geometry.boolean")
        connector = importlib.import_module(f"{addon.__name__}.geometry.connector")
        source = self.cube()
        with addon.operators.GeometryTransaction() as transaction:
            cutter = connector.prism(transaction, Matrix.Identity(3), Vector((9.5, 0)), 5, 13, 2, 32)
            mesh = boolean.ExactBoolean(context, transaction).run(source.data, cutter, "DIFFERENCE")
            socket = transaction.object(context.scene.collection, "Thin socket wall", mesh)
            transaction.publish(socket)
        context.view_layer.update()
        addon.operators.select_results(context, [socket])
        self.assertEqual(bpy.ops.tntmesh.diagnose(wall_mm=.75, wall_map=True), {"FINISHED"})
        preview = addon.diagnostics_ui.current(context)
        self.assertTrue(preview.result.checked_walls)
        self.assertAlmostEqual(preview.overlay.limits[0], .5, delta=.1)
        self.assertTrue(any(11.2 < start.x < 11.6 and abs(end.x - 12) < 1e-4
                            for start, end in preview.marks["THIN_WALL"]))

    def test_diagnostics_finds_coplanar_pairs_across_spatial_tree_branches(self):
        vertices = []
        faces = []
        for block in range(11):
            base = len(vertices)
            x = block * 8
            vertices.extend(((x, 0, 0), (x + 4, 0, 0), (x, 4, 0),
                             (x + 1, 1, 0), (x + 5, 1, 0), (x + 1, 5, 0)))
            faces.extend(((base, base + 1, base + 2), (base + 3, base + 4, base + 5)))
        mesh = bpy.data.meshes.new("Disconnected overlapping triangles")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        geometry = importlib.import_module(f"{self.addon.__name__}.geometry.diagnostics")
        report = geometry.scan(mesh, 0, 0, intersections=True)
        self.assertEqual(next(item.count for item in report.findings if item.kind == "COPLANAR"), 22)

    def test_diagnostics_find_duplicate_faces_and_nearby_vertices(self):
        bpy.ops.mesh.primitive_plane_add(size=5)
        first = bpy.context.active_object
        bpy.ops.mesh.primitive_plane_add(size=5)
        first.select_set(True)
        bpy.context.view_layer.objects.active = first
        bpy.ops.object.join()
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result
        counts = {item.kind: item.count for item in result.findings}
        self.assertEqual(counts["DUP_FACE"], 1)
        self.assertEqual(counts["DUP_VERT"], 8)
        self.assertEqual(counts["OPEN"], 8)
        self.assertEqual(counts["COPLANAR"], 2)

    def test_diagnostics_detect_partial_coplanar_overlap_and_ignores_edge_contact(self):
        mesh = bpy.data.meshes.new("Coplanar triangles")
        points = [(0, 0, 0), (4, 0, 0), (0, 4, 0), (2, 1, 0), (5, 1, 0), (2, 3, 0),
                  (4, 0, 0), (4, -1, 0), (0, 0, 0)]
        mesh.from_pydata(points, [], [(0, 1, 2), (3, 4, 5), (6, 7, 8)])
        mesh.update()
        obj = bpy.data.objects.new("Overlapping faces", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.rotation_euler = (.4, .9, .7)
        bpy.context.view_layer.update()
        self.addon.operators.select_results(bpy.context, [obj])
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        result = self.addon.diagnostics_ui.current(bpy.context).result
        counts = {item.kind: item.count for item in result.findings}
        self.assertEqual(counts["COPLANAR"], 2)

    def test_material_batch_separates_multiple_solid_regions_atomically(self):
        source = self.cube()
        mesh = source.data
        for name, color in (("Body", (.2, .2, .2, 1)), ("Green", (0, 1, 0, 1)),
                            ("Red", (1, 0, 0, 1))):
            mat = bpy.data.materials.new(name)
            mat.diffuse_color = color
            mesh.materials.append(mat)
        max(mesh.polygons, key=lambda face: face.normal.z).material_index = 1
        max(mesh.polygons, key=lambda face: face.normal.x).material_index = 2
        mesh.update()
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split_materials(keep_slot=4), {"CANCELLED"})
        self.assertEqual(bpy.ops.tntmesh.split_materials(depth=30), {"CANCELLED"})
        self.assertEqual(self.parts(), [])
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        self.assertFalse(source.hide_get())
        self.assertEqual(bpy.ops.tntmesh.split_materials(depth=2), {"FINISHED"})
        parts = self.parts()
        self.assertEqual([obj["tntmesh_material_slot"] for obj in parts], [1, 2, 3])
        self.assertEqual([tuple(obj.color) for obj in parts[1:]], [(0, 1, 0, 1), (1, 0, 0, 1)])
        self.assertAlmostEqual(sum(self.checked(obj) for obj in parts), 24**3, places=3)
        self.assertAlmostEqual(self.checked(parts[1]), 24 * 24 * 2, places=3)
        self.assertAlmostEqual(self.checked(parts[2]), 22 * 24 * 2, places=3)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, parts))

    def test_material_batch_connects_each_region_to_the_final_body(self):
        source = self.cube()
        mesh = source.data
        for name in ("Body", "Green", "Red"):
            mesh.materials.append(bpy.data.materials.new(name))
        max(mesh.polygons, key=lambda face: face.normal.z).material_index = 1
        max(mesh.polygons, key=lambda face: face.normal.x).material_index = 2
        mesh.update()
        self.settings.region_connector = "ROUND"
        self.settings.diameter = 4
        self.settings.insertion = 1.5
        self.settings.wall = .5
        self.settings.loose_pins = True
        self.assertEqual(
            bpy.ops.tntmesh.split_materials(depth=4, with_connectors=True), {"FINISHED"},
        )
        parts = self.parts()
        pins = [obj for obj in parts if "Pin " in obj.name]
        self.assertEqual({obj["tntmesh_material_slot"] for obj in pins}, {2, 3})
        self.assertEqual(len(parts), 5)
        for pin in pins:
            self.assertAlmostEqual(self.checked(pin), 64 * sin(tau / 64) * 2**2 * 3 / 2, places=3)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, parts))

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

    def test_symmetric_cuts_reflect_asymmetric_templates_without_editing_them(self):
        source = self.cube(48)
        pin = self.cube(3)
        socket = self.cube(3.6)
        for template in (pin, socket):
            for vertex in template.data.vertices:
                vertex.co.x += .35 * vertex.co.z
            template.data.update()
        originals = [[vertex.co.copy() for vertex in template.data.vertices] for template in (pin, socket)]
        self.addon.operators.select_results(bpy.context, [source])
        self.settings.cut_kind = "SYMMETRY"
        self.settings.axis = "X"
        self.settings.offset = 10
        self.settings.connector = "CUSTOM"
        self.settings.pin_template = pin
        self.settings.socket_template = socket
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        first, central, second = self.parts()
        outward = [vertex.co for vertex in central.data.vertices if vertex.co.x > 10.01]
        reflected = [vertex.co for vertex in central.data.vertices if vertex.co.x < -10.01]
        self.assertGreaterEqual(len(outward), 4)
        self.assertEqual(sorted(tuple(round(co, 4) for co in point) for point in outward),
                         sorted((round(-point.x, 4), round(point.y, 4), round(point.z, 4))
                                for point in reflected))
        self.assertAlmostEqual(self.checked(first), self.checked(second), delta=.001)
        self.assertFalse(self.addon.assembly.overlaps(bpy.context, [first, central, second]))
        for template, original in zip((pin, socket), originals, strict=True):
            self.assertEqual([vertex.co for vertex in template.data.vertices], original)

    def test_base_analysis_and_cut_keep_two_different_contact_elevations(self):
        source = stepped_base_fixture(self.addon)
        self.settings.cut_kind = "BASE"
        self.settings.base_band = 7
        base_geometry = importlib.import_module(f"{self.addon.__name__}.geometry.base")
        analysis = base_geometry.analyze_base(source.data, self.settings.base_config())
        self.assertEqual(len(analysis.contacts), 2)
        self.assertEqual([round(item.center.z, 5) for item in analysis.contacts], [3, 5])
        self.assertEqual([round(item.area, 5) for item in analysis.contacts], [36, 36])
        before = self.checked(source)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        base, figure = self.parts()
        self.assertAlmostEqual(self.checked(base), 40 * 24 * 3 + 10 * 10 * 2, places=2)
        self.assertAlmostEqual(self.checked(base) + self.checked(figure), before, places=2)

    def test_base_without_contacts_has_no_published_results(self):
        source = self.cube()
        self.settings.cut_kind = "BASE"
        before = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.split(), {"CANCELLED"})
        self.assertFalse(source.hide_get())
        self.assertEqual(set(bpy.data.meshes.keys()), before)
        self.assertEqual(self.parts(), [])

    def test_base_with_one_contact_uses_the_automatic_search_height(self):
        stepped_base_fixture(self.addon, single=True)
        self.settings.cut_kind = "BASE"
        self.assertEqual(bpy.ops.tntmesh.find_base_contacts(), {"FINISHED"})
        self.assertEqual(len(self.settings.base_contacts), 1)
        self.assertAlmostEqual(self.settings.base_contacts[0].height, 3)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        base, figure = self.parts()
        self.assertAlmostEqual(self.checked(base), 40 * 24 * 3)
        self.assertAlmostEqual(self.checked(figure), 6 * 6 * 18)

    def test_base_contact_cut_follows_inclined_support_surfaces(self):
        source = stepped_base_fixture(self.addon)
        deform = self.addon.operators.Matrix.Identity(4)
        deform[2][0] = .05
        source.data.transform(deform)
        source.data.update()
        self.settings.cut_kind = "BASE"
        self.settings.base_band = 8
        self.assertEqual(bpy.ops.tntmesh.find_base_contacts(), {"FINISHED"})
        self.assertEqual(len(self.settings.base_contacts), 2)
        before = self.checked(source)
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        base, figure = self.parts()
        self.assertAlmostEqual(self.checked(base), 40 * 24 * 3 + 10 * 10 * 2, places=2)
        self.assertAlmostEqual(self.checked(base) + self.checked(figure), before, places=2)

    def test_base_contact_connector_overrides_are_used_in_a_draft(self):
        source = stepped_base_fixture(self.addon)
        self.settings.cut_kind = "BASE"
        self.settings.base_band = 7
        self.settings.base_pins = True
        self.settings.loose_pins = True
        self.settings.base_shape = "HEX"
        self.settings.insertion = 1.2
        self.settings.diameter = 2
        self.settings.wall = .5
        self.assertEqual(bpy.ops.tntmesh.find_base_contacts(), {"FINISHED"})
        self.assertEqual(len(self.settings.base_contacts), 2)
        self.settings.base_contacts[0].connector = False
        self.settings.base_contacts[1].diameter = 3
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        base, figure, pin = self.parts()
        self.assertAlmostEqual(pin.dimensions.x, 3, places=5)
        self.assertAlmostEqual(pin.location.x + sum(v.co.x for v in pin.data.vertices) /
                               len(pin.data.vertices), 10, places=5)
        self.checked(base)
        self.checked(figure)
        self.checked(pin)
        self.assertTrue(source.hide_get())

    def test_base_contact_uses_profile_width_and_keeps_the_oval_height(self):
        stepped_base_fixture(self.addon)
        self.settings.cut_kind = "BASE"
        self.settings.base_band = 7
        self.settings.base_pins = self.settings.loose_pins = True
        self.settings.base_shape = "OVAL"
        self.settings.connector_width, self.settings.connector_height = 2, 1.5
        self.settings.insertion, self.settings.wall = 1.2, .5
        self.assertEqual(bpy.ops.tntmesh.find_base_contacts(), {"FINISHED"})
        self.settings.base_contacts[0].connector = False
        self.settings.base_contacts[1].diameter = 3
        self.assertEqual(bpy.ops.tntmesh.split(), {"FINISHED"})
        base, figure, pin = self.parts()
        self.assertAlmostEqual(pin.dimensions.x, 3, places=5)
        self.assertAlmostEqual(pin.dimensions.y, 1.5, places=5)
        self.assertEqual(self.addon.assembly.overlaps(bpy.context, [base, figure, pin]), [])

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

    def test_symmetric_draft_rotates_only_the_second_cut_and_preserves_the_last_good_build(self):
        source = self.cube(48)
        source.location = (53, -29, 14)
        self.settings.cut_kind = "SYMMETRY"
        self.settings.axis = "X"
        self.settings.offset = 10
        self.settings.symmetry_rotation = (0, .18, 0)
        self.settings.connector = "NONE"
        self.assertEqual(bpy.ops.tntmesh.draft_create(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.draft_action(action="ADD"), {"FINISHED"})
        cut = self.addon.draft.active_plan(bpy.context.scene).cuts[0]
        self.assertAlmostEqual(cut.settings.symmetry_rotation[1], .18)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"FINISHED"})
        outer, center, opposite = self.parts()
        self.assertAlmostEqual(outer.dimensions.x, 14)
        self.assertGreater(opposite.dimensions.x, 17)
        self.assertTrue(any(abs(face.normal.x) > .9 and .17 < abs(face.normal.y) < .19
                            for face in opposite.data.polygons))
        self.assertAlmostEqual(sum(map(self.checked, (outer, center, opposite))), 48**3, delta=.02)
        cut.settings.symmetry_rotation = (0, 1.2, 0)
        self.assertEqual(bpy.ops.tntmesh.draft_build(), {"CANCELLED"})
        self.assertEqual(self.parts(), [outer, center, opposite])

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

    def test_insertion_path_detects_an_obstruction_between_clear_endpoints(self):
        moving = self.cube(2)
        blocker = self.cube(2)
        blocker.location.x = 5
        off_path = self.cube(3)
        off_path.location = (5, 4, 0)
        bpy.context.view_layer.update()
        parts = [moving, blocker, off_path]
        for obj in parts:
            self.addon.operators.identify_part(obj, "insertion-fixture")
        self.addon.operators.select_results(bpy.context, [moving])
        self.assertEqual(bpy.ops.tntmesh.assembly_project(), {"FINISHED"})
        assembly = self.addon.assembly
        transforms = {obj: obj.matrix_world.copy() for obj in parts}
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(assembly.overlaps(bpy.context, parts), [])
        hit = assembly.insertion_hit(bpy.context, moving, parts, Vector((1, 0, 0)), 10)
        self.assertEqual(hit.obstacle, blocker)
        self.assertGreater(hit.distance_mm, 5)
        self.assertLess(hit.distance_mm, 7)
        self.assertGreater(hit.volume_mm3, 0)
        self.assertIsNone(assembly.insertion_hit(bpy.context, moving, parts, Vector((-1, 0, 0)), 10, 2))
        self.assertEqual(bpy.ops.tntmesh.check_insertion(axis="+X", distance=10, steps=2), {"FINISHED"})
        self.assertEqual({obj: obj.matrix_world for obj in parts}, transforms)
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)

    def test_insertion_search_finds_a_thin_diagonal_obstacle_and_ignores_tangent_contact(self):
        direction = Vector((3, 4, 0)).normalized()
        moving = self.cube(.35)
        thin = self.cube(.22)
        thin.location = direction * 6.321
        thin.rotation_euler.z = .61
        tangent = self.cube(1)
        tangent.location = direction * 9
        tangent.location.z = (.35 + 1) / 2
        bpy.context.view_layer.update()
        assembly = self.addon.assembly
        self.assertIsNone(assembly.insertion_hit(bpy.context, moving, [tangent], direction, 20))
        hit = assembly.insertion_hit(bpy.context, moving, [thin, tangent], direction, 20)
        self.assertEqual(hit.obstacle, thin)
        self.assertGreater(hit.distance_mm, 6.321)
        self.assertLess(hit.distance_mm, 6.8)
        nearer_start = self.cube(.22)
        nearer_start.location = direction * 12.11
        bpy.context.view_layer.update()
        first = assembly.insertion_hit(bpy.context, moving, [thin, nearer_start], direction, 20)
        self.assertEqual(first.obstacle, nearer_start)
        self.assertEqual(assembly.insertion_hit(bpy.context, moving, [nearer_start, thin], direction, 20), first)

    def test_insertion_rotation_finds_a_blocker_between_clear_end_poses(self):
        moving = self.cube(2)
        moving.scale = (5, .35, .5)
        blocker = self.cube(.4)
        blocker.location = (3.2, 3.2, 0)
        for obj in (moving, blocker):
            self.addon.operators.identify_part(obj, "rotating-insertion-test")
        context = bpy.context
        context.view_layer.update()
        transforms = {obj: obj.matrix_world.copy() for obj in (moving, blocker)}
        datablocks = tuple(bpy.data.meshes.keys())
        assembly = self.addon.assembly
        self.assertEqual(assembly.overlaps(context, [moving, blocker]), [])
        axis, direction = Vector((0, 0, 1)), Vector((0, 0, 0))
        hit = assembly.insertion_hit(context, moving, [blocker], direction, 0,
                                     rotation_axis=axis, rotation_radians=pi / 2)
        self.assertEqual(hit.obstacle, blocker)
        self.assertAlmostEqual(hit.rotation_radians, pi / 4, delta=.2)
        self.assertEqual(hit.distance_mm, 0)
        self.assertIsNone(assembly.insertion_hit(context, moving, [blocker], direction, 0,
                                                 rotation_axis=axis, rotation_radians=-pi / 2))
        self.addon.operators.select_results(context, [moving])
        self.assertEqual(bpy.ops.tntmesh.assembly_project(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.check_insertion(distance=0, rotation=pi / 2), {"FINISHED"})
        self.assertEqual({obj: obj.matrix_world for obj in transforms}, transforms)
        self.assertEqual(tuple(bpy.data.meshes.keys()), datablocks)

    def test_insertion_with_rotation_and_translation_uses_the_world_pivot_in_scene_units(self):
        context = bpy.context
        context.scene.unit_settings.system = "METRIC"
        context.scene.unit_settings.scale_length = .01
        pivot = Vector((1, 2, 3))
        moving = self.cube(.1)
        moving.location = pivot + Vector((4, 0, 0))
        blocker = self.cube(.1)
        blocker.location = pivot + Vector((2 * sqrt(2), 2 * sqrt(2), 2))
        context.view_layer.update()
        assembly = self.addon.assembly
        axis = Vector((0, 0, 1))
        self.assertIsNone(assembly.insertion_hit(context, moving, [blocker], axis, 40))
        self.assertIsNone(assembly.insertion_hit(context, moving, [blocker], axis, 0,
                                                 rotation_axis=axis, rotation_radians=pi / 2, pivot_world=pivot))
        hit = assembly.insertion_hit(context, moving, [blocker], axis, 40, rotation_axis=axis,
                                     rotation_radians=pi / 2, pivot_world=pivot)
        self.assertEqual(hit.obstacle, blocker)
        self.assertAlmostEqual(hit.distance_mm, 20, delta=2)
        self.assertAlmostEqual(hit.rotation_radians, pi / 4, delta=.06)
        context.scene.cursor.location = pivot
        for obj in (moving, blocker):
            self.addon.operators.identify_part(obj, "translating-rotation-test")
        self.addon.operators.select_results(context, [moving])
        self.assertEqual(bpy.ops.tntmesh.assembly_project(), {"FINISHED"})
        self.assertEqual(bpy.ops.tntmesh.check_insertion(axis="+Z", distance=40, rotation=pi / 2,
                                                        rotation_pivot="CURSOR"), {"FINISHED"})

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

    def test_repair_corrects_mixed_winding_and_preserves_nested_cavities(self):
        source = self.cube(24)
        cavity = self.cube(12)
        cavity.data.flip_normals()
        island = self.cube(4)
        island.data.flip_normals()
        other = self.cube(3)
        other.location.x = 19
        other.data.flip_normals()
        for obj in (source, cavity, island, other):
            obj.select_set(True)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.join()
        bm = bmesh.new()
        try:
            bm.from_mesh(source.data)
            face = next(face for face in bm.faces if face.calc_center_median().x < -11)
            bmesh.ops.reverse_faces(bm, faces=[face])
            bm.to_mesh(source.data)
        finally:
            bm.free()
        source.data.update()
        original = [tuple(face.vertices) for face in source.data.polygons]
        self.assertEqual(bpy.ops.tntmesh.repair(), {"CANCELLED"})
        self.settings.repair_orientation = True
        self.assertEqual(bpy.ops.tntmesh.repair(), {"FINISHED"})
        result = bpy.context.active_object
        self.assertNotEqual(source.data, result.data)
        self.assertEqual([tuple(face.vertices) for face in source.data.polygons], original)
        self.assertAlmostEqual(self.checked(result, shells=4), 24**3 - 12**3 + 4**3 + 3**3, places=3)
        self.assertEqual(bpy.ops.tntmesh.diagnose(), {"FINISHED"})
        findings = {item.kind: item.count for item in self.addon.diagnostics_ui.current(bpy.context).result.findings}
        self.assertEqual(findings, {"SHELLS": 4, "CAVITY": 1})

    def test_repair_rejects_intersecting_shells_without_publishing_a_copy(self):
        source = self.cube(20)
        other = self.cube(9)
        other.location.x = 8
        other.rotation_euler.z = .2
        source.select_set(True)
        bpy.context.view_layer.objects.active = source
        bpy.ops.object.join()
        self.settings.repair_orientation = True
        objects = set(bpy.data.objects.keys())
        meshes = set(bpy.data.meshes.keys())
        self.assertEqual(bpy.ops.tntmesh.repair(), {"CANCELLED"})
        self.assertEqual(set(bpy.data.objects.keys()), objects)
        self.assertEqual(set(bpy.data.meshes.keys()), meshes)
        self.assertFalse(source.hide_get())

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
