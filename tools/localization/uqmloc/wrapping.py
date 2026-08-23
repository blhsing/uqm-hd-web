from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from .core import LocError, load_workspace, safe_resource_path, write_json


CJK_RANGES = (
    (0x2E80, 0x2FFF),
    (0x3000, 0x303F),
    (0x3040, 0x30FF),
    (0x3100, 0x312F),
    (0x31A0, 0x31BF),
    (0x31F0, 0x31FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xF900, 0xFAFF),
    (0xFE30, 0xFE4F),
    (0xFF00, 0xFFEF),
)
OPENING_PUNCTUATION = frozenset("（［｛「『《〈【〔〖〘〚“‘")
CLOSING_PUNCTUATION = frozenset("）］｝」』》〉】〕〗〙〛，。！？；：、…,.!?;:%％")
NATURAL_BREAK_AFTER = frozenset("，。！？；：、…,.!?;:")


def is_cjk(character: str) -> bool:
    codepoint = ord(character)
    return any(start <= codepoint <= end for start, end in CJK_RANGES)


def contains_cjk(text: str) -> bool:
    return any(is_cjk(character) for character in text)


def _choose_chunk_end(token: str, start: int, limit: int) -> int:
    hard_end = min(len(token), start + limit)
    if hard_end == len(token):
        return hard_end
    # Prefer a natural punctuation boundary in the latter half of the chunk.
    preferred = None
    for pos in range(start + max(1, limit // 2), hard_end):
        if token[pos] in NATURAL_BREAK_AFTER:
            preferred = pos + 1
    end = preferred or hard_end
    # Do not strand opening punctuation or start the next word with closing marks.
    # Keep the hard limit: move the break left so the next chunk begins with a
    # regular character followed by the closing mark, rather than absorbing the
    # closing mark into an over-limit chunk.
    while end > start + 1 and token[end - 1] in OPENING_PUNCTUATION:
        end -= 1
    while end < len(token) and token[end] in CLOSING_PUNCTUATION and end > start + 1:
        end -= 1
    return max(start + 1, end)


def split_cjk_token(token: str, max_characters: int) -> str:
    """Insert ASCII break spaces so the engine never sees one huge CJK word."""
    if max_characters < 2:
        raise LocError("CJK token limit must be at least 2")
    if not contains_cjk(token) or len(token) <= max_characters:
        return token
    chunks: list[str] = []
    start = 0
    while start < len(token):
        end = _choose_chunk_end(token, start, max_characters)
        chunks.append(token[start:end])
        start = end
    return " ".join(chunks)


def add_engine_breaks(text: str, max_cjk_token: int) -> str:
    output: list[str] = []
    # Preserve existing spaces/tabs exactly; they may be intentional dialogue markup.
    for piece in re.split(r"([ \t]+)", text):
        if piece and not piece.isspace():
            output.append(split_cjk_token(piece, max_cjk_token))
        else:
            output.append(piece)
    return "".join(output)


def _split_line_by_bytes(line: str, max_bytes: int) -> list[str]:
    if len(line.encode("utf-8")) <= max_bytes:
        return [line]
    result: list[str] = []
    remaining = line
    while len(remaining.encode("utf-8")) > max_bytes:
        used = 0
        last_space = -1
        end = 0
        for index, character in enumerate(remaining):
            width = len(character.encode("utf-8"))
            if used + width > max_bytes:
                break
            used += width
            end = index + 1
            if character == " ":
                last_space = index
        if last_space > 0:
            result.append(remaining[:last_space].rstrip(" "))
            remaining = remaining[last_space + 1 :].lstrip(" ")
        elif end > 0:
            result.append(remaining[:end])
            remaining = remaining[end:]
        else:  # max_bytes cannot hold even one encoded codepoint.
            raise LocError(f"Physical-line byte limit {max_bytes} is too small")
    result.append(remaining)
    return result


def hard_wrap_physical_lines(text: str, max_bytes: int) -> str:
    lines: list[str] = []
    for line in text.split("\n"):
        lines.extend(_split_line_by_bytes(line, max_bytes))
    return "\n".join(lines)


def wrap_translation(text: str, max_cjk_token: int, max_line_bytes: int) -> str:
    pieces = []
    for line in text.split("\n"):
        pieces.append(add_engine_breaks(line, max_cjk_token))
    return hard_wrap_physical_lines("\n".join(pieces), max_line_bytes)


def wrap_workspace(
    workspace: Path,
    *,
    output: Path | None,
    in_place: bool,
    max_cjk_token: int,
    max_line_bytes: int,
    all_text: bool = False,
) -> tuple[Path, int]:
    if in_place and output is not None:
        raise LocError("Use either --in-place or --output, not both")
    if not in_place and output is None:
        raise LocError("wrap requires --output unless --in-place is selected")
    if in_place:
        target = workspace
    else:
        assert output is not None
        target = output
    if not in_place:
        if target.exists():
            if any(target.iterdir()) if target.is_dir() else True:
                raise LocError(f"Wrap output must not exist or must be empty: {target}")
            target.rmdir()
        shutil.copytree(workspace, target)
    _, documents = load_workspace(target)
    changed = 0
    for document in documents:
        is_conversation = "CONVERSATION" in document["resource_types"]
        if not all_text and not is_conversation:
            continue
        for entry in document["entries"]:
            if entry["unit_kind"] == "immutable" or not isinstance(entry.get("translation"), str):
                continue
            before = entry["translation"]
            after = wrap_translation(before, max_cjk_token, max_line_bytes)
            if after != before:
                entry["translation"] = after
                changed += 1
        relative = f"resources/{safe_resource_path(document['source_path'])}.json"
        write_json(target.joinpath(*PurePosixPath(relative).parts), document)
    return target, changed


def is_renderable_character(character: str) -> bool:
    category = unicodedata.category(character)
    return not character.isspace() and not category.startswith("C")
