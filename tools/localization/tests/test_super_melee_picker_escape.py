from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class SuperMeleePickerEscapeTests(unittest.TestCase):
    def test_source_uses_physical_edit_cancel_and_existing_confirmation(self):
        source = (REPO_ROOT / "engine/src/uqm/supermelee/pickmele.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("PulsedInputState.menu[KEY_MENU_EDIT_CANCEL]", source)
        self.assertIn("&& ConfirmExit ()", source)
        self.assertIn("goto aborted;", source)

    def test_binary_patch_is_exact_hash_gated_and_uses_its_own_cave(self):
        picker = (
            REPO_ROOT
            / "tools/install/patch_uqm_hd_super_melee_picker_escape.py"
        ).read_text(encoding="utf-8")
        active_bout = (
            REPO_ROOT / "tools/install/patch_uqm_hd_super_melee_escape.py"
        ).read_text(encoding="utf-8")
        right_alt = (
            REPO_ROOT / "tools/install/patch_uqm_hd_right_alt.py"
        ).read_text(encoding="utf-8")

        self.assertIn('ORIGINAL_SHA256 = "14bb155c', picker)
        self.assertIn('PATCHED_SHA256 = "84d2b879', picker)
        self.assertIn("HOOK_OFFSET = 0xEA975", picker)
        self.assertIn("CAVE_OFFSET = 0x68061", picker)
        self.assertIn("CAVE_OFFSET = 0x7329E", active_bout)
        self.assertIn("CAVE_OFFSET = 0x75351", right_alt)
        self.assertIn("E8 A8 6F 00 00", picker)
        self.assertIn("A8 20", picker)
        self.assertIn("E8 CE 6F 00 00", picker)

    def test_installer_and_verifier_include_picker_escape_as_final_stage(self):
        installer = (REPO_ROOT / "tools/install/Install-UqmHdZhTw.ps1").read_text(
            encoding="utf-8"
        )
        verifier = (
            REPO_ROOT / "tools/install/Test-UqmHdZhTwInstall.ps1"
        ).read_text(encoding="utf-8")

        right_alt_index = installer.rfind("patch_uqm_hd_right_alt.py")
        picker_index = installer.rfind("patch_uqm_hd_super_melee_picker_escape.py")
        self.assertGreater(picker_index, right_alt_index)
        self.assertIn("84d2b879e0029684", installer)
        self.assertIn("0xEA975..0xEA97B", verifier)
        self.assertIn("0x68061..0x6807D", verifier)

    def test_managed_install_updater_is_present(self):
        updater = (
            REPO_ROOT
            / "tools/install/update_uqm_hd_super_melee_picker_escape.py"
        ).read_text(encoding="utf-8")
        self.assertIn("patch_uqm_hd_super_melee_picker_escape", updater)
        self.assertIn("marker must contain exactly one uqm.exe", updater)
        self.assertIn("_write_json_atomic", updater)


if __name__ == "__main__":
    unittest.main()
