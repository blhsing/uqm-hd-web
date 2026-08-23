from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from uqmloc.core import ContentResolver, LocError


ADDONS = ("native1080-zh_TW",)
ASCII_PROBES = ("00020.png", "00030.png", "00041.png", "00061.png")
CJK_PROBE = "04e00.png"


def _archive_info(
    name: str, compression: int = zipfile.ZIP_DEFLATED
) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = compression
    info.external_attr = 0o100644 << 16
    return info


def _files(root: Path):
    return sorted(path for path in root.rglob("*") if path.is_file())


def _font_paths(shadow_root: Path) -> list[str]:
    return sorted(
        path.relative_to(shadow_root).as_posix()
        for path in shadow_root.rglob("*.fon")
        if path.is_dir()
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_shadow_archive(
    resolver: ContentResolver,
    shadow_root: Path,
    menu_root: Path,
    destination: Path,
) -> dict[str, object]:
    # Values are either in-memory stock font bytes or a file to read.  Stock
    # glyphs are registered first; generated CJK glyphs and audited menu assets
    # intentionally take precedence when names overlap.
    entries: dict[str, bytes | Path] = {}
    font_report: dict[str, dict[str, object]] = {}
    font_paths = _font_paths(shadow_root)
    for font_path in font_paths:
        originals = resolver.list_files(font_path)
        if not originals:
            raise LocError(f"Original font is empty or missing: {font_path}")
        for name, raw in originals.items():
            if "/" in name or "\\" in name:
                raise LocError(f"Unsafe glyph filename in {font_path}: {name!r}")
            entries[f"{font_path}/{name}"] = raw
        font_report[font_path] = {
            "original_glyphs": len(originals),
            "probes": {probe: probe in originals for probe in ASCII_PROBES},
        }

    for path in _files(shadow_root):
        entries[path.relative_to(shadow_root).as_posix()] = path

    menu_files = _files(menu_root)
    if len(menu_files) != 7:
        raise LocError(f"Expected seven audited menu assets in {menu_root}, found {len(menu_files)}")
    for path in menu_files:
        relative = path.relative_to(menu_root).as_posix()
        if relative not in entries:
            raise LocError(f"Menu replacement has no source counterpart: {relative}")
        entries[relative] = path

    if len(entries) >= 65535:
        raise LocError(f"Shadow archive would require ZIP64: {len(entries)} files")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
        allowZip64=False,
    ) as archive:
        for name in sorted(entries):
            source = entries[name]
            raw = source.read_bytes() if isinstance(source, Path) else source
            archive.writestr(
                _archive_info(name),
                raw,
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=1,
            )

    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise LocError(f"CRC validation failed: {destination}")
        names = set(archive.namelist())
        if len(names) != len(entries):
            raise LocError(f"Duplicate paths in shadow archive: {destination}")
        for font_path, details in font_report.items():
            missing = [probe for probe in ASCII_PROBES if f"{font_path}/{probe}" not in names]
            if missing:
                raise LocError(f"{font_path}: missing stock glyph probes {missing}")
            if f"{font_path}/{CJK_PROBE}" not in names:
                raise LocError(f"{font_path}: missing generated CJK probe {CJK_PROBE}")
            details["packaged_glyphs"] = sum(
                name.startswith(f"{font_path}/") for name in names
            )

    return {
        "files": len(entries),
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "menu_files": len(menu_files),
        "fonts": font_report,
    }


def _append_shadow(source: Path, shadow: Path, destination: Path, addon: str) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    member = f"{addon}/shadow-content/{addon}-shadow.uqm"
    with zipfile.ZipFile(
        destination,
        "a",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=1,
        allowZip64=False,
    ) as archive:
        if member in archive.namelist():
            raise LocError(f"Source package already contains {member}")
        archive.writestr(
            _archive_info(member, zipfile.ZIP_STORED),
            shadow.read_bytes(),
            compress_type=zipfile.ZIP_STORED,
        )
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise LocError(f"CRC validation failed: {destination}")
        names = archive.namelist()
        if names.count(member) != 1:
            raise LocError(f"Expected one nested shadow archive in {destination}")
        if archive.getinfo(member).compress_type != zipfile.ZIP_STORED:
            raise LocError(f"Nested shadow archive must be stored, not deflated: {destination}")
    return {
        "files": len(names),
        "bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
        "shadow_member": member,
    }


def repack(content_root: Path, source_build: Path, menu_assets: Path, output: Path) -> list[dict[str, object]]:
    if output.exists():
        raise LocError(f"Output must not already exist: {output}")
    output.mkdir(parents=True)
    report: list[dict[str, object]] = []
    with ContentResolver(content_root) as resolver:
        for addon in ADDONS:
            shadow_root = source_build / "trees" / addon / "shadow-content"
            menu_root = menu_assets / addon
            source_pack = source_build / "packages" / f"{addon}.uqm"
            if not shadow_root.is_dir() or not menu_root.is_dir() or not source_pack.is_file():
                raise LocError(f"Missing source inputs for {addon}")
            shadow_pack = output / "shadow-archives" / f"{addon}-shadow.uqm"
            shadow_report = _write_shadow_archive(
                resolver, shadow_root, menu_root, shadow_pack
            )
            package = output / "packages" / f"{addon}.uqm"
            package_report = _append_shadow(source_pack, shadow_pack, package, addon)
            report.append(
                {
                    "addon": addon,
                    "shadow": shadow_report,
                    "package": package_report,
                }
            )
    (output / "repack-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repack completed localization trees with a mounted, self-contained shadow archive."
    )
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--source-build", type=Path, required=True)
    parser.add_argument("--menu-assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = repack(
        args.content_root.resolve(),
        args.source_build.resolve(),
        args.menu_assets.resolve(),
        args.output.resolve(),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
