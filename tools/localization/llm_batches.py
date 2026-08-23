#!/usr/bin/env python3
"""Split UQM records into document-stable LLM batches and combine responses."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


NEWLINE_RE = re.compile(r"\r\n|\r|\n")
PROTECTED_RE = re.compile(
    r"%(?:\([^)\r\n]+\))?(?:\d+\$)?[-+#0']*(?:\d+|\*)?"
    r"(?:\.(?:\d+|\*))?(?:hh|h|ll|l|L|z|j|t)?[diuoxXfFeEgGaAcspn%]"
    r"|\{\{[^{}\r\n]+\}\}|\$\{[A-Za-z_][A-Za-z0-9_.:-]*\}"
    r"|\{[A-Za-z_][A-Za-z0-9_.:-]*(?:![rsa])?(?::[^{}\r\n]+)?\}"
    r"|\$[A-Z_][A-Z0-9_]*|\\(?:[nrtbfv\\'\"0]|x[0-9A-Fa-f]{2}|u[0-9A-Fa-f]{4})"
    r"|&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);"
)


def load_records(path: Path) -> list[dict[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, dict):
        value = value.get("records")
    if not isinstance(value, list):
        raise ValueError(f"{path}: expected a JSON record array")
    rows: list[dict[str, str]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not isinstance(row.get("text"), str):
            raise ValueError(f"{path}: invalid record {index}")
        rows.append({"id": row["id"], "text": row["text"]})
    return rows


def split(args: argparse.Namespace) -> None:
    rows = load_records(args.input)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    order: dict[str, int] = {}
    for index, row in enumerate(rows):
        source_path = row["id"].rsplit("::", 1)[0]
        grouped[source_path].append(row)
        order.setdefault(source_path, index)

    bins: list[dict[str, object]] = [{"chars": 0, "paths": []} for _ in range(args.count)]
    groups = sorted(grouped.items(), key=lambda item: sum(len(row["text"]) for row in item[1]), reverse=True)
    for source_path, group_rows in groups:
        target = min(bins, key=lambda item: int(item["chars"]))
        target["paths"].append(source_path)
        target["chars"] = int(target["chars"]) + sum(len(row["text"]) for row in group_rows)

    args.output.mkdir(parents=True, exist_ok=True)
    output_dir = args.output / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for number, bin_info in enumerate(bins, 1):
        paths = sorted(bin_info["paths"], key=lambda path: order[path])
        path_set = set(paths)
        batch_rows = [row for row in rows if row["id"].rsplit("::", 1)[0] in path_set]
        name = f"batch{number:02d}.json"
        destination = args.output / name
        if destination.exists() and not args.force:
            raise FileExistsError(f"refusing to replace {destination}; use --force")
        payload = {
            "format": "uqm-llm-translation-batch-v1",
            "batch": f"batch{number:02d}",
            "source_characters": sum(len(row["text"]) for row in batch_rows),
            "source_paths": paths,
            "records": batch_rows,
        }
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        manifest.append({
            "batch": payload["batch"],
            "input": name,
            "output": f"output/{name}",
            "records": len(batch_rows),
            "source_characters": payload["source_characters"],
            "source_paths": paths,
        })
    (args.output / "manifest.json").write_text(
        json.dumps({"format": "uqm-llm-batch-manifest-v1", "batches": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"split {len(rows)} records into {len(manifest)} document-stable batches")
    for item in manifest:
        print(f"{item['batch']}: records={item['records']} chars={item['source_characters']}")


def structural_signature(text: str) -> tuple[object, ...]:
    return (
        NEWLINE_RE.findall(text),
        text.count("\t"),
        text.count("<"),
        text.count(">"),
        PROTECTED_RE.findall(text),
    )


def validate_batch(args: argparse.Namespace) -> None:
    source_rows = load_records(args.source)
    response_rows = load_records(args.response)
    if [row["id"] for row in source_rows] != [row["id"] for row in response_rows]:
        raise ValueError("response IDs/order do not exactly match the source batch")
    errors = [
        source["id"]
        for source, response in zip(source_rows, response_rows)
        if structural_signature(source["text"]) != structural_signature(response["text"])
    ]
    if errors:
        raise ValueError(f"protected structure changed in {len(errors)} records (first: {errors[0]})")
    print(f"validated {len(response_rows)} translated records in {args.response}")


def combine(args: argparse.Namespace) -> None:
    source_rows = load_records(args.source)
    source = {row["id"]: row["text"] for row in source_rows}
    manifest = json.loads((args.batches / "manifest.json").read_text(encoding="utf-8"))
    translated: dict[str, str] = {}
    errors: list[str] = []
    for item in manifest["batches"]:
        path = args.batches / item["output"]
        if not path.exists():
            errors.append(f"missing output: {path}")
            continue
        for row in load_records(path):
            record_id = row["id"]
            if record_id in translated:
                errors.append(f"duplicate id: {record_id}")
                continue
            if record_id not in source:
                errors.append(f"unexpected id: {record_id}")
                continue
            if structural_signature(source[record_id]) != structural_signature(row["text"]):
                errors.append(f"protected structure changed: {record_id}")
                continue
            translated[record_id] = row["text"]
    missing = [record_id for record_id in source if record_id not in translated]
    if missing:
        errors.append(f"missing ids: {len(missing)} (first: {missing[0]})")
    if errors:
        raise ValueError("\n".join(errors[:50]))
    ordered = [{"id": row["id"], "text": translated[row["id"]]} for row in source_rows]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"combined and structurally validated {len(ordered)} LLM translations into {args.output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    split_parser = commands.add_parser("split")
    split_parser.add_argument("--input", type=Path, required=True)
    split_parser.add_argument("--output", type=Path, required=True)
    split_parser.add_argument("--count", type=int, default=15)
    split_parser.add_argument("--force", action="store_true")
    split_parser.set_defaults(func=split)
    combine_parser = commands.add_parser("combine")
    combine_parser.add_argument("--source", type=Path, required=True)
    combine_parser.add_argument("--batches", type=Path, required=True)
    combine_parser.add_argument("--output", type=Path, required=True)
    combine_parser.set_defaults(func=combine)
    validate_parser = commands.add_parser("validate-batch")
    validate_parser.add_argument("--source", type=Path, required=True)
    validate_parser.add_argument("--response", type=Path, required=True)
    validate_parser.set_defaults(func=validate_batch)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
