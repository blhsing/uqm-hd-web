from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class MousePressSnapshotTests(unittest.TestCase):
    def test_sdl_button_down_captures_press_position_atomically(self):
        header = (REPO_ROOT / "engine/src/libs/inplib.h").read_text(encoding="utf-8")
        source = (REPO_ROOT / "engine/src/libs/input/sdl/input.c").read_text(
            encoding="utf-8"
        )

        for field in ("press_x", "press_y", "press_inside_viewport"):
            self.assertIn(field, header)
        button_down = source.index("case SDL_MOUSEBUTTONDOWN:")
        generation = source.index("++MouseState.press_generation;", button_down)
        capture = source.index("MouseState.press_x = MouseState.x;", button_down)
        self.assertLess(capture, generation)
        self.assertIn(
            "MouseState.press_inside_viewport = MouseState.inside_viewport;",
            source[button_down:generation],
        )

    def test_mouse_click_does_not_hide_or_recenter_the_cursor(self):
        source = (REPO_ROOT / "engine/src/libs/input/sdl/input.c").read_text(
            encoding="utf-8"
        )
        button_down = source.index("case SDL_MOUSEBUTTONDOWN:")
        button_up = source.index("case SDL_MOUSEBUTTONUP:", button_down)
        click_handler = source[button_down:button_up]
        self.assertIn("setMouseCursorVisible (TRUE);", click_handler)
        self.assertNotIn("setMouseCursorVisible (FALSE);", click_handler)
        self.assertNotIn("SDL_WarpMouse", source)

    def test_print_screen_requests_an_opengl_framebuffer_capture(self):
        input_source = (REPO_ROOT / "engine/src/libs/input/sdl/input.c").read_text(
            encoding="utf-8"
        )
        renderer = (
            REPO_ROOT / "engine/src/libs/graphics/sdl/opengl.c"
        ).read_text(encoding="utf-8")
        self.assertIn("Event->key.keysym.sym == SDLK_PRINT", input_source)
        self.assertIn("TFB_GL_RequestScreenshot ();", input_source)
        self.assertIn("TFB_GL_CaptureFramebuffer", renderer)
        self.assertIn("TFB_Win32_CopyRGBAToClipboard", renderer)
        self.assertIn('"%s/screenshots"', renderer)

    def test_every_clickable_surface_targets_press_coordinates(self):
        sources = {
            "restart": REPO_ROOT / "engine/src/uqm/restart.c",
            "melee": REPO_ROOT / "engine/src/uqm/supermelee/melee.c",
            "buildpick": REPO_ROOT / "engine/src/uqm/supermelee/buildpick.c",
            "pickmele": REPO_ROOT / "engine/src/uqm/supermelee/pickmele.c",
        }
        for name, path in sources.items():
            source = path.read_text(encoding="utf-8")
            with self.subTest(surface=name):
                self.assertIn("press_inside_viewport", source)
                self.assertIn("press_x", source)
                self.assertIn("press_y", source)


class SuperMeleeStatsCardTests(unittest.TestCase):
    def test_shared_card_contains_performance_and_energy_fields(self):
        melee = (REPO_ROOT / "engine/src/uqm/supermelee/melee.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("DrawMeleeShipStatsCard", melee)
        for label in ("船員", "能量", "極速", "加速", "轉向", "回能", "武器", "特技"):
            self.assertIn(label, melee)
        self.assertIn("max_thrust >> RESOLUTION_FACTOR", melee)

    def test_both_picker_surfaces_call_shared_card(self):
        buildpick = (
            REPO_ROOT / "engine/src/uqm/supermelee/buildpick.c"
        ).read_text(encoding="utf-8")
        pickmele = (
            REPO_ROOT / "engine/src/uqm/supermelee/pickmele.c"
        ).read_text(encoding="utf-8")

        self.assertGreaterEqual(buildpick.count("DrawMeleeShipStatsCard"), 2)
        self.assertIn("GetBuildPickStatsRect", buildpick)
        self.assertIn("popupRect.corner.y + popupRect.extent.height", buildpick)
        self.assertIn("BoxUnion (&popupRect, &statsRect, r);", buildpick)
        self.assertIn("DrawMeleeShipStatsCard", pickmele)
        self.assertIn("隨機選船", pickmele)
        self.assertIn("返回隊伍設定", pickmele)


class SuperMeleeShipPickerMouseActionTests(unittest.TestCase):
    def test_picker_side_labels_dispatch_keyboard_equivalent_actions(self):
        source = (
            REPO_ROOT / "engine/src/uqm/supermelee/buildpick.c"
        ).read_text(encoding="utf-8")
        assets = (
            REPO_ROOT / "tools/localization/uqmloc/shipinfoassets.py"
        ).read_text(encoding="utf-8")

        self.assertIn("BuildPick_findActionAt", source)
        self.assertIn("BUILD_PICK_ACTION_CONFIRM", source)
        self.assertIn("BUILD_PICK_ACTION_INFO", source)
        self.assertIn(
            "BuildPick_findActionAt (mouse.press_x, mouse.press_y,",
            source,
        )
        confirm = source.index("pressedAction == BUILD_PICK_ACTION_CONFIRM")
        info = source.index("pressedAction == BUILD_PICK_ACTION_INFO")
        self.assertIn("pMS->buildPickConfirmed = true;", source[confirm:info])
        self.assertIn("DoShipSpin (pMS->currentShip", source[info:])
        for c_name, coordinate in (
            ("BUILD_PICK_CONFIRM_LEFT", 13),
            ("BUILD_PICK_CONFIRM_RIGHT", 67),
            ("BUILD_PICK_INFO_LEFT", 440),
            ("BUILD_PICK_INFO_RIGHT", 495),
        ):
            self.assertIn(f"#define {c_name} {coordinate}", source)
        self.assertIn("(13, 74, 67, 445)", assets)
        self.assertIn("(440, 74, 495, 445)", assets)

    def test_ship_info_click_exit_is_scoped_and_debounced(self):
        buildpick = (
            REPO_ROOT / "engine/src/uqm/supermelee/buildpick.c"
        ).read_text(encoding="utf-8")
        fmv = (REPO_ROOT / "engine/src/uqm/fmv.c").read_text(encoding="utf-8")
        intro = (REPO_ROOT / "engine/src/uqm/intro.c").read_text(
            encoding="utf-8"
        )

        self.assertIn("ShowPresentationWithMouseExit (vnbuf);", fmv)
        self.assertIn("Presentation_mouseClickExitRequested", intro)
        self.assertIn("mouse.last_button == TFB_MOUSE_BUTTON_LEFT", intro)
        self.assertIn("mouse.press_inside_viewport", intro)
        self.assertIn("mouse.press_generation", intro)
        self.assertIn(
            "pis.MousePressGeneration = mouse.press_generation;", intro
        )
        self.assertIn("ShowPresentationInternal (res, FALSE)", intro)
        self.assertIn("ShowPresentationInternal (res, TRUE)", intro)

        info = buildpick.index("pressedAction == BUILD_PICK_ACTION_INFO")
        spin = buildpick.index("DoShipSpin (pMS->currentShip", info)
        sync = buildpick.index("BuildPick_syncMouseState (pMS);", spin)
        self.assertLess(spin, sync)


if __name__ == "__main__":
    unittest.main()
