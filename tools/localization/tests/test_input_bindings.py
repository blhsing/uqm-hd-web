from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class PlayerOneRightAltTests(unittest.TestCase):
    def test_engine_loads_three_flight_alternates_but_editor_stays_two_slot(self):
        common_header = (
            REPO_ROOT / "engine/src/libs/input/input_common.h"
        ).read_text(encoding="utf-8")
        setup_menu = (REPO_ROOT / "engine/src/uqm/setupmenu.c").read_text(
            encoding="utf-8"
        )

        match = re.search(
            r"^#define\s+MAX_FLIGHT_ALTERNATES\s+(\d+)\s*$",
            common_header,
            re.MULTILINE,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(int(match.group(1)), 3)
        self.assertIn("for (j = 0; j < 2; j++)", setup_menu)

    def test_installer_writes_and_verifier_checks_right_alt_binding(self):
        common = (REPO_ROOT / "tools/install/UqmInstall.Common.ps1").read_text(
            encoding="utf-8"
        )
        installer = (REPO_ROOT / "tools/install/Install-UqmHdZhTw.ps1").read_text(
            encoding="utf-8"
        )
        verifier = (REPO_ROOT / "tools/install/Test-UqmHdZhTwInstall.ps1").read_text(
            encoding="utf-8"
        )

        expected = "1.special.3 = STRING:key RightAlt"
        self.assertIn(expected, common)
        self.assertIn("Set-UqmPlayerOneRightAltBinding -ProfileDir $profile", installer)
        self.assertIn("1\\.special\\.3", verifier)
        self.assertIn("RightAlt", verifier)

    def test_binary_patch_is_hash_gated_and_uses_a_distinct_cave(self):
        patcher = (REPO_ROOT / "tools/install/patch_uqm_hd_right_alt.py").read_text(
            encoding="utf-8"
        )
        escape_patcher = (
            REPO_ROOT / "tools/install/patch_uqm_hd_super_melee_escape.py"
        ).read_text(encoding="utf-8")
        installer = (REPO_ROOT / "tools/install/Install-UqmHdZhTw.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('ORIGINAL_SHA256 = "3d2174f5', patcher)
        self.assertIn('PATCHED_SHA256 = "14bb155c', patcher)
        self.assertIn("CAVE_OFFSET = 0x75351", patcher)
        self.assertIn("position-independent hook", patcher)
        self.assertNotIn('"A1 B0 A2 52 00 "', patcher)
        self.assertIn("CAVE_OFFSET = 0x7329E", escape_patcher)
        self.assertIn("patch_uqm_hd_right_alt.py", installer)
        self.assertIn("14bb155c41af889e", installer)


if __name__ == "__main__":
    unittest.main()
