from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from .core import (
    ContentResolver,
    LocError,
    RmpEntry,
    load_workspace,
    parse_rmp,
    render_document,
    safe_resource_path,
)
from .fontgen import NotoRenderer, build_font_directory, translation_charset
from .menuassets import (
    build_localized_key_help,
    build_localized_main_menus,
    build_localized_status_labels,
    build_localized_super_melee_assets,
)
from .shipinfoassets import build_localized_ship_info_assets
from .validation import validate_documents


BASE_ADDON = "native1080-zh_TW"
VARIANTS = ((BASE_ADDON, "hires4x", 614),)
FONT_WEIGHT = 500
FONT_SUPERSAMPLE = 4
# The native tier uses an 8x logical canvas. Its shared UI fonts are authored
# at twice the 4x dimensions so the final 1080p downsample retains fine strokes.
# derives each glyph's hotspot and leading from the PNG canvas, while several
# SIS HUD fields retain fixed 20-pixel ink bands. Keep the medium Han ink large
# enough to read without moving its top rows beyond those gradient effects.
UI_FONT_METRICS: dict[tuple[str, str], tuple[int, int]] = {
    ("native1080-zh_TW", "starcon.fon"): (40, 38),
    ("native1080-zh_TW", "tiny.fon"): (40, 40),
    ("native1080-zh_TW", "micro.fon"): (48, 60),
}
FALLBACK_RESOURCE_TARGETS = {
    "font.fallbackto1x": (BASE_ADDON, "fonts/starcon.fon"),
    "font.fallbackto2x": (BASE_ADDON, "fonts/starcon.fon"),
    "font.fallbackto4x": (BASE_ADDON, "fonts/starcon.fon"),
    "font.tinyfallbackto1x": (BASE_ADDON, "fonts/tiny.fon"),
    "font.tinyfallbackto2x": (BASE_ADDON, "fonts/tiny.fon"),
    "font.tinyfallbackto4x": (BASE_ADDON, "fonts/tiny.fon"),
}
CONVERSATION_FONT_ALIASES = {
    "safeones": "spathi",
    "yehat.rebel": "yehat",
}
_DIRECT_FONT_RE = re.compile(
    r"^FONT(?:1X|2X|4X)?[ \t]+\d+(?:[ \t]+)([^ \t\r\n]+\.fon)[ \t]*$",
    re.M,
)


@dataclass(frozen=True)
class FontBuild:
    source_path: str
    mapped_path: str
    resource_ids: tuple[str, ...]


@dataclass
class VariantPlan:
    addon: str
    stock_addon: str | None
    rmp_entries: list[RmpEntry]
    font_builds: list[FontBuild]
    expected_rmp_count: int


def _all_translation_text(document: dict[str, Any]) -> str:
    return "\n".join(
        entry["translation"]
        for entry in document["entries"]
        if isinstance(entry.get("translation"), str)
    )


def _localized_conversation_fields(entry: RmpEntry, localized_path: str) -> tuple[str, ...]:
    if len(entry.fields) >= 3:
        return (localized_path, *entry.fields[1:])
    original = PurePosixPath(entry.fields[0])
    voice_name = original.parent.name
    stem = original.stem
    return (
        localized_path,
        f"addons/3dovoice/{voice_name}/",
        f"addons/3dovoice/{voice_name}/{stem}.ts",
    )


def _localized_text_entry(entry: RmpEntry, addon: str) -> RmpEntry:
    original = safe_resource_path(entry.fields[0])
    localized = f"addons/{addon}/{original}"
    fields = (
        _localized_conversation_fields(entry, localized)
        if entry.resource_type == "CONVERSATION"
        else (localized,)
    )
    return RmpEntry(entry.resource_id, entry.resource_type, fields)


def _font_output_path(addon: str, source_path: str) -> str:
    basename = PurePosixPath(source_path).name
    return f"addons/{addon}/fonts/{basename}"


def _fallback_rmp_entry(resource_id: str) -> RmpEntry:
    addon, relative = FALLBACK_RESOURCE_TARGETS[resource_id]
    return RmpEntry(resource_id, "FONTRES", (f"addons/{addon}/{relative}",))


def make_variant_plans(
    core_entries: list[RmpEntry], resolver: ContentResolver
) -> dict[str, VariantPlan]:
    text_entries = [entry for entry in core_entries if entry.resource_type in {"STRTAB", "CONVERSATION"}]
    core_fonts = [entry for entry in core_entries if entry.resource_type == "FONTRES"]
    if len(text_entries) != 104:
        raise LocError(f"Expected 104 core text mappings, found {len(text_entries)}")
    if len(core_fonts) != 39:
        raise LocError(f"Expected 39 core FONTRES mappings, found {len(core_fonts)}")
    plans: dict[str, VariantPlan] = {}
    core_font_ids = {entry.resource_id for entry in core_fonts}
    for addon, stock_addon, expected_gfx in VARIANTS:
        graphics: list[RmpEntry] = []
        if stock_addon:
            rmp_source, rmp_text = resolver.find_addon_rmp(stock_addon)
            stock_entries = parse_rmp(rmp_text, rmp_source)
            graphics = [entry for entry in stock_entries if entry.resource_type == "GFXRES"]
            if len(graphics) != expected_gfx:
                raise LocError(
                    f"{stock_addon}: expected {expected_gfx} GFXRES mappings, found {len(graphics)}"
                )
            stock_fonts = {
                entry.resource_id: entry
                for entry in stock_entries
                if entry.resource_type == "FONTRES"
            }
            unexpected_missing = core_font_ids - set(stock_fonts) - set(FALLBACK_RESOURCE_TARGETS)
            if unexpected_missing:
                raise LocError(
                    f"{stock_addon}: missing non-fallback font mappings: {sorted(unexpected_missing)}"
                )
            source_fonts = stock_fonts
        else:
            source_fonts = {entry.resource_id: entry for entry in core_fonts}

        localized_fonts: list[RmpEntry] = []
        build_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
        for core_font in core_fonts:
            resource_id = core_font.resource_id
            if resource_id in FALLBACK_RESOURCE_TARGETS:
                localized = _fallback_rmp_entry(resource_id)
            else:
                source = source_fonts.get(resource_id)
                if source is None:
                    raise LocError(f"{addon}: no source font for {resource_id}")
                mapped = _font_output_path(addon, source.fields[0])
                localized = RmpEntry(resource_id, "FONTRES", (mapped,))
                build_groups[(source.fields[0], mapped)].add(resource_id)
            localized_fonts.append(localized)
        # The six runtime fallback IDs intentionally point at the localized
        # starcon/tiny directories rather than separate fonts. Include their
        # all-text coverage requirement in the directory they target.
        for localized in localized_fonts:
            if localized.resource_id not in FALLBACK_RESOURCE_TARGETS:
                continue
            for key in list(build_groups):
                if key[1] == localized.fields[0]:
                    build_groups[key].add(localized.resource_id)
                    break
        localized_text = [_localized_text_entry(entry, addon) for entry in text_entries]
        rmp_entries = [*graphics, *localized_text, *localized_fonts]
        ids = [entry.resource_id for entry in rmp_entries]
        duplicates = sorted({resource_id for resource_id in ids if ids.count(resource_id) > 1})
        if duplicates:
            raise LocError(f"{addon}: duplicate RMP resource ids: {duplicates[:20]}")
        expected_total = expected_gfx + 104 + 39
        if len(rmp_entries) != expected_total:
            raise LocError(
                f"{addon}: internal mapping count {len(rmp_entries)} != expected {expected_total}"
            )
        plans[addon] = VariantPlan(
            addon=addon,
            stock_addon=stock_addon,
            rmp_entries=rmp_entries,
            font_builds=[
                FontBuild(source, mapped, tuple(sorted(resource_ids)))
                for (source, mapped), resource_ids in sorted(build_groups.items())
            ],
            expected_rmp_count=expected_total,
        )
    return plans


def _resource_charsets(
    documents: list[dict[str, Any]], core_entries: list[RmpEntry]
) -> tuple[dict[str, set[str]], set[str], set[str]]:
    by_resource: dict[str, set[str]] = {}
    document_by_path = {document["source_path"]: document for document in documents}
    for entry in core_entries:
        if entry.resource_type not in {"STRTAB", "CONVERSATION"}:
            continue
        document = document_by_path[entry.fields[0]]
        by_resource[entry.resource_id] = translation_charset([_all_translation_text(document)])
    all_chars = set().union(*(by_resource.values() or [set()]))
    script_documents = [
        document
        for document in documents
        if "/cutscene/" in document["source_path"].lower()
    ]
    script_chars = translation_charset(_all_translation_text(document) for document in script_documents)
    return by_resource, all_chars, script_chars


def _font_charset(
    resource_ids: Iterable[str],
    text_charsets: dict[str, set[str]],
    all_chars: set[str],
) -> set[str]:
    output: set[str] = set()
    general = set().union(
        *(
            chars
            for resource_id, chars in text_charsets.items()
            if not resource_id.startswith("comm.")
        ),
        set(),
    )
    lander = set().union(
        *(chars for resource_id, chars in text_charsets.items() if resource_id.startswith("text.")),
        set(),
    )
    credits = text_charsets.get("credits.credits", set())
    for resource_id in resource_ids:
        if resource_id in FALLBACK_RESOURCE_TARGETS:
            output.update(all_chars)
        elif resource_id.startswith("comm.") and resource_id.endswith(".font"):
            name = resource_id[len("comm.") : -len(".font")]
            dialogue_name = CONVERSATION_FONT_ALIASES.get(name, name)
            output.update(text_charsets.get(f"comm.{dialogue_name}.dialogue", set()))
            if name == "spathi":
                output.update(text_charsets.get("comm.safeones.dialogue", set()))
            if name == "yehat":
                output.update(text_charsets.get("comm.yehat.rebel.dialogue", set()))
            if name == "computer":
                output.update(text_charsets.get("comm.orz.dialogue", set()))
        elif resource_id.startswith("credits.font."):
            output.update(credits)
        elif resource_id == "font.lander":
            output.update(lander)
        else:
            output.update(general)
    return output


def _tree_path(trees_root: Path, mapped_resource_path: str) -> Path:
    path = safe_resource_path(mapped_resource_path)
    if not path.startswith("addons/"):
        raise LocError(f"Localized output path is not under addons/: {path}")
    relative = path[len("addons/") :]
    return trees_root.joinpath(*PurePosixPath(relative).parts)


def _write_text_trees(
    trees_root: Path,
    shadow_trees_root: Path,
    documents: list[dict[str, Any]],
    core_entries: list[RmpEntry],
) -> None:
    document_by_path = {document["source_path"]: document for document in documents}
    mapped_paths = {
        entry.fields[0]
        for entry in core_entries
        if entry.resource_type in {"STRTAB", "CONVERSATION"}
    }
    for source_path in sorted(mapped_paths):
        document = document_by_path[source_path]
        destination = trees_root / BASE_ADDON
        destination = destination.joinpath(*PurePosixPath(source_path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(render_document(document))
    for document in documents:
        if not document.get("auxiliary"):
            continue
        for addon, _, _ in VARIANTS:
            shadow = shadow_trees_root / addon
            destination = shadow.joinpath(*PurePosixPath(document["source_path"]).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(render_document(document))


def _direct_font_paths(documents: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()
    for document in documents:
        for entry in document["entries"]:
            for match in _DIRECT_FONT_RE.finditer(entry["body"]):
                paths.add(safe_resource_path(match.group(1)))
    return paths


def _write_rmps(trees_root: Path, plans: dict[str, VariantPlan]) -> None:
    for addon, plan in plans.items():
        path = trees_root / addon / f"{addon}.rmp"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(entry.format() for entry in plan.rmp_entries) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")


def _generate_fonts(
    resolver: ContentResolver,
    trees_root: Path,
    shadow_trees_root: Path,
    plans: dict[str, VariantPlan],
    documents: list[dict[str, Any]],
    core_entries: list[RmpEntry],
    renderer: NotoRenderer,
) -> dict[str, dict[str, Any]]:
    text_charsets, all_chars, script_chars = _resource_charsets(documents, core_entries)
    report: dict[str, dict[str, Any]] = {}
    for addon, plan in plans.items():
        variant_report: dict[str, Any] = {"mapped_fonts": {}, "shadow_fonts": {}}
        for font_build in plan.font_builds:
            characters = _font_charset(font_build.resource_ids, text_charsets, all_chars)
            destination = _tree_path(trees_root, font_build.mapped_path)
            metric_override = UI_FONT_METRICS.get(
                (plan.addon, PurePosixPath(font_build.mapped_path).name)
            )
            metrics, count = build_font_directory(
                resolver,
                font_build.source_path,
                destination,
                characters,
                renderer,
                copy_original=True,
                metric_override=metric_override,
                source_scale=2,
            )
            variant_report["mapped_fonts"][font_build.mapped_path] = {
                "source": font_build.source_path,
                "resource_ids": list(font_build.resource_ids),
                "metrics": {"width": metrics.width, "height": metrics.height},
                "generated_glyphs": count,
            }
        for source_path in sorted(_direct_font_paths(documents)):
            destination = shadow_trees_root / addon
            destination = destination.joinpath(*PurePosixPath(source_path).parts)
            metrics, count = build_font_directory(
                resolver,
                source_path,
                destination,
                script_chars,
                renderer,
                # A shadow-mounted ``*.fon`` directory replaces the original
                # font resource; it is not merged with it.  Keep the stock
                # Latin, digit, and punctuation glyphs alongside the added
                # Traditional-Chinese glyphs so presentations can render and
                # advance normally.
                copy_original=True,
                source_scale=2,
            )
            variant_report["shadow_fonts"][source_path] = {
                "metrics": {"width": metrics.width, "height": metrics.height},
                "generated_glyphs": count,
            }
        report[addon] = variant_report
    return report


def _write_metadata(
    trees_root: Path,
    plans: dict[str, VariantPlan],
    font_path: Path,
    font_report: dict[str, dict[str, Any]],
    menu_report: dict[str, dict[str, object]],
) -> None:
    for addon, plan in plans.items():
        metadata = {
            "locale": "zh-TW",
            "addon": addon,
            "source_font": font_path.name,
            "source_font_weight": FONT_WEIGHT,
            "font_supersampling": FONT_SUPERSAMPLE,
            "rmp_entries": len(plan.rmp_entries),
            "fonts": font_report[addon],
            "main_menu": menu_report[addon],
            "font_notice": (
                "Glyphs were rasterized from Noto Sans TC. Preserve and review the SIL Open Font "
                "License before redistributing this package."
            ),
        }
        path = trees_root / addon / "LOCALIZATION-METADATA.json"
        path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def _zip_tree(
    source: Path,
    destination: Path,
    *,
    include_root: bool = True,
    compresslevel: int = 1,
) -> int:
    if not 0 <= compresslevel <= 9:
        raise LocError(f"ZIP compression level must be between 0 and 9: {compresslevel}")
    files = sorted(path for path in source.rglob("*") if path.is_file())
    if len(files) >= 65535:
        raise LocError(
            f"{source.name} has {len(files)} files; UQM rejects ZIP64 and supports fewer than 65535"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        # The payload is dominated by already-compressed PNG glyphs. Deflate
        # level 9 adds many minutes on older CPUs for negligible size savings;
        # level 1 remains deterministic and compatible with UQM's ZIP reader.
        compresslevel=compresslevel,
        allowZip64=False,
    ) as archive:
        for path in files:
            base = source.parent if include_root else source
            relative = path.relative_to(base).as_posix()
            # UQM mounts the shadow archive from inside the outer add-on ZIP.
            # Deflating that nested archive makes the legacy ZIP backend
            # reinflate it repeatedly for backward seeks.  Store archive
            # members directly; their own contents remain compressed.
            compression = (
                zipfile.ZIP_STORED
                if path.suffix.lower() in {".uqm", ".zip"}
                else zipfile.ZIP_DEFLATED
            )
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = compression
            info.external_attr = 0o100644 << 16
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=compression,
                compresslevel=(
                    compresslevel if compression == zipfile.ZIP_DEFLATED else None
                ),
            )
    return len(files)


def _write_shadow_archives(
    trees_root: Path,
    shadow_trees_root: Path,
    plans: dict[str, VariantPlan],
) -> dict[str, int]:
    """Package shadow overrides in the nested archive format UQM actually mounts.

    UQM's prepareShadowAddons() opens an add-on's ``shadow-content`` directory
    and mounts only ``.zip``/``.uqm`` files found directly inside it. Ordinary
    ``shadow-content/base/...`` files are silently ignored.
    """
    counts: dict[str, int] = {}
    for addon in plans:
        source = shadow_trees_root / addon
        if not source.is_dir() or not any(path.is_file() for path in source.rglob("*")):
            raise LocError(f"{addon}: shadow override tree is empty")
        destination = trees_root / addon / "shadow-content" / f"{addon}-shadow.uqm"
        count = _zip_tree(source, destination, include_root=False)
        with zipfile.ZipFile(destination) as archive:
            names = archive.namelist()
            if archive.testzip() is not None:
                raise LocError(f"{addon}: generated shadow archive failed CRC validation")
            if not names or any(name.startswith(f"{addon}/") for name in names):
                raise LocError(f"{addon}: shadow archive paths must be rooted at base content")
        counts[addon] = count
    return counts


def _validate_built_paths(
    resolver: ContentResolver,
    trees_root: Path,
    plans: dict[str, VariantPlan],
) -> None:
    localized_prefixes = tuple(f"addons/{addon}/" for addon in plans)
    for addon, plan in plans.items():
        if len(plan.rmp_entries) != plan.expected_rmp_count:
            raise LocError(f"{addon}: RMP count changed after planning")
        for entry in plan.rmp_entries:
            path = entry.fields[0]
            if path.startswith(localized_prefixes):
                local = _tree_path(trees_root, path)
                if entry.resource_type == "FONTRES":
                    if not local.is_dir() or not any(local.glob("*.png")):
                        raise LocError(f"{addon}: mapped font does not exist: {path}")
                elif not local.is_file():
                    raise LocError(f"{addon}: mapped localized resource does not exist: {path}")
            elif entry.resource_type == "GFXRES":
                if not resolver.exists(path):
                    raise LocError(f"{addon}: stock graphics resource does not exist: {path}")
            if entry.resource_type == "CONVERSATION" and len(entry.fields) >= 3:
                if not resolver.exists(entry.fields[1]):
                    raise LocError(
                        f"{addon}: conversation voice directory does not exist: {entry.fields[1]}"
                    )
                if not resolver.exists(entry.fields[2]):
                    raise LocError(
                        f"{addon}: conversation timestamp file does not exist: {entry.fields[2]}"
                    )


def build_packages(
    content_root: Path,
    workspace: Path,
    output: Path,
    font_path: Path,
    menu_background: Path,
) -> dict[str, Any]:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise LocError(f"Build output must not exist or must be empty: {output}")
    _, documents = load_workspace(workspace)
    errors = validate_documents(documents)
    if errors:
        raise LocError("Workspace is invalid before build:\n" + "\n".join(errors[:100]))
    # Fail before creating a partial package when Pillow/the font is unavailable.
    renderer = NotoRenderer(
        font_path,
        weight=FONT_WEIGHT,
        supersample=FONT_SUPERSAMPLE,
    )
    output.mkdir(parents=True, exist_ok=True)
    trees_root = output / "trees"
    shadow_trees_root = output / "shadow-trees"
    packages_root = output / "packages"
    with ContentResolver(content_root) as resolver:
        manifest, _ = load_workspace(workspace)
        core_entries = parse_rmp(
            resolver.read_text(manifest["source_rmp"]), manifest["source_rmp"]
        )
        plans = make_variant_plans(core_entries, resolver)
        _write_text_trees(trees_root, shadow_trees_root, documents, core_entries)
        _write_rmps(trees_root, plans)
        font_report = _generate_fonts(
            resolver,
            trees_root,
            shadow_trees_root,
            plans,
            documents,
            core_entries,
            renderer,
        )
        menu_report = build_localized_main_menus(
            resolver, shadow_trees_root, menu_background, font_path
        )
        key_help_report = build_localized_key_help(
            resolver, shadow_trees_root, font_path
        )
        status_label_report = build_localized_status_labels(
            resolver, shadow_trees_root, font_path
        )
        super_melee_report = build_localized_super_melee_assets(
            resolver,
            shadow_trees_root,
            font_path,
            menu_background.parent / "super-melee",
        )
        ship_info_report = build_localized_ship_info_assets(
            resolver,
            shadow_trees_root,
            font_path,
        )
        for addon in menu_report:
            menu_report[addon]["key_help"] = key_help_report[addon]
            menu_report[addon]["combat_status_labels"] = status_label_report[addon]
            menu_report[addon]["super_melee"] = super_melee_report[addon]
            menu_report[addon]["super_melee"]["ship_picker"] = (
                ship_info_report[addon]["ship_picker"]
            )
            menu_report[addon]["super_melee"]["ship_info"] = (
                ship_info_report[addon]["ship_info"]
            )
        _write_metadata(trees_root, plans, font_path, font_report, menu_report)
        _validate_built_paths(resolver, trees_root, plans)
        shadow_counts = _write_shadow_archives(trees_root, shadow_trees_root, plans)
        package_counts = {
            addon: _zip_tree(trees_root / addon, packages_root / f"{addon}.uqm")
            for addon in plans
        }
    return {
        "output": str(output),
        "shadow_files": shadow_counts,
        "packages": {
            addon: {
                "path": str(packages_root / f"{addon}.uqm"),
                "files": package_counts[addon],
                "rmp_entries": plans[addon].expected_rmp_count,
            }
            for addon in plans
        },
    }
