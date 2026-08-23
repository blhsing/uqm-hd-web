from __future__ import annotations

import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, Iterator

from .core import LocError, load_workspace, safe_resource_path, write_json


def translation_id(document: dict[str, Any], entry: dict[str, Any]) -> str:
    # Unpadded decimal indices match the original records.en.json convention.
    return f"{document['source_path']}::{entry['index']}"


def _translation_aliases(document: dict[str, Any], entry: dict[str, Any]) -> tuple[str, ...]:
    canonical = translation_id(document, entry)
    padded = f"{document['source_path']}::{entry['index']:04d}"
    return (canonical,) if padded == canonical else (canonical, padded)


def iter_records(documents: list[dict[str, Any]]) -> Iterator[dict[str, str]]:
    for document in documents:
        for entry in document["entries"]:
            text = entry.get("translation")
            if entry["unit_kind"] != "immutable" and isinstance(text, str):
                yield {"id": translation_id(document, entry), "text": text}


def export_records(workspace: Path, output: Path, *, json_lines: bool) -> int:
    _, documents = load_workspace(workspace)
    records = list(iter_records(documents))
    output.parent.mkdir(parents=True, exist_ok=True)
    if json_lines:
        payload = "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        )
    else:
        payload = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    output.write_text(payload, encoding="utf-8", newline="\n")
    return len(records)


def _load_records(path: Path) -> list[dict[str, Any]]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise LocError(f"{path}: translation response must not contain a UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LocError(f"{path}: translation response is not UTF-8: {exc}") from exc
    try:
        if path.suffix.lower() == ".jsonl":
            records = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            records = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LocError(f"{path}: malformed JSON response: {exc}") from exc
    if not isinstance(records, list):
        raise LocError(f"{path}: expected a JSON array or JSONL records")
    return records


def _copy_workspace(workspace: Path, output: Path | None, in_place: bool) -> Path:
    if in_place and output is not None:
        raise LocError("Use either --in-place or --output, not both")
    if not in_place and output is None:
        raise LocError("merge requires --output unless --in-place is selected")
    if in_place:
        return workspace
    assert output is not None
    target = output
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise LocError(f"Merge output must not exist or must be empty: {target}")
        target.rmdir()
    shutil.copytree(workspace, target)
    return target


def merge_records(
    workspace: Path,
    response: Path,
    *,
    output: Path | None,
    in_place: bool,
    allow_partial: bool,
) -> tuple[Path, int]:
    target = _copy_workspace(workspace, output, in_place)
    _, documents = load_workspace(target)
    expected: dict[str, tuple[str, dict[str, Any], dict[str, Any]]] = {}
    canonical_ids: set[str] = set()
    for document in documents:
        for entry in document["entries"]:
            if entry["unit_kind"] != "immutable" and isinstance(entry.get("translation"), str):
                canonical = translation_id(document, entry)
                canonical_ids.add(canonical)
                for alias in _translation_aliases(document, entry):
                    expected[alias] = (canonical, document, entry)
    response_records = _load_records(response)
    seen: set[str] = set()
    seen_canonical: set[str] = set()
    touched_documents: dict[str, dict[str, Any]] = {}
    for record_number, record in enumerate(response_records, 1):
        if not isinstance(record, dict):
            raise LocError(f"Response record {record_number} is not an object")
        record_id = record.get("id")
        text = record.get("text")
        if not isinstance(record_id, str) or not isinstance(text, str):
            raise LocError(f"Response record {record_number} requires string id and text fields")
        if record_id in seen:
            raise LocError(f"Duplicate response id: {record_id}")
        seen.add(record_id)
        if record_id not in expected:
            raise LocError(f"Unknown or immutable response id: {record_id}")
        canonical, document, entry = expected[record_id]
        if canonical in seen_canonical:
            raise LocError(
                f"Response contains two aliases for the same translation unit: {canonical}"
            )
        seen_canonical.add(canonical)
        entry["translation"] = text
        touched_documents[document["source_path"]] = document
    missing = sorted(canonical_ids - seen_canonical)
    if missing and not allow_partial:
        raise LocError(
            f"Translation response is missing {len(missing)} record(s); first: {missing[:5]}. "
            "Use --allow-partial only for an intentional batch merge."
        )
    for source_path, document in touched_documents.items():
        relative = f"resources/{safe_resource_path(source_path)}.json"
        write_json(target.joinpath(*PurePosixPath(relative).parts), document)
    return target, len(seen)
