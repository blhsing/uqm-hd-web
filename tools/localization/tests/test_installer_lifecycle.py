from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMON = REPO_ROOT / "tools/install/UqmInstall.Common.ps1"
INSTALLER = REPO_ROOT / "tools/install/Install-UqmHdZhTw.ps1"
VERIFIER = REPO_ROOT / "tools/install/Test-UqmHdZhTwInstall.ps1"


def _quote(value: Path | str) -> str:
    return str(value).replace("'", "''")


def _powershell(prefer_windows_51: bool = False) -> str | None:
    if prefer_windows_51:
        candidate = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
        if candidate.is_file():
            return str(candidate)
    return shutil.which("powershell.exe") or shutil.which("pwsh")


def _run_powershell(script: str, *, prefer_windows_51: bool = False) -> str:
    executable = _powershell(prefer_windows_51)
    if executable is None:
        raise unittest.SkipTest("PowerShell is unavailable")
    completed = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


class InstallerLifecycleTests(unittest.TestCase):
    def test_shortcuts_use_the_installed_multisize_icon(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            install = root / "install"
            profile = root / "profile"
            install.mkdir()
            profile.mkdir()
            (install / "uqm.exe").write_bytes(b"not-a-real-executable")
            (install / "uqm-hd-zh-tw.ico").write_bytes(b"not-a-real-icon")
            shortcut = root / "test.lnk"
            script = f"""
. '{_quote(COMMON)}'
$specifications = @(Get-UqmShortcutSpecifications `
  -InstallRoot '{_quote(install)}' -ProfileDir '{_quote(profile)}')
$expectedIcon = (Get-UqmFullPath -Path '{_quote(install / "uqm-hd-zh-tw.ico")}') + ',0'
if (@($specifications | Where-Object {{
  -not [string]::Equals($_.IconLocation, $expectedIcon, [StringComparison]::OrdinalIgnoreCase)
}}).Count -ne 0) {{ throw 'A shortcut specification does not use the installed icon.' }}
$specification = $specifications[0]
$startMenu = @($specifications | Where-Object {{ $_.Kind -eq 'start-menu-fullscreen' }})
if ($startMenu.Count -ne 1) {{ throw 'Expected one explicit Start Menu fullscreen shortcut.' }}
$specification.Path = '{_quote(shortcut)}'
$specification.AllowedRoot = '{_quote(root)}'
[void](Write-UqmShortcut -Specification $specification)
$actual = Get-UqmShortcutDetails -Path '{_quote(shortcut)}'
[pscustomobject]@{{
  Count = $specifications.Count
  IconLocation = $actual.IconLocation
  Matches = Test-UqmShortcutMatches -Actual $actual -Expected $specification
  StartLeaf = Split-Path -Path $startMenu[0].Path -Leaf
  StartParent = Split-Path -Path $startMenu[0].Path -Parent
  Programs = Get-UqmFullPath -Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Programs))
  StartIsFullscreen = $startMenu[0].Arguments -match '(?:^|\\s)-f(?:\\s|$)'
}} | ConvertTo-Json -Compress
"""
            result = json.loads(_run_powershell(script))

        self.assertEqual(result["Count"], 2)
        self.assertEqual(
            result["IconLocation"].lower(),
            f"{install / 'uqm-hd-zh-tw.ico'},0".lower(),
        )
        self.assertTrue(result["Matches"])
        self.assertEqual(
            result["StartLeaf"],
            "The Ur-Quan Masters HD - Traditional Chinese.lnk",
        )
        self.assertEqual(result["StartParent"].lower(), result["Programs"].lower())
        self.assertTrue(result["StartIsFullscreen"])

    def test_stale_file_plan_is_read_only_and_removal_is_hash_gated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "install"
            install.mkdir()
            stale = install / "obsolete.dll"
            stale.write_bytes(b"managed-old-runtime")
            script = f"""
. '{_quote(COMMON)}'
$path = '{_quote(stale)}'
$marker = [pscustomobject]@{{
  State = 'complete'
  Files = @([pscustomobject]@{{
    Path = 'obsolete.dll'
    Length = (Get-Item -LiteralPath $path).Length
    Sha256 = Get-UqmSha256 -Path $path
  }})
}}
$plan = @(Get-UqmStaleManagedFilePlan -PreviousMarker $marker `
  -CurrentRelativePaths @('uqm.exe') -InstallRoot '{_quote(install)}')
$existedAfterPlan = Test-Path -LiteralPath $path
$removed = Remove-UqmStaleManagedFiles -Files $plan -InstallRoot '{_quote(install)}'
[pscustomobject]@{{
  Planned = $plan.Count
  ExistedAfterPlan = $existedAfterPlan
  Removed = $removed
  ExistsAfterRemoval = Test-Path -LiteralPath $path
}} | ConvertTo-Json -Compress
"""
            result = json.loads(_run_powershell(script))

        self.assertEqual(result["Planned"], 1)
        self.assertTrue(result["ExistedAfterPlan"])
        self.assertEqual(result["Removed"], 1)
        self.assertFalse(result["ExistsAfterRemoval"])

    def test_stale_file_plan_refuses_modified_previous_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            install = Path(temporary) / "install"
            install.mkdir()
            stale = install / "obsolete.dll"
            stale.write_bytes(b"user-modified")
            script = f"""
. '{_quote(COMMON)}'
$marker = [pscustomobject]@{{
  State = 'complete'
  Files = @([pscustomobject]@{{
    Path = 'obsolete.dll'
    Length = 3
    Sha256 = ('0' * 64)
  }})
}}
try {{
  [void]@(Get-UqmStaleManagedFilePlan -PreviousMarker $marker `
    -CurrentRelativePaths @('uqm.exe') -InstallRoot '{_quote(install)}')
  throw 'expected refusal was not raised'
}}
catch {{
  if ($_.Exception.Message -notlike '*refusing to delete it as stale*') {{ throw }}
  'refused'
}}
"""
            result = _run_powershell(script)
            self.assertEqual(stale.read_bytes(), b"user-modified")

        self.assertEqual(result, "refused")

    def test_custom_mode_excludes_upstream_top_level_binaries(self) -> None:
        script = f"""
. '{_quote(COMMON)}'
$tokens = $null
$errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
  '{_quote(INSTALLER)}', [ref]$tokens, [ref]$errors)
if (@($errors).Count -ne 0) {{ throw ($errors -join [Environment]::NewLine) }}
$definition = $ast.FindAll({{
  param($node)
  $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
    $node.Name -eq 'Test-ExcludedUqmSourceFile'
}}, $true) | Select-Object -First 1
Invoke-Expression $definition.Extent.Text
[pscustomobject]@{{
  LegacyDll = Test-ExcludedUqmSourceFile -RelativePath 'SDL.dll'
  CustomDll = Test-ExcludedUqmSourceFile -RelativePath 'SDL.dll' -CustomRuntime
  CustomExe = Test-ExcludedUqmSourceFile -RelativePath 'uqm.exe' -CustomRuntime
  NestedAsset = Test-ExcludedUqmSourceFile -RelativePath 'content/addons/example.dll' -CustomRuntime
}} | ConvertTo-Json -Compress
"""
        result = json.loads(_run_powershell(script))
        self.assertFalse(result["LegacyDll"])
        self.assertTrue(result["CustomDll"])
        self.assertTrue(result["CustomExe"])
        self.assertFalse(result["NestedAsset"])

    def test_transaction_plan_and_verifier_guards_are_wired(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        verifier = VERIFIER.read_text(encoding="utf-8")
        plan_boundary = installer.index("if ($PlanOnly)")
        self.assertIn("Get-UqmStaleManagedFilePlan", installer[:plan_boundary])
        self.assertIn("Assert-UqmPlayerOneRightAltBindingTarget", installer[:plan_boundary])
        self.assertIn("Assert-UqmFileDestinationPreflight", installer[:plan_boundary])
        self.assertIn(
            "Write-UqmUtf8JsonAtomic -Path $installingMarkerPath -Value $provisionalMarker",
            installer,
        )
        self.assertNotIn(
            "Write-UqmUtf8JsonAtomic -Path $markerPath -Value $provisionalMarker",
            installer,
        )
        self.assertLess(
            installer.index("Remove-UqmStaleManagedFiles"),
            installer.index("Write-UqmUtf8JsonAtomic -Path $markerPath -Value $finalMarker"),
        )
        self.assertIn("$removedLegacyStartShortcut = $false", installer)
        self.assertIn("Test-MarkerListsShortcut -Marker $previousMarker", installer)
        self.assertIn("if ($removedLegacyStartShortcut -and", installer)
        self.assertIn("absent from the managed manifest", verifier)

    def test_hex_conversion_works_in_windows_powershell_51(self) -> None:
        script = f"""
. '{_quote(COMMON)}'
ConvertTo-UqmHexString -Bytes ([byte[]](1, 2, 255))
"""
        self.assertEqual(
            _run_powershell(script, prefer_windows_51=True),
            "0102FF",
        )


if __name__ == "__main__":
    unittest.main()
