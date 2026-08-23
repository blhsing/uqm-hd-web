from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]


class NativeResolutionSourceTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_engine_accepts_and_defaults_to_native_factor_three(self) -> None:
        source = self.read("engine/src/uqm.c")
        self.assertIn("INIT_CONFIG_OPTION(  resolutionFactor,  3 )", source)
        self.assertIn("options->resolutionFactor.value > 3", source)
        self.assertIn('"Resolution factor has to be 0, 1, 2 or 3."', source)

    def test_native_canvas_and_opengl_texture_are_large_enough(self) -> None:
        units = self.read("engine/src/uqm/units.h")
        opengl = self.read("engine/src/libs/graphics/sdl/opengl.c")
        self.assertIn("RES_NATIVE_SCALE", units)
        self.assertIn("texture_width = 512 << resolutionFactor", opengl)
        self.assertIn("texture_height = 256 << resolutionFactor", opengl)
        self.assertIn("GL_MAX_TEXTURE_SIZE", opengl)

    def test_native_combat_world_fits_legacy_coordinate_storage(self) -> None:
        units = self.read("engine/src/uqm/units.h")
        self.assertIn(
            "#define WORLD_RESOLUTION_FACTOR (RESOLUTION_FACTOR > 2 ? 2 : RESOLUTION_FACTOR)",
            units,
        )
        self.assertIn(
            "#define ONE_SHIFT (RESOLUTION_FACTOR > 2 ? 1 : 2)", units
        )
        self.assertIn("__builtin_choose_expr (__builtin_constant_p (x)", units)
        self.assertIn("16 << WORLD_RESOLUTION_FACTOR", units)

        screen_width = 2560
        screen_height = 1920
        status_width = 64 * 3 * 2
        one_shift = 1
        space_width = screen_width - status_width
        transition_width = (space_width << one_shift) << 2
        transition_height = (screen_height << one_shift) << 2
        logical_width = (space_width << one_shift) << 3
        logical_height = (screen_height << one_shift) << 3

        self.assertEqual((transition_width, transition_height), (17408, 15360))
        self.assertEqual((logical_width, logical_height), (34816, 30720))
        self.assertLess(transition_width, 1 << 15)
        self.assertLess(transition_height, 1 << 15)
        self.assertLess(logical_width, 1 << 16)
        self.assertLess(logical_height, 1 << 16)

    def test_stock_truecolor_frames_are_converted_then_resampled(self) -> None:
        loader = self.read("engine/src/libs/graphics/gfxload.c")
        canvas = self.read("engine/src/libs/graphics/sdl/canvas.c")
        self.assertIn("resolutionFactor > 2 && !ani[cel_ct].native_resolution", loader)
        self.assertIn("TFB_DrawCanvas_Rescale_Bilinear", loader)
        self.assertIn("SDL_ConvertSurface", canvas)
        self.assertIn("Could not convert %d-bit source", canvas)

    def test_installer_exposes_only_the_native_fullscreen_profile(self) -> None:
        common = self.read("tools/install/UqmInstall.Common.ps1")
        self.assertIn("$script:UqmPackNames = @('native1080-zh_TW.uqm')", common)
        self.assertIn("[ValidateSet(3)]", common)
        self.assertIn("-c bilinear --resfactor=3", common)
        self.assertIn("--addon native1080-zh_TW", common)
        self.assertEqual(common.count("ResolutionFactor = 3"), 2)


if __name__ == "__main__":
    unittest.main()
