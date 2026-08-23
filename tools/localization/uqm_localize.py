#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from uqmloc.builder import build_packages
from uqmloc.core import LocError, export_workspace, import_workspace
from uqmloc.validation import validate_workspace
from uqmloc.wrapping import wrap_workspace
from uqmloc.translation_io import export_records, merge_records


DEFAULT_MENU_BACKGROUND = (
    Path(__file__).resolve().parents[2]
    / "localization"
    / "menu-assets"
    / "source"
    / "newgame4x-clean-imagegen.png"
)


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Traditional-Chinese localization pipeline for UQM HD Beta 1"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser(
        "export", help="export every uqm.rmp text entry to protected JSON"
    )
    export.add_argument("--content-root", type=_path, required=True)
    export.add_argument("--rmp", default="uqm.rmp", help="resource-map path under content root")
    export.add_argument("--output", type=_path, required=True)

    import_cmd = subparsers.add_parser(
        "import", help="rebuild UTF-8 .txt resources from a translated workspace"
    )
    import_cmd.add_argument("--workspace", type=_path, required=True)
    import_cmd.add_argument("--output", type=_path, required=True)

    bundle = subparsers.add_parser(
        "bundle", help="export editable units as flat {id,text} JSON/JSONL records"
    )
    bundle.add_argument("--workspace", type=_path, required=True)
    bundle.add_argument("--output", type=_path, required=True)
    bundle.add_argument(
        "--jsonl", action="store_true", help="write one JSON object per line instead of an array"
    )

    merge = subparsers.add_parser(
        "merge", help="merge returned {id,text} records into a protected workspace"
    )
    merge.add_argument("--workspace", type=_path, required=True)
    merge.add_argument("--response", type=_path, required=True)
    merge_destination = merge.add_mutually_exclusive_group(required=True)
    merge_destination.add_argument("--output", type=_path)
    merge_destination.add_argument("--in-place", action="store_true")
    merge.add_argument("--allow-partial", action="store_true")

    validate = subparsers.add_parser(
        "validate", help="validate labels, audio, scripts, UTF-8, line sizes, and CJK breaks"
    )
    validate.add_argument("--workspace", type=_path, required=True)
    validate.add_argument("--max-cjk-token", type=int, default=12)

    wrap = subparsers.add_parser(
        "wrap", help="insert ASCII engine break opportunities in Traditional-Chinese text"
    )
    wrap.add_argument("--workspace", type=_path, required=True)
    destination = wrap.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=_path)
    destination.add_argument("--in-place", action="store_true")
    wrap.add_argument("--max-cjk-token", type=int, default=12)
    wrap.add_argument(
        "--max-line-bytes",
        type=int,
        default=900,
        help="hard-wrap below the engine's 1023-byte physical-line ceiling",
    )
    wrap.add_argument(
        "--all-text",
        action="store_true",
        help="also wrap non-conversation payloads (normally only dialogue is touched)",
    )

    build = subparsers.add_parser(
        "build", help="build the native-1080p supersampled Traditional Chinese .uqm package"
    )
    build.add_argument("--content-root", type=_path, required=True)
    build.add_argument("--workspace", type=_path, required=True)
    build.add_argument("--output", type=_path, required=True)
    build.add_argument(
        "--font",
        type=_path,
        default=_path(r"C:\Windows\Fonts\NotoSansTC-VF.ttf"),
        help="Noto Sans TC TrueType/variable-TrueType font used for supersampled glyphs",
    )
    build.add_argument(
        "--menu-background",
        type=_path,
        default=DEFAULT_MENU_BACKGROUND,
        help="clean 4:3 restart-menu background used for exact zh-TW labels",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export":
        manifest = export_workspace(args.content_root, args.rmp, args.output)
        print(
            f"Exported {manifest['text_resource_count']} mapped text resources "
            f"as {manifest['document_count']} protected documents to {args.output}"
        )
    elif args.command == "import":
        count = import_workspace(args.workspace, args.output)
        print(f"Imported {count} documents to {args.output}")
    elif args.command == "bundle":
        count = export_records(args.workspace, args.output, json_lines=args.jsonl)
        print(f"Exported {count} protected translation records to {args.output}")
    elif args.command == "merge":
        target, count = merge_records(
            args.workspace,
            args.response,
            output=args.output,
            in_place=args.in_place,
            allow_partial=args.allow_partial,
        )
        print(f"Merged {count} translation records into {target}")
    elif args.command == "validate":
        documents, entries = validate_workspace(
            args.workspace, max_cjk_token=args.max_cjk_token
        )
        print(f"Validated {documents} documents and {entries} entries")
    elif args.command == "wrap":
        target, changed = wrap_workspace(
            args.workspace,
            output=args.output,
            in_place=args.in_place,
            max_cjk_token=args.max_cjk_token,
            max_line_bytes=args.max_line_bytes,
            all_text=args.all_text,
        )
        print(f"Wrapped {changed} translated entries in {target}")
    elif args.command == "build":
        report = build_packages(
            args.content_root,
            args.workspace,
            args.output,
            args.font,
            args.menu_background,
        )
        for addon, item in report["packages"].items():
            print(
                f"Built {addon}: {item['rmp_entries']} RMP mappings, "
                f"{item['files']} files -> {item['path']}"
            )
    else:  # pragma: no cover - argparse enforces a known command.
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LocError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
