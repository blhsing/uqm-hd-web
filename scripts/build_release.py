from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
import zipfile


PACKS = {
    "native1080-zh_TW.uqm": (
        189_687_374,
        "f24d1f55e326fe20bb577c53eb12836ecff71af7a8b34ea2520537ec4ef1aef2",
    ),
}

DEFAULT_VERSION = "0.5.3"
VERSION_PATTERN = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+\-]{0,127}\Z")

SOURCE_FILES = (
    "LICENSE",
    "NOTICE.md",
    "LICENSES/UPSTREAM-COPYING.txt",
    "LICENSES/OFL-1.1-NotoSansCJK.txt",
    "tools/install/Install-UqmHdZhTw.ps1",
    "tools/install/UqmInstall.Common.ps1",
    "tools/install/Test-UqmHdZhTwInstall.ps1",
    "tools/install/patch_uqm_hd_menu_highlight.py",
    "tools/install/patch_uqm_hd_right_alt.py",
    "tools/install/patch_uqm_hd_super_melee_escape.py",
    "tools/install/patch_uqm_hd_super_melee_picker_escape.py",
    "tools/install/update_uqm_hd_escape_patch.py",
    "tools/install/update_uqm_hd_super_melee_picker_escape.py",
    "tools/install/README.md",
    "engine/build/win32_install/icon.ico",
)

RUNTIME_MANIFEST_NAME = "runtime-manifest.json"
RUNTIME_ARCHIVE_ROOT = "runtime/windows-x86"
RUNTIME_HASH_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
RUNTIME_LEAF_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+\-]*\Z")


@dataclass(frozen=True)
class RuntimeFile:
    path: str
    install_path: str
    length: int
    sha256: str
    kind: str
    source: Path


@dataclass(frozen=True)
class RuntimeBundle:
    root: Path
    manifest: Path
    files: tuple[RuntimeFile, ...]
    licenses: tuple[tuple[str, Path], ...]

INSTALL_TEXT = """UQM-HD 繁體中文版 v{version} — Windows 安裝說明

本壓縮檔不包含原版遊戲內容。請先從 UQM-HD 的官方 SourceForge
專案取得 Windows Beta 1，並解壓縮至獨立目錄。{runtime_intro}

需求：
- Windows PowerShell 5.1 或 PowerShell 7
{runtime_requirements}
- 原版目錄須包含 content 及 content\\addons{source_executable_requirement}

建議安裝方式：

1. 將本壓縮檔完整解壓縮，並保留所有檔案的相對路徑。
2. 先在解壓縮目錄開啟 PowerShell，執行唯讀演練：

   powershell.exe -NoProfile -ExecutionPolicy Bypass `
     -File .\\tools\\install\\Install-UqmHdZhTw.ps1 `
     -SourceRoot C:\\path\\to\\UQM-HD `
     -PacksDir . `
{runtime_argument}     -InstallRoot C:\\Games\\UQM-HD-TW `
     -ProfileDir "$env:APPDATA\\UQM-HD-zh_TW" `
     -PlanOnly

3. 確認演練結果後，以相同命令移除最後的 -PlanOnly 正式安裝。
4. 從開始選單開啟
   "The Ur-Quan Masters HD - Traditional Chinese"；預設以
   2560x1920 超取樣畫布、雙線性縮放及主螢幕原生解析度全螢幕啟動。
   F11 可切換全螢幕；PrtScr 會複製畫面至剪貼簿，並另存 BMP 至
   %APPDATA%/UQM-HD-zh_TW/screenshots。

安裝器只讀取 SourceRoot，另建受管理的目的地副本。它會驗證單一原生 1080p 套件。
{runtime_behavior}
它不會覆寫原版目錄中的任何檔案。

完整玩法、船艦圖鑑、原始碼、限制及疑難排解：
https://github.com/blhsing/uqm-hd-traditional-chinese

套件 SHA-256 請見 SHA256SUMS。授權及歸屬請見 LICENSE、NOTICE.md 與
LICENSES 目錄。本地化遊戲內容採 CC BY-NC-SA 2.5，不得作商業用途。
"""


def _runtime_leaf(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not RUNTIME_LEAF_PATTERN.fullmatch(value):
        raise ValueError(f"runtime {field} must be a safe ASCII leaf filename: {value!r}")
    if value in {".", ".."}:
        raise ValueError(f"runtime {field} is not a filename: {value!r}")
    return value


def validate_version(value: object) -> str:
    """Return a release version that is safe to embed in archive paths."""
    if not isinstance(value, str) or not VERSION_PATTERN.fullmatch(value):
        raise ValueError(
            "release version must be 1-128 ASCII letters, digits, dots, underscores, "
            "pluses, or hyphens, and must begin with a letter or digit"
        )
    return value


def _runtime_license_path(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"runtime {field} must be a POSIX path below LICENSES/: {value!r}")
    if any(character in value for character in '\x00<>:"|?*'):
        raise ValueError(f"runtime {field} contains an unsafe character: {value!r}")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) < 2
        or path.parts[0] != "LICENSES"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"runtime {field} must be a normalized path below LICENSES/: {value!r}")
    return value


def load_runtime_bundle(runtime_dir: Path) -> RuntimeBundle:
    root = runtime_dir.resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"runtime directory must be a normal directory: {root}")
    manifest_path = root / RUNTIME_MANIFEST_NAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise FileNotFoundError(f"runtime manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"runtime manifest is not valid UTF-8 JSON: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("runtime manifest root must be an object")
    if manifest.get("schemaVersion") != 1:
        raise ValueError("runtime manifest schemaVersion must be 1")
    if manifest.get("platform") != "windows-x86":
        raise ValueError("runtime manifest platform must be windows-x86")
    executable = _runtime_leaf(manifest.get("executable"), field="executable")
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise ValueError("runtime manifest files must be a non-empty array")

    files: list[RuntimeFile] = []
    seen_paths: set[str] = set()
    seen_install_paths: set[str] = set()
    executable_entries = 0
    library_entries = 0
    referenced_licenses: set[str] = set()
    for index, raw_entry in enumerate(raw_files):
        if not isinstance(raw_entry, dict):
            raise ValueError(f"runtime files[{index}] must be an object")
        path = _runtime_leaf(raw_entry.get("path"), field=f"files[{index}].path")
        install_path = _runtime_leaf(
            raw_entry.get("installPath"), field=f"files[{index}].installPath"
        )
        path_key = path.casefold()
        install_key = install_path.casefold()
        if path_key in seen_paths:
            raise ValueError(f"duplicate runtime source path: {path}")
        if install_key in seen_install_paths:
            raise ValueError(f"duplicate runtime install path: {install_path}")
        seen_paths.add(path_key)
        seen_install_paths.add(install_key)

        length = raw_entry.get("length")
        if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
            raise ValueError(f"runtime files[{index}].length must be a positive integer")
        digest = raw_entry.get("sha256")
        if not isinstance(digest, str) or not RUNTIME_HASH_PATTERN.fullmatch(digest):
            raise ValueError(f"runtime files[{index}].sha256 must contain 64 hex digits")
        digest = digest.lower()
        kind = raw_entry.get("kind")
        if kind == "executable":
            executable_entries += 1
            if path != executable or install_path.casefold() != "uqm.exe":
                raise ValueError(
                    "the runtime executable entry must match executable and install as uqm.exe"
                )
            if Path(path).suffix.casefold() != ".exe":
                raise ValueError("the runtime executable source must have an .exe suffix")
        elif kind == "runtime-library":
            library_entries += 1
            if Path(path).suffix.casefold() != ".dll" or path != install_path:
                raise ValueError(
                    "runtime-library entries must be DLLs installed under the same leaf name"
                )
        else:
            raise ValueError(f"unsupported runtime files[{index}].kind: {kind!r}")

        for field in ("package", "version", "license"):
            value = raw_entry.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"runtime files[{index}].{field} must be a non-empty string")
        license_files = raw_entry.get("licenseFiles")
        if not isinstance(license_files, list) or not license_files:
            raise ValueError(f"runtime files[{index}].licenseFiles must be a non-empty array")
        for license_index, license_path in enumerate(license_files):
            referenced_licenses.add(
                _runtime_license_path(
                    license_path,
                    field=f"files[{index}].licenseFiles[{license_index}]",
                )
            )
        provenance = raw_entry.get("provenance")
        if not isinstance(provenance, dict) or not provenance:
            raise ValueError(f"runtime files[{index}].provenance must be a non-empty object")

        source = root / path
        if not source.is_file() or source.is_symlink():
            raise FileNotFoundError(f"runtime payload file is missing or unsafe: {source}")
        if source.stat().st_size != length:
            raise ValueError(f"runtime payload length differs from manifest: {path}")
        if sha256_file(source) != digest:
            raise ValueError(f"runtime payload SHA-256 differs from manifest: {path}")
        files.append(RuntimeFile(path, install_path, length, digest, kind, source))

    if executable_entries != 1:
        raise ValueError("runtime manifest must contain exactly one executable entry")
    if library_entries == 0:
        raise ValueError("runtime manifest must contain at least one runtime-library entry")
    listed = {entry.path.casefold() for entry in files}
    unlisted_binaries = sorted(
        item.name
        for item in root.iterdir()
        if item.is_file()
        and item.suffix.casefold() in {".exe", ".dll"}
        and item.name.casefold() not in listed
    )
    if unlisted_binaries:
        raise ValueError(
            "runtime directory contains unlisted executable files: "
            + ", ".join(unlisted_binaries)
        )

    licenses_root = root / "LICENSES"
    if not licenses_root.is_dir() or licenses_root.is_symlink():
        raise FileNotFoundError(f"runtime LICENSES directory is missing: {licenses_root}")
    licenses: list[tuple[str, Path]] = []
    for item in sorted(licenses_root.rglob("*")):
        if item.is_symlink():
            raise ValueError(f"runtime LICENSES contains a symbolic link: {item}")
        if item.is_file():
            relative = item.relative_to(root).as_posix()
            licenses.append((relative, item))
    if not licenses:
        raise ValueError("runtime LICENSES directory contains no license files")
    available_licenses = {relative for relative, _ in licenses}
    missing_licenses = sorted(referenced_licenses - available_licenses)
    if missing_licenses:
        raise FileNotFoundError(
            "runtime manifest references missing license files: " + ", ".join(missing_licenses)
        )
    return RuntimeBundle(
        root=root,
        manifest=manifest_path,
        files=tuple(sorted(files, key=lambda item: item.path.casefold())),
        licenses=tuple(licenses),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(source) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def verify_packs(packs_dir: Path) -> None:
    for name, (expected_size, expected_hash) in PACKS.items():
        path = packs_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"required release pack is missing: {path}")
        if path.stat().st_size != expected_size:
            raise ValueError(
                f"wrong size for {name}: expected {expected_size}, got {path.stat().st_size}"
            )
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise ValueError(
                f"wrong SHA-256 for {name}: expected {expected_hash}, got {actual_hash}"
            )


def write_file(archive: zipfile.ZipFile, arcname: str, source: Path) -> None:
    with source.open("rb") as input_file, archive.open(zip_info(arcname), "w") as output:
        shutil.copyfileobj(input_file, output, length=1024 * 1024)


def verify_release_archive(
    archive_path: Path,
    *,
    repo_root: Path,
    version: str,
    install_text: bytes,
    checksum_text: bytes,
    runtime: RuntimeBundle | None,
) -> None:
    version = validate_version(version)
    prefix = f"uqm-hd-zh-tw-v{version}"
    expected_names = {
        *(f"{prefix}/{name}" for name in PACKS),
        f"{prefix}/INSTALL.zh-TW.txt",
        f"{prefix}/SHA256SUMS",
        *(f"{prefix}/{relative}" for relative in SOURCE_FILES),
    }
    if runtime is not None:
        expected_names.add(f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{RUNTIME_MANIFEST_NAME}")
        expected_names.update(
            f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{entry.path}" for entry in runtime.files
        )
        expected_names.update(
            f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{relative}"
            for relative, _ in runtime.licenses
        )
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != expected_names:
            raise ValueError("release archive entries do not match the exact manifest")
        if archive.testzip() is not None:
            raise ValueError("release archive failed its CRC integrity check")
        for info in archive.infolist():
            if info.compress_type != zipfile.ZIP_STORED:
                raise ValueError(f"release entry was unexpectedly compressed: {info.filename}")
            if info.date_time != (1980, 1, 1, 0, 0, 0):
                raise ValueError(f"release entry has a nondeterministic timestamp: {info.filename}")
        expected_executables = set()
        if runtime is not None:
            expected_executables = {
                f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{entry.path}"
                for entry in runtime.files
                if entry.kind == "executable"
            }
        actual_executables = {name for name in names if name.casefold().endswith(".exe")}
        if actual_executables != expected_executables:
            raise ValueError("release archive executable entries do not match the runtime manifest")
        for name, (expected_size, expected_hash) in PACKS.items():
            info = archive.getinfo(f"{prefix}/{name}")
            if info.file_size != expected_size:
                raise ValueError(f"release archive has the wrong size for {name}")
            with archive.open(info) as source:
                if sha256_stream(source) != expected_hash:
                    raise ValueError(f"release archive has the wrong SHA-256 for {name}")
        if archive.read(f"{prefix}/INSTALL.zh-TW.txt") != install_text:
            raise ValueError("release installation instructions changed after writing")
        if archive.read(f"{prefix}/SHA256SUMS") != checksum_text:
            raise ValueError("release checksum manifest changed after writing")
        for relative in SOURCE_FILES:
            if archive.read(f"{prefix}/{relative}") != (repo_root / relative).read_bytes():
                raise ValueError(f"release source file changed after writing: {relative}")
        if runtime is not None:
            manifest_name = f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{RUNTIME_MANIFEST_NAME}"
            if archive.read(manifest_name) != runtime.manifest.read_bytes():
                raise ValueError("release runtime manifest changed after writing")
            for entry in runtime.files:
                name = f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{entry.path}"
                info = archive.getinfo(name)
                if info.file_size != entry.length:
                    raise ValueError(f"release runtime has the wrong size for {entry.path}")
                with archive.open(info) as source:
                    if sha256_stream(source) != entry.sha256:
                        raise ValueError(
                            f"release runtime has the wrong SHA-256 for {entry.path}"
                        )
            for relative, source in runtime.licenses:
                name = f"{prefix}/{RUNTIME_ARCHIVE_ROOT}/{relative}"
                if archive.read(name) != source.read_bytes():
                    raise ValueError(f"release runtime license changed after writing: {relative}")


def build_release(
    *,
    repo_root: Path,
    packs_dir: Path,
    output: Path,
    version: str,
    force: bool,
    runtime_dir: Path | None = None,
) -> None:
    version = validate_version(version)
    verify_packs(packs_dir)
    runtime = load_runtime_bundle(runtime_dir) if runtime_dir is not None else None
    for relative in SOURCE_FILES:
        if not (repo_root / relative).is_file():
            raise FileNotFoundError(f"required repository file is missing: {relative}")
    if output.exists() and not force:
        raise FileExistsError(f"refusing to overwrite {output}; pass --force to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"uqm-hd-zh-tw-v{version}"
    checksum_lines = [
        f"{expected_hash}  {name}\n"
        for name, (_, expected_hash) in PACKS.items()
    ]
    if runtime is not None:
        checksum_lines.append(
            f"{sha256_file(runtime.manifest)}  {RUNTIME_ARCHIVE_ROOT}/{RUNTIME_MANIFEST_NAME}\n"
        )
        checksum_lines.extend(
            f"{entry.sha256}  {RUNTIME_ARCHIVE_ROOT}/{entry.path}\n"
            for entry in runtime.files
        )
        checksum_lines.extend(
            f"{sha256_file(source)}  {RUNTIME_ARCHIVE_ROOT}/{relative}\n"
            for relative, source in runtime.licenses
        )
    checksum_text = "".join(checksum_lines).encode("ascii")
    if runtime is None:
        install_values = {
            "runtime_intro": "",
            "runtime_requirements": "- Python 3.10 以上，且 python 指令可由 PATH 執行",
            "source_executable_requirement": "，並須包含 uqm.exe",
            "runtime_argument": "",
            "runtime_behavior": (
                "安裝時會在目的地副本上套用雜湊鎖定的舊版執行檔補丁；"
                "未知 uqm.exe 版本會被拒絕。"
            ),
        }
    else:
        install_values = {
            "runtime_intro": (
                "\n本版亦包含從公開原始碼建置的 Windows x86 執行環境，"
                "並以 SHA-256 清單鎖定。"
            ),
            "runtime_requirements": "- 使用附帶執行環境時不需要 Python",
            "source_executable_requirement": "",
            "runtime_argument": "     -RuntimeDir .\\runtime\\windows-x86 `\n",
            "runtime_behavior": (
                "附帶執行環境的 runtime-manifest.json 會在寫入前驗證每個 EXE/DLL，"
                "並將自建執行檔安裝為 uqm.exe；此路徑不會套用舊版二進位補丁。"
            ),
        }
    install_text = INSTALL_TEXT.format(version=version, **install_values).encode("utf-8")

    with tempfile.NamedTemporaryFile(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with zipfile.ZipFile(
            temporary_path, "w", allowZip64=False, strict_timestamps=True
        ) as archive:
            for name in PACKS:
                write_file(archive, f"{prefix}/{name}", packs_dir / name)
            archive.writestr(zip_info(f"{prefix}/INSTALL.zh-TW.txt"), install_text)
            archive.writestr(zip_info(f"{prefix}/SHA256SUMS"), checksum_text)
            for relative in SOURCE_FILES:
                write_file(archive, f"{prefix}/{relative}", repo_root / relative)
            if runtime is not None:
                runtime_prefix = f"{prefix}/{RUNTIME_ARCHIVE_ROOT}"
                write_file(
                    archive,
                    f"{runtime_prefix}/{RUNTIME_MANIFEST_NAME}",
                    runtime.manifest,
                )
                for entry in runtime.files:
                    write_file(archive, f"{runtime_prefix}/{entry.path}", entry.source)
                for relative, source in runtime.licenses:
                    write_file(archive, f"{runtime_prefix}/{relative}", source)
        verify_release_archive(
            temporary_path,
            repo_root=repo_root,
            version=version,
            install_text=install_text,
            checksum_text=checksum_text,
            runtime=runtime,
        )
        os.replace(temporary_path, output)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the verified standalone Traditional-Chinese release ZIP."
    )
    parser.add_argument("--packs-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default=DEFAULT_VERSION, type=validate_version)
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        help=(
            "optional verified Windows x86 runtime directory containing "
            "runtime-manifest.json and LICENSES/"
        ),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    build_release(
        repo_root=repo_root,
        packs_dir=args.packs_dir.resolve(),
        output=args.output.resolve(),
        version=args.version,
        force=args.force,
        runtime_dir=args.runtime_dir.resolve() if args.runtime_dir is not None else None,
    )
    print(f"built {args.output.resolve()}")
    print(f"sha256 {sha256_file(args.output.resolve())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
