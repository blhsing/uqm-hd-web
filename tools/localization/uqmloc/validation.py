from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .core import (
    MAX_ENGINE_LINE_BYTES,
    MAX_ENTRIES,
    LocError,
    load_workspace,
    parse_string_document,
    render_document,
)
from .wrapping import contains_cjk


_SETUP_FIXED_LINES_RE = re.compile(
    r"^(?:SUBTITLES|CHOICES|CAT_\d+_OPTS|SLIDERS|BUTTONS|LABELS|"
    r"TEXT_ENTRIES|TEXT_ENTRIES_INITIAL|CONTROL_ENTRIES)$"
)
_CREDITS_COLUMNS_RE = re.compile(
    r"^(\d+)[ \t]+([LCR](?:/\d+)?(?:,[LCR](?:/\d+)?)*)[ \t]*$"
)


def _error(errors: list[str], document: dict[str, Any], entry: dict[str, Any] | None, message: str) -> None:
    where = document["source_path"]
    if entry is not None:
        where += f" entry {entry['index']} #({entry['label']})"
    errors.append(f"{where}: {message}")


def _validate_translation(
    document: dict[str, Any],
    entry: dict[str, Any],
    errors: list[str],
    max_cjk_token: int,
) -> None:
    kind = entry["unit_kind"]
    translation = entry.get("translation")
    if kind == "immutable":
        if translation is not None:
            _error(errors, document, entry, "immutable script/format entry has a translation")
        return
    if not isinstance(translation, str):
        _error(errors, document, entry, "translation must be a JSON string")
        return
    source = entry.get("source") or ""
    if "\x00" in translation or "\r" in translation or "\ufeff" in translation:
        _error(errors, document, entry, "translation contains NUL, CR, or BOM")
    for line in translation.split("\n"):
        if line.startswith("#"):
            _error(errors, document, entry, "a text line starts with # and would become a new entry")
        for word in re.split(r"[ \t]+", line):
            if contains_cjk(word) and len(word) > max_cjk_token:
                _error(
                    errors,
                    document,
                    entry,
                    f"CJK word has {len(word)} characters; run wrap or keep <= {max_cjk_token}",
                )
                break
    if translation.count("$") != source.count("$"):
        _error(errors, document, entry, "the count of $ font-switch markers changed")
    for character in translation:
        if ord(character) > 0xFFFF:
            _error(
                errors,
                document,
                entry,
                f"U+{ord(character):X} is outside the engine font loader's BMP limit",
            )
            break
    if document["source_path"].lower().endswith("/ui/setupmenu.txt"):
        if _SETUP_FIXED_LINES_RE.fullmatch(entry["label"]):
            if translation.count("\n") != source.count("\n"):
                _error(errors, document, entry, "setup-menu list line count changed")
    if kind == "credits-text":
        layout = entry["body"].split("\n", 1)[0]
        match = _CREDITS_COLUMNS_RE.fullmatch(layout)
        if not match:
            _error(errors, document, entry, "credits layout prefix is malformed")
        else:
            columns = match.group(2).count(",") + 1
            for line_no, line in enumerate(translation.split("\n"), 1):
                if line.count("\t") >= columns:
                    _error(
                        errors,
                        document,
                        entry,
                        f"credits payload line {line_no} has more tab columns than its layout",
                    )


def _validate_ship_name_abbreviations(
    document: dict[str, Any], errors: list[str]
) -> None:
    """Keep localized ship-table short labels from losing CJK characters.

    Each stock ship string table stores the full race and vessel class at
    indices 0/3 and English space-saving variants at indices 2/4.  Han names
    are already compact, so carrying an English trailing full stop into the
    translation both looks like a missing glyph and needlessly truncates the
    name.  Requiring the localized short slots to reuse the full translation
    also keeps every UI path deterministic.
    """
    source_path = document["source_path"].replace("\\", "/").lower()
    entries = document.get("entries", [])
    if not source_path.startswith("base/ships/") or not source_path.endswith(".txt"):
        return
    if len(entries) < 5:
        return

    for full_index, short_index, kind in ((0, 2, "race"), (3, 4, "vessel")):
        full_entry = entries[full_index]
        short_entry = entries[short_index]
        full_translation = full_entry.get("translation")
        if (
            full_entry.get("source") != short_entry.get("source")
            and isinstance(full_translation, str)
            and contains_cjk(full_translation)
            and short_entry.get("translation") != full_translation
        ):
            _error(
                errors,
                document,
                short_entry,
                f"localized {kind} abbreviation must match the full CJK name "
                f"from entry {full_index}",
            )


def validate_documents(
    documents: Iterable[dict[str, Any]],
    *,
    max_cjk_token: int = 12,
) -> list[str]:
    errors: list[str] = []
    for document in documents:
        entries = document.get("entries", [])
        if not (1 <= len(entries) <= MAX_ENTRIES):
            _error(errors, document, None, f"entry count {len(entries)} is outside 1..{MAX_ENTRIES}")
        for expected_index, entry in enumerate(entries):
            if entry.get("index") != expected_index:
                _error(errors, document, entry, "entry index/order changed")
            _validate_translation(document, entry, errors, max_cjk_token)
        _validate_ship_name_abbreviations(document, errors)
        try:
            rendered = render_document(document)
        except LocError as exc:
            errors.append(str(exc))
            continue
        if rendered.startswith(b"\xef\xbb\xbf"):
            _error(errors, document, None, "rendered file has a UTF-8 BOM")
        for line_number, line in enumerate(rendered.splitlines(keepends=True), 1):
            if len(line) > MAX_ENGINE_LINE_BYTES:
                _error(
                    errors,
                    document,
                    None,
                    f"physical line {line_number} is {len(line)} bytes; engine maximum is {MAX_ENGINE_LINE_BYTES}",
                )
        try:
            reparsed = parse_string_document(
                rendered,
                document["source_path"],
                document["resource_ids"],
                document["resource_types"],
                auxiliary=document.get("auxiliary", False),
            )
        except LocError as exc:
            errors.append(str(exc))
            continue
        if len(reparsed["entries"]) != len(entries):
            _error(errors, document, None, "rendered entry count changed")
            continue
        for old, new in zip(entries, reparsed["entries"]):
            if (old["label"], old["header_suffix"], old["audio"]) != (
                new["label"],
                new["header_suffix"],
                new["audio"],
            ):
                _error(errors, document, old, "rendering changed label or audio metadata")
    return errors


def validate_workspace(workspace: Path, *, max_cjk_token: int = 12) -> tuple[int, int]:
    _, documents = load_workspace(workspace)
    errors = validate_documents(documents, max_cjk_token=max_cjk_token)
    if errors:
        preview = "\n".join(f"- {item}" for item in errors[:100])
        remainder = len(errors) - min(100, len(errors))
        if remainder:
            preview += f"\n- ... {remainder} more error(s)"
        raise LocError(f"Localization validation failed ({len(errors)} error(s)):\n{preview}")
    return len(documents), sum(len(document["entries"]) for document in documents)
