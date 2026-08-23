from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import zipfile

from scripts import build_release as release


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RuntimeReleaseTests(unittest.TestCase):
    def test_release_metadata_matches_v053_payloads(self) -> None:
        self.assertEqual(release.DEFAULT_VERSION, "0.5.3")
        self.assertEqual(
            release.PACKS,
            {
                "native1080-zh_TW.uqm": (
                    189_687_374,
                    "f24d1f55e326fe20bb577c53eb12836ecff71af7a8b34ea2520537ec4ef1aef2",
                ),
            },
        )

    def test_release_version_rejects_path_and_traversal_syntax(self) -> None:
        for invalid in (
            "",
            ".",
            "..",
            "../0.3.0",
            "0.3.0/asset",
            r"0.3.0\asset",
            "/absolute",
            r"C:\absolute",
            "0.3.0:alternate-stream",
            "0.3.0\nnext",
            " 0.3.0",
            "0.3.0 ",
            "a" * 129,
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    release.validate_version(invalid)

    def test_release_version_accepts_common_safe_versions(self) -> None:
        for valid in ("0.3.0", "0.3.0-rc.1", "v0.3.0+windows_x86", "test"):
            with self.subTest(valid=valid):
                self.assertEqual(release.validate_version(valid), valid)

    def test_fallback_release_includes_every_binary_patch_and_updater(self) -> None:
        self.assertTrue(
            {
                "tools/install/patch_uqm_hd_menu_highlight.py",
                "tools/install/patch_uqm_hd_right_alt.py",
                "tools/install/patch_uqm_hd_super_melee_escape.py",
                "tools/install/patch_uqm_hd_super_melee_picker_escape.py",
                "tools/install/update_uqm_hd_escape_patch.py",
                "tools/install/update_uqm_hd_super_melee_picker_escape.py",
                "engine/build/win32_install/icon.ico",
            }.issubset(release.SOURCE_FILES)
        )

    def make_runtime(self, root: Path) -> Path:
        runtime = root / "runtime"
        runtime.mkdir()
        executable = b"custom-uqm-runtime"
        library = b"custom-sdl-runtime"
        (runtime / "uqm-hd.exe").write_bytes(executable)
        (runtime / "SDL.dll").write_bytes(library)
        licenses = runtime / "LICENSES"
        licenses.mkdir()
        (licenses / "runtime-dependencies.txt").write_text(
            "Test-only license inventory.\n", encoding="utf-8"
        )
        manifest = {
            "schemaVersion": 1,
            "platform": "windows-x86",
            "executable": "uqm-hd.exe",
            "files": [
                {
                    "path": "uqm-hd.exe",
                    "installPath": "uqm.exe",
                    "length": len(executable),
                    "sha256": _sha256(executable),
                    "kind": "executable",
                    "package": "uqm-hd",
                    "version": "test",
                    "license": "GPL-2.0-or-later",
                    "licenseFiles": ["LICENSES/runtime-dependencies.txt"],
                    "provenance": {"source": "test fixture"},
                },
                {
                    "path": "SDL.dll",
                    "installPath": "SDL.dll",
                    "length": len(library),
                    "sha256": _sha256(library),
                    "kind": "runtime-library",
                    "package": "SDL",
                    "version": "test",
                    "license": "LGPL-2.1-or-later",
                    "licenseFiles": ["LICENSES/runtime-dependencies.txt"],
                    "provenance": {"source": "test fixture"},
                },
            ],
        }
        (runtime / release.RUNTIME_MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        return runtime

    def test_runtime_bundle_validates_hashes_and_install_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.make_runtime(Path(temporary))
            bundle = release.load_runtime_bundle(runtime)

        self.assertEqual(bundle.files[0].path, "SDL.dll")
        executable = next(item for item in bundle.files if item.kind == "executable")
        self.assertEqual(executable.install_path, "uqm.exe")
        self.assertEqual(bundle.licenses[0][0], "LICENSES/runtime-dependencies.txt")

    def test_runtime_bundle_rejects_tampered_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.make_runtime(Path(temporary))
            (runtime / "SDL.dll").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "length differs"):
                release.load_runtime_bundle(runtime)

    def test_runtime_bundle_rejects_unlisted_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.make_runtime(Path(temporary))
            (runtime / "unexpected.dll").write_bytes(b"not listed")
            with self.assertRaisesRegex(ValueError, "unlisted executable"):
                release.load_runtime_bundle(runtime)

    def test_powershell_installer_accepts_the_same_runtime_manifest(self) -> None:
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh")
        if powershell is None:
            self.skipTest("PowerShell is unavailable")
        repo_root = Path(__file__).resolve().parents[3]
        common = repo_root / "tools/install/UqmInstall.Common.ps1"
        installer = repo_root / "tools/install/Install-UqmHdZhTw.ps1"
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.make_runtime(Path(temporary))
            quote = lambda value: str(value).replace("'", "''")
            script = f"""
. '{quote(common)}'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    '{quote(installer)}', [ref]$tokens, [ref]$errors)
if (@($errors).Count -ne 0) {{ throw ($errors -join [Environment]::NewLine) }}
$wanted = @('Test-UqmRuntimeLeafName', 'Get-UqmCustomRuntime')
$definitions = $ast.FindAll({{
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $wanted -contains $node.Name
}}, $true)
foreach ($definition in $definitions) {{ Invoke-Expression $definition.Extent.Text }}
$result = Get-UqmCustomRuntime -Path '{quote(runtime)}'
[pscustomobject]@{{
    Kind = $result.Kind
    Platform = $result.Platform
    Files = @($result.Files).Count
    Executable = @($result.Files | Where-Object Kind -eq 'custom-runtime-executable').RelativePath
}} | ConvertTo-Json -Compress
"""
            completed = subprocess.run(
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            result = json.loads(completed.stdout.strip())
        self.assertEqual(result["Kind"], "custom")
        self.assertEqual(result["Platform"], "windows-x86")
        self.assertEqual(result["Files"], 2)
        self.assertEqual(result["Executable"], "uqm.exe")

    def test_release_contains_only_manifest_runtime_and_licenses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            (repo / "LICENSE").write_text("test license\n", encoding="utf-8")
            packs = root / "packs"
            packs.mkdir()
            pack_data = b"test-pack"
            (packs / "zh_TW.uqm").write_bytes(pack_data)
            runtime = self.make_runtime(root)
            output = root / "release.zip"
            with (
                mock.patch.object(
                    release, "PACKS", {"zh_TW.uqm": (len(pack_data), _sha256(pack_data))}
                ),
                mock.patch.object(release, "SOURCE_FILES", ("LICENSE",)),
            ):
                release.build_release(
                    repo_root=repo,
                    packs_dir=packs,
                    output=output,
                    version="test",
                    force=False,
                    runtime_dir=runtime,
                )

            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                prefix = "uqm-hd-zh-tw-vtest/runtime/windows-x86"
                self.assertIn(f"{prefix}/uqm-hd.exe", names)
                self.assertIn(f"{prefix}/SDL.dll", names)
                self.assertIn(f"{prefix}/runtime-manifest.json", names)
                self.assertIn(f"{prefix}/LICENSES/runtime-dependencies.txt", names)
                install_text = archive.read(
                    "uqm-hd-zh-tw-vtest/INSTALL.zh-TW.txt"
                ).decode("utf-8")
                self.assertIn("-RuntimeDir .\\runtime\\windows-x86", install_text)


if __name__ == "__main__":
    unittest.main()
