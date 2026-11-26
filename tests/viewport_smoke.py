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
export_steps = (
    (open_export_browser, check_export_browser, check_export_cancelled) if line_steps else ()
)
steps = iter((
    setup, panel, *line_steps, *contour_steps, split, undo, redo, spanish, panel,
    lambda: screenshot("03-spanish.png"),
    *export_steps, draft_panel, finish,
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
