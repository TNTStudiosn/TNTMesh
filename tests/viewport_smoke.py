# SPDX-License-Identifier: GPL-3.0-or-later
"""Run with a graphical Blender process and an isolated user configuration."""
import os
import sys
import traceback
from pathlib import Path

import addon_utils
import bpy
from mathutils import Euler

output = Path(os.environ["TNTMESH_SMOKE_OUTPUT"])
output.mkdir(parents=True, exist_ok=True)
PACKAGE = os.environ.get("TNTMESH_TEST_PACKAGE", "tntmesh")
if PACKAGE == "tntmesh":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def viewport():
    window = bpy.context.window_manager.windows[0]
    area = next(area for area in window.screen.areas if area.type == "VIEW_3D")
    region = next(region for region in area.regions if region.type == "WINDOW")
    return window, area, region


def panel():
    _, area, _ = viewport()
    region = next(region for region in area.regions if region.type == "UI")
    region.active_panel_category = "TNTMesh"
    area.tag_redraw()


def setup():
    if addon_utils.enable(PACKAGE, default_set=True) is None:
        raise RuntimeError("Could not enable TNTMesh")
    window, area, region = viewport()
    bpy.context.preferences.filepaths.temporary_directory = str(output)
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()
        bpy.context.scene.unit_settings.system = "NONE"
        bpy.ops.mesh.primitive_cube_add(size=24)
        bpy.context.object.name = "TNTMesh Sample"
        bpy.ops.ed.undo_push(message="TNTMesh smoke baseline")
    view = area.spaces.active
    view.show_region_ui = True
    view.region_3d.view_distance = 75
    view.region_3d.view_rotation = Euler((1.0, 0, 0.55), "XYZ").to_quaternion()
    view.overlay.show_floor = False


def screenshot(name):
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.screen.screenshot(filepath=str(output / name)) == {"FINISHED"}


def pieces():
    return [obj for obj in bpy.context.scene.objects if obj.get("tntmesh_role") == "part"]


def split():
    screenshot("01-preview.png")
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.split() == {"FINISHED"}
        bpy.ops.ed.undo_push(message="TNTMesh smoke result")
    assert len(pieces()) == 2


def undo():
    screenshot("02-split.png")
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.ed.undo() == {"FINISHED"}


def redo():
    assert not pieces()
    assert not bpy.context.scene.objects["TNTMesh Sample"].hide_get()
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.ed.redo() == {"FINISHED"}


def spanish():
    assert len(pieces()) == 2
    bpy.context.preferences.view.language = "es"
    bpy.context.preferences.view.use_translate_interface = True
    translate = bpy.app.translations.pgettext_iface
    assert translate("Split Model", bpy.app.translations.contexts.operator_default) == "Dividir modelo"


def draft_panel():
    if not hasattr(bpy.types.Scene, "tntmesh_drafts"):
        return
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        settings = bpy.context.scene.tntmesh_settings
        settings.mode = "DRAFT"
        settings.connector = "NONE"
        assert bpy.ops.tntmesh.draft_create() == {"FINISHED"}
        assert bpy.ops.tntmesh.draft_action(action="ADD") == {"FINISHED"}
        assert bpy.ops.tntmesh.draft_action(action="ADD") == {"FINISHED"}
    area.tag_redraw()


def finish():
    if hasattr(bpy.types.Scene, "tntmesh_drafts"):
        screenshot("04-draft.png")
    (output / "status.txt").write_text("PASS\n", encoding="utf-8")


def start_printer_preview():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.printer_add() == {"FINISHED"}
        bpy.context.scene.tntmesh_printers[0].build_mm = (38, 30, 34)
        bpy.context.scene.tntmesh_settings.show_build_volume = True
    area.tag_redraw()


def toggle_smoke_panel(vertical_offset):
    window, area, _ = viewport()
    sidebar = next(region for region in area.regions if region.type == "UI")
    for value in ("PRESS", "RELEASE"):
        window.event_simulate(
            type="LEFTMOUSE", value=value, x=sidebar.x + 13, y=window.height - vertical_offset,
        )


def printer_screenshot():
    screenshot("06-printer.png")
    bpy.context.scene.tntmesh_settings.show_build_volume = False


def open_calibration_dialog():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.calibrate_connectors("INVOKE_DEFAULT") == {"RUNNING_MODAL"}


def capture_calibration():
    screenshot("07-calibration.png")
    cancel_line()


def set_region_preview():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        obj = bpy.context.active_object
        top = max(obj.data.polygons, key=lambda face: face.normal.z)
        for face in obj.data.polygons:
            face.select = face.index == top.index
        obj.data.update()
        settings = bpy.context.scene.tntmesh_settings
        settings.cut_kind = "REGION"
        settings.region_method = "SELECTION"
        settings.region_smoothing = 2
        settings.show_plane = True
    area.tag_redraw()


def set_symmetry_preview():
    screenshot("08-region.png")
    settings = bpy.context.scene.tntmesh_settings
    settings.cut_kind = "SYMMETRY"
    settings.axis = "X"
    settings.offset = 6.0
    settings.symmetry_axis = "X"
    settings.symmetry_rotation = (0, .20, 0)
    viewport()[1].tag_redraw()


def reset_cut_preview():
    screenshot("09-symmetry.png")
    settings = bpy.context.scene.tntmesh_settings
    settings.cut_kind = "PLANAR"
    settings.axis = "Z"
    settings.offset = 0
    viewport()[1].tag_redraw()


def start_exploded_preview():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.assembly_project() == {"FINISHED"}
        bpy.context.scene.tntmesh_assembly.distance = 11
    area.tag_redraw()


def capture_assembly():
    screenshot("10-assembly.png")
    assert bpy.ops.tntmesh.assembly_action(action="RESET") == {"FINISHED"}


def start_base_preview():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "tntmesh_integration_fixture", Path(__file__).with_name("integration.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        module.stepped_base_fixture(module.load_addon())
        settings = bpy.context.scene.tntmesh_settings
        settings.cut_kind = "BASE"
        settings.base_band = 7
        assert bpy.ops.tntmesh.find_base_contacts() == {"FINISHED"}
        assert len(settings.base_contacts) == 2
        area.spaces.active.region_3d.view_location.z = 9
    area.tag_redraw()


def capture_base():
    screenshot("11-base-contacts.png")


def open_material_separation():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        obj = bpy.context.active_object
        obj.data.materials.clear()
        for label in ("Base material", "Top material"):
            obj.data.materials.append(bpy.data.materials.new(label))
        for face in obj.data.polygons:
            face.material_index = 0
        max(obj.data.polygons, key=lambda face: face.normal.z).material_index = 1
        settings = bpy.context.scene.tntmesh_settings
        settings.cut_kind = "REGION"
        settings.region_method = "MATERIAL"
        assert bpy.ops.tntmesh.split_materials("INVOKE_DEFAULT") == {"RUNNING_MODAL"}
    area.tag_redraw()


def capture_material_separation():
    screenshot("12-material-separation.png")
    cancel_line()


def open_insertion_dialog():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.check_insertion("INVOKE_DEFAULT") == {"RUNNING_MODAL"}


def capture_insertion_dialog():
    screenshot("13-insertion.png")
    cancel_line()


def start_diagnostics():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        from mathutils import Vector

        bpy.ops.mesh.primitive_plane_add(size=25, location=(-6, -8, 19), rotation=(.7, 0, .25))
        obj = bpy.context.object
        obj.name = "Open surface"
        area.spaces.active.region_3d.view_location = Vector(obj.location)
        assert bpy.ops.tntmesh.diagnose() == {"FINISHED"}
        assert bpy.ops.tntmesh.diagnostic_view(kind="OPEN", focus=True) == {"FINISHED"}
    area.tag_redraw()


def capture_diagnostics():
    screenshot("14-diagnostics.png")
    assert bpy.ops.tntmesh.diagnostic_view(kind="CLEAR") == {"FINISHED"}


def start_wall_check():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        bpy.ops.mesh.primitive_cube_add(size=20, location=(0, 0, 19))
        slab = bpy.context.object
        slab.name = "0.6 mm wall"
        slab.scale.z = .03
        bpy.context.view_layer.update()
        assert bpy.ops.tntmesh.diagnose(wall_mm=.8) == {"FINISHED"}
        assert bpy.ops.tntmesh.diagnostic_view(kind="THIN_WALL", focus=True) == {"FINISHED"}
    area.tag_redraw()


def capture_wall_check():
    screenshot("15-wall-thickness.png")
    assert bpy.ops.tntmesh.diagnostic_view(kind="CLEAR") == {"FINISHED"}


def show_repair_panel():
    settings = bpy.context.scene.tntmesh_settings
    settings.mode = "EASY"
    settings.repair_orientation = True
    viewport()[1].tag_redraw()


def start_line():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.draw_plane("INVOKE_DEFAULT") == {"RUNNING_MODAL"}


def click_start():
    window, _, region = viewport()
    window.event_simulate(
        type="LEFTMOUSE", value="PRESS", x=region.x + region.width // 5,
        y=region.y + region.height // 2,
    )


def click_end():
    window, _, region = viewport()
    window.event_simulate(
        type="LEFTMOUSE", value="PRESS", x=region.x + 3 * region.width // 5,
        y=region.y + 2 * region.height // 5,
    )


def verify_line():
    settings = bpy.context.scene.tntmesh_settings
    assert settings.axis == "FREE"
    assert settings.show_plane
    assert not pieces()
    screenshot("00-drawn-plane.png")
    settings.axis = "Z"
    settings.offset = 0.0


def cancel_line():
    window, _, _ = viewport()
    window.event_simulate(type="ESC", value="PRESS")


def verify_cancel():
    assert bpy.context.scene.tntmesh_settings.axis == "Z"
    assert not pieces()


def start_contour():
    bpy.context.scene.tntmesh_settings.cut_kind = "POLYGON"
    start_line()


def contour_click(x, y, *, value="PRESS", shift=False, event="LEFTMOUSE"):
    window, _, region = viewport()
    window.event_simulate(
        type=event, value=value, shift=shift,
        x=region.x + round(x * region.width), y=region.y + round(y * region.height),
    )


def finish_contour():
    window, _, _ = viewport()
    window.event_simulate(type="RET", value="PRESS")


def verify_contour():
    settings = bpy.context.scene.tntmesh_settings
    assert settings.cut_kind == "POLYGON" and settings.axis == "FREE"
    assert len(settings.contour) >= 4
    assert settings.contour_depth > 24.0
    screenshot("00-contour.png")
    settings.cut_kind = "PLANAR"
    settings.axis = "Z"


def start_manual_path():
    settings = bpy.context.scene.tntmesh_settings
    settings.cut_kind = "PATH"
    settings.path_smoothing = 1
    start_line()


def verify_manual_path():
    settings = bpy.context.scene.tntmesh_settings
    assert settings.cut_kind == "PATH" and settings.axis == "FREE"
    assert len(settings.contour) == 3 and settings.path_smoothing == 1
    assert settings.contour_depth > 24.0
    screenshot("17-manual-path.png")
    settings.cut_kind = "PLANAR"
    settings.axis = "Z"


def open_export_browser():
    window, area, region = viewport()
    with bpy.context.temp_override(window=window, area=area, region=region):
        assert bpy.ops.tntmesh.export_stl("INVOKE_DEFAULT", directory=str(output)) == {"RUNNING_MODAL"}


def check_export_browser():
    window, area = next(
        (window, area) for window in bpy.context.window_manager.windows
        for area in window.screen.areas if area.type == "FILE_BROWSER"
    )
    with bpy.context.temp_override(window=window, area=area):
        result = bpy.ops.screen.screenshot(filepath=str(output / "05-export.png"))
        assert result == {"FINISHED"}
    window.event_simulate(type="ESC", value="PRESS")


def check_export_cancelled():
    assert not any(
        area.type == "FILE_BROWSER" for window in bpy.context.window_manager.windows
        for area in window.screen.areas
    )
    assert len(pieces()) == 2


line_steps = (start_line, click_start, click_end, verify_line, start_line, click_start,
              cancel_line, verify_cancel) if os.environ.get("TNTMESH_TEST_EVENTS") == "1" else ()
contour_steps = (
    start_contour,
    lambda: contour_click(.40, .42, shift=True),
    lambda: contour_click(.46, .42, event="MOUSEMOVE", value="NOTHING", shift=True),
    lambda: contour_click(.52, .42, event="MOUSEMOVE", value="NOTHING", shift=True),
    lambda: contour_click(.52, .42, value="RELEASE", shift=True),
    lambda: contour_click(.52, .56),
    lambda: contour_click(.40, .56),
    finish_contour,
    verify_contour,
) if line_steps and os.environ.get("TNTMESH_TEST_CONTOUR") == "1" else ()
path_steps = (
    start_manual_path, lambda: contour_click(.40, .48),
    lambda: contour_click(.46, .56), lambda: contour_click(.54, .48),
    finish_contour, verify_manual_path,
) if line_steps and os.environ.get("TNTMESH_TEST_PATH") == "1" else ()
export_steps = (
    (open_export_browser, check_export_browser, check_export_cancelled) if line_steps else ()
)
printer_steps = (
    (start_printer_preview, lambda: toggle_smoke_panel(93),
     lambda: toggle_smoke_panel(120), printer_screenshot,
     lambda: toggle_smoke_panel(120), lambda: toggle_smoke_panel(93))
    if os.environ.get("TNTMESH_TEST_PRINTER") == "1" else ()
)
phase3_steps = (
    (set_region_preview, set_symmetry_preview, reset_cut_preview)
    if line_steps and os.environ.get("TNTMESH_TEST_PHASE3") == "1" else ()
)
assembly_steps = (
    (open_calibration_dialog, capture_calibration, start_exploded_preview,
     lambda: toggle_smoke_panel(93), lambda: toggle_smoke_panel(146),
     capture_assembly, lambda: toggle_smoke_panel(146), lambda: toggle_smoke_panel(93))
    if phase3_steps else ()
)
base_steps = (start_base_preview, capture_base) if os.environ.get("TNTMESH_TEST_BASE") == "1" else ()
material_steps = (
    (open_material_separation, capture_material_separation)
    if os.environ.get("TNTMESH_TEST_MATERIAL") == "1" else ()
)
insertion_steps = (
    (open_insertion_dialog, capture_insertion_dialog)
    if os.environ.get("TNTMESH_TEST_INSERTION") == "1" else ()
)
diagnostics_steps = (
    (start_diagnostics, capture_diagnostics, start_wall_check, capture_wall_check)
    if os.environ.get("TNTMESH_TEST_DIAGNOSTICS") == "1" else ()
)
repair_steps = (
    (show_repair_panel, lambda: toggle_smoke_panel(218), lambda: screenshot("16-repair.png"))
    if os.environ.get("TNTMESH_TEST_REPAIR") == "1" else ()
)
steps = iter((
    setup, panel, *line_steps, *contour_steps, *path_steps, *phase3_steps, split, undo, redo, spanish, panel,
    lambda: screenshot("03-spanish.png"),
    *export_steps, *printer_steps, *assembly_steps, *material_steps, *insertion_steps,
    *base_steps, draft_panel, *diagnostics_steps, finish, *repair_steps,
))


def tick():
    try:
        step = next(steps, None)
        if step is not None:
            step()
            return 0.6
    except Exception:
        (output / "status.txt").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(tick, first_interval=1.0)
