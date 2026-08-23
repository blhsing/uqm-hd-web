from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "localization"))

from uqmloc.shipinfoassets import (  # noqa: E402
    SHIP_INFO_PAGES,
    SHIP_INFO_GAUGE_LABEL_ERASE_BOXES,
    SHIP_INFO_VARIANTS,
    SHIP_PICK_LABELS,
    _render_ship_info_frames,
    _scaled_box,
    _wrap_cjk,
    build_localized_ship_info_assets,
)


class ShipInfoAssetTests(unittest.TestCase):
    def test_all_twenty_five_pages_have_stable_native_resource_mappings(self):
        self.assertEqual([page.index for page in SHIP_INFO_PAGES], list(range(25)))
        self.assertEqual(len({page.stem for page in SHIP_INFO_PAGES}), 25)
        self.assertEqual(SHIP_INFO_PAGES[0].stem, "androsynth")
        self.assertEqual(SHIP_INFO_PAGES[-1].stem, "zoqfot")
        self.assertTrue(all(page.name and page.weapon and page.special for page in SHIP_INFO_PAGES))
        self.assertEqual(
            [
                (
                    variant.addon,
                    variant.ui_prefix,
                    variant.spin_prefix,
                    variant.canvas,
                    variant.native_scale,
                )
                for variant in SHIP_INFO_VARIANTS
            ],
            [
                (
                    "native1080-zh_TW",
                    "addons/hires4x/ui",
                    "addons/hires4x/cutscene/spins",
                    (2560, 1920),
                    2,
                ),
            ],
        )

    def test_picker_wording_is_localized(self):
        self.assertEqual(SHIP_PICK_LABELS["pick_ship"], "選擇船艦")
        self.assertEqual(SHIP_PICK_LABELS["ship_info"], "船艦資料")
        self.assertEqual(SHIP_PICK_LABELS["more_ships"], "想要更多船艦？")

    def test_canonical_race_names_and_closing_punctuation(self):
        self.assertEqual(SHIP_INFO_PAGES[1].name, "阿里盧拉萊萊・小艇")
        self.assertEqual(SHIP_INFO_PAGES[3].name, "克姆爾混合種・化身艦")

        class FixedWidthDraw:
            @staticmethod
            def textbbox(_position, text, font=None):
                del font
                return (0, 0, len(text) * 10, 10)

        self.assertEqual(
            _wrap_cjk(FixedWidthDraw(), "甲乙丙。", None, 30),
            ["甲乙", "丙。"],
        )

    @unittest.skipUnless(
        Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf").is_file(),
        "Noto Sans TC variable font is not installed",
    )
    def test_one_page_build_is_deterministic_and_uses_shadow_paths(self):
        from PIL import Image, ImageDraw

        base = Image.new("RGB", (1280, 960), (9, 11, 23))
        draw = ImageDraw.Draw(base)
        draw.rectangle((0, 92, 1279, 368), fill=(88, 88, 88))
        draw.rectangle((320, 196, 336, 220), fill=(230, 230, 230))
        draw.rectangle((1032, 248, 1260, 356), fill=(4, 5, 91))
        base_buffer = io.BytesIO()
        base.save(base_buffer, format="PNG")
        base.close()

        picker = Image.new("RGB", (512, 392), (128, 128, 124))
        picker_buffer = io.BytesIO()
        picker.save(picker_buffer, format="PNG")
        picker.close()

        class Resolver:
            @staticmethod
            def read_bytes(path: str) -> bytes:
                if path == "addons/hires4x/ui/meleemenu-027.png":
                    return picker_buffer.getvalue()
                if path == "addons/hires4x/cutscene/spins/ship00.ani":
                    return (
                        b"androsynth.png -2 -1 0 0\n"
                        b"androsynth-ovl.png -2 -1 0 0\n"
                    )
                if path == "addons/hires4x/cutscene/spins/androsynth.png":
                    return base_buffer.getvalue()
                raise AssertionError(f"unexpected resource: {path}")

        variant = SHIP_INFO_VARIANTS[0]
        page = SHIP_INFO_PAGES[0]
        font = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            with patch(
                "uqmloc.shipinfoassets.SHIP_INFO_VARIANTS", (variant,)
            ), patch("uqmloc.shipinfoassets.SHIP_INFO_PAGES", (page,)):
                first_report = build_localized_ship_info_assets(
                    Resolver(), first, font
                )
                second_report = build_localized_ship_info_assets(
                    Resolver(), second, font
                )

            expected = (
                "addons/hires4x/ui/meleemenu-027.png",
                "addons/hires4x/cutscene/spins/ship00.ani",
                "addons/hires4x/cutscene/spins/androsynth.png",
                "addons/hires4x/cutscene/spins/androsynth-ovl.png",
            )
            for relative in expected:
                first_file = first / "native1080-zh_TW" / Path(relative)
                second_file = second / "native1080-zh_TW" / Path(relative)
                with self.subTest(resource=relative):
                    self.assertTrue(first_file.is_file())
                    self.assertEqual(first_file.read_bytes(), second_file.read_bytes())

            report = first_report["native1080-zh_TW"]
            self.assertEqual(report["ship_info"]["pages"], 1)
            self.assertTrue(report["ship_info"]["native_resolution"])
            self.assertEqual(len(report["files"]), 4)
            with Image.open(
                first / "native1080-zh_TW/addons/hires4x/cutscene/spins/androsynth.png"
            ) as rendered_base:
                self.assertEqual(rendered_base.size, (2560, 1920))
                # A long English tagline may extend left of the nominal header;
                # the complete stock wording must be removed.
                self.assertEqual(
                    rendered_base.convert("RGB").getpixel((656, 416)),
                    (80, 80, 80),
                )
                # An untouched corner of the battle artwork remains intact.
                self.assertEqual(rendered_base.convert("RGB").getpixel((16, 1200)), (9, 11, 23))
            with Image.open(
                first / "native1080-zh_TW/addons/hires4x/cutscene/spins/androsynth-ovl.png"
            ) as rendered_overlay:
                self.assertEqual(rendered_overlay.size, (2560, 1920))
                self.assertIsNotNone(rendered_overlay.convert("RGBA").getchannel("A").getbbox())

    @unittest.skipUnless(
        Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf").is_file(),
        "Noto Sans TC variable font is not installed",
    )
    def test_shofixti_portrait_readout_is_localized(self):
        from PIL import Image, ImageDraw, ImageFont

        source = Image.new("RGB", (1280, 960), (9, 11, 23))
        draw = ImageDraw.Draw(source)
        draw.rectangle((1036, 204, 1168, 232), fill=(211, 17, 31))
        base, overlay = _render_ship_info_frames(
            Image,
            ImageDraw,
            ImageFont,
            source,
            SHIP_INFO_PAGES[13],
            Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf"),
        )
        source.close()
        overlay.close()
        panel = base.convert("RGB").crop((1036, 204, 1168, 232))
        raw = panel.tobytes()
        pixels = {raw[index : index + 3] for index in range(0, len(raw), 3)}
        self.assertNotIn(bytes((211, 17, 31)), pixels)
        self.assertGreater(len(pixels), 1)
        panel.close()
        base.close()

    @unittest.skipUnless(
        Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf").is_file(),
        "Noto Sans TC variable font is not installed",
    )
    def test_gauge_labels_match_panel_without_covering_gauge_artwork(self):
        from PIL import Image, ImageDraw, ImageFont

        panel_color = (73, 73, 73)
        crew_gauge_color = (0, 211, 31)
        energy_gauge_color = (221, 13, 17)
        old_crew_label_color = (5, 89, 5)
        old_energy_label_color = (101, 4, 4)
        frame_color = (116, 116, 116)
        font = Path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf")

        for variant in SHIP_INFO_VARIANTS:
            with self.subTest(addon=variant.addon):
                source = Image.new("RGB", variant.canvas, panel_color)
                draw = ImageDraw.Draw(source)
                draw.rectangle(
                    _scaled_box(variant.canvas, (40, 296, 68, 313)),
                    fill=crew_gauge_color,
                )
                draw.rectangle(
                    _scaled_box(variant.canvas, (236, 296, 264, 313)),
                    fill=energy_gauge_color,
                )
                draw.rectangle(
                    _scaled_box(variant.canvas, (40, 320, 127, 332)),
                    fill=old_crew_label_color,
                )
                draw.rectangle(
                    _scaled_box(variant.canvas, (180, 320, 263, 332)),
                    fill=old_energy_label_color,
                )
                scale_x = variant.canvas[0] / 1280
                scale_y = variant.canvas[1] / 960
                divider_x = round(276 * scale_x)
                separator_y = round(352 * scale_y)
                divider_top = round(205 * scale_y)
                separator_left = round(20 * scale_x)
                separator_right = round(280 * scale_x)
                draw.line(
                    (divider_x, divider_top, divider_x, separator_y),
                    fill=frame_color,
                )
                draw.line(
                    (
                        separator_left,
                        separator_y,
                        separator_right,
                        separator_y,
                    ),
                    fill=frame_color,
                )

                base, overlay = _render_ship_info_frames(
                    Image,
                    ImageDraw,
                    ImageFont,
                    source,
                    SHIP_INFO_PAGES[0],
                    font,
                )
                source.close()
                overlay.close()
                rendered = base.convert("RGB")

                crew_probe = _scaled_box(
                    variant.canvas, (45, 307, 46, 308)
                )[:2]
                energy_probe = _scaled_box(
                    variant.canvas, (241, 307, 242, 308)
                )[:2]
                self.assertEqual(
                    rendered.getpixel(crew_probe), crew_gauge_color
                )
                self.assertEqual(
                    rendered.getpixel(energy_probe), energy_gauge_color
                )
                self.assertEqual(
                    {
                        rendered.getpixel((divider_x, y))
                        for y in range(divider_top, separator_y + 1)
                    },
                    {frame_color},
                )
                self.assertEqual(
                    {
                        rendered.getpixel((x, separator_y))
                        for x in range(separator_left, separator_right + 1)
                    },
                    {frame_color},
                )

                for box, old_color in zip(
                    SHIP_INFO_GAUGE_LABEL_ERASE_BOXES,
                    (old_crew_label_color, old_energy_label_color),
                ):
                    rendered_box = rendered.crop(
                        _scaled_box(variant.canvas, box)
                    )
                    self.assertNotIn(
                        old_color, set(rendered_box.get_flattened_data())
                    )
                    self.assertEqual(rendered_box.getpixel((0, 0)), panel_color)
                    rendered_box.close()
                rendered.close()
                base.close()


if __name__ == "__main__":
    unittest.main()
