from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator, Sequence


WORKSPACE_FORMAT = "uqm-hd-localization-v1"
TEXT_RESOURCE_TYPES = frozenset({"STRTAB", "CONVERSATION"})
MAX_ENTRIES = 2048
MAX_ENGINE_LINE_BYTES = 1023  # uio_fgets(char[1024]) must also fit the LF.


class LocError(RuntimeError):
    """A user-actionable localization pipeline error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def safe_resource_path(value: str) -> str:
    """Normalize a content path and reject traversal/absolute paths."""
    value = value.replace("\\", "/").strip()
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise LocError(f"Unsafe or empty content path: {value!r}")
    # UQM paths are relative and drive letters are never valid resource components.
    if ":" in path.parts[0]:
        raise LocError(f"Absolute content path is not allowed: {value!r}")
    return path.as_posix()


@dataclass(frozen=True)
class RmpEntry:
    resource_id: str
    resource_type: str
    fields: tuple[str, ...]
    line_number: int = 0

    def format(self) -> str:
        return f"{self.resource_id} = {self.resource_type}:{':'.join(self.fields)}"


_RMP_RE = re.compile(r"^\s*([^#][^=]*?)\s*=\s*([A-Za-z0-9_]+)\s*:(.*)$")


def parse_rmp(text: str, source: str = "<rmp>") -> list[RmpEntry]:
    if text.startswith("\ufeff"):
        raise LocError(f"{source}: UTF-8 BOM is not supported by the game")
    result: list[RmpEntry] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _RMP_RE.match(line)
        if not match:
            raise LocError(f"{source}:{line_no}: malformed resource-map line: {line!r}")
        resource_id, resource_type, raw_fields = match.groups()
        fields = tuple(field.strip() for field in raw_fields.split(":"))
        if not resource_id.strip() or not all(fields):
            raise LocError(f"{source}:{line_no}: empty resource id or data field")
        result.append(
            RmpEntry(resource_id.strip(), resource_type.upper(), fields, line_no)
        )
    return result


class ContentResolver:
    """Read UQM content from extracted files or the adjacent .uqm/.zip packages."""

    def __init__(self, content_root: Path | str):
        self.root = Path(content_root).resolve()
        if not self.root.is_dir():
            raise LocError(f"Content root is not a directory: {self.root}")
        self._archive_paths: list[Path] | None = None
        self._zip_handles: dict[Path, zipfile.ZipFile] = {}
        self._zip_names: dict[Path, tuple[str, ...]] = {}

    def close(self) -> None:
        for handle in self._zip_handles.values():
            handle.close()
        self._zip_handles.clear()
        self._zip_names.clear()

    def __enter__(self) -> "ContentResolver":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def archive_paths(self) -> list[Path]:
        if self._archive_paths is None:
            candidates: list[Path] = []
            for base in (self.root, self.root / "addons"):
                if base.is_dir():
                    for suffix in ("*.uqm", "*.zip"):
                        candidates.extend(base.glob(suffix))
            self._archive_paths = sorted({p.resolve() for p in candidates})
        return self._archive_paths

    def _zip(self, path: Path) -> zipfile.ZipFile:
        if path not in self._zip_handles:
            try:
                self._zip_handles[path] = zipfile.ZipFile(path)
            except (OSError, zipfile.BadZipFile) as exc:
                raise LocError(f"Cannot open content package {path}: {exc}") from exc
        return self._zip_handles[path]

    @staticmethod
    def _member_candidates(path: str) -> list[str]:
        path = safe_resource_path(path)
        candidates = [path]
        if path.startswith("addons/"):
            candidates.append(path[len("addons/") :])
        return list(dict.fromkeys(candidates))

    def read_bytes(self, resource_path: str) -> bytes:
        normalized = safe_resource_path(resource_path)
        direct = self.root.joinpath(*PurePosixPath(normalized).parts)
        if direct.is_file():
            return direct.read_bytes()
        for archive in self.archive_paths:
            handle = self._zip(archive)
            for member in self._member_candidates(normalized):
                try:
                    return handle.read(member)
                except KeyError:
                    pass
        raise LocError(f"Content resource was not found: {normalized}")

    def exists(self, resource_path: str) -> bool:
        normalized = safe_resource_path(resource_path)
        direct = self.root.joinpath(*PurePosixPath(normalized).parts)
        if direct.is_file() or direct.is_dir():
            return True
        for archive in self.archive_paths:
            handle = self._zip(archive)
            for member in self._member_candidates(normalized):
                try:
                    handle.getinfo(member)
                    return True
                except KeyError:
                    # ZIP directory entries are optional. Treat any member below
                    # the requested directory as proof that it exists.
                    member_name = PurePosixPath(member).name.lower()
                    if "." not in member_name or member_name.endswith(".fon"):
                        prefix = member.rstrip("/") + "/"
                        names = self._zip_names.setdefault(archive, tuple(handle.namelist()))
                        if any(name.startswith(prefix) for name in names):
                            return True
        return False

    def read_text(self, resource_path: str) -> str:
        raw = self.read_bytes(resource_path)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise LocError(f"{resource_path}: UTF-8 BOM would hide the first # label")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LocError(f"{resource_path}: not valid UTF-8: {exc}") from exc

    def list_files(self, resource_dir: str) -> dict[str, bytes]:
        """Return immediate regular files in a virtual content directory."""
        normalized = safe_resource_path(resource_dir).rstrip("/")
        result: dict[str, bytes] = {}
        direct = self.root.joinpath(*PurePosixPath(normalized).parts)
        if direct.is_dir():
            for item in direct.iterdir():
                if item.is_file():
                    result[item.name] = item.read_bytes()
        prefixes = [candidate.rstrip("/") + "/" for candidate in self._member_candidates(normalized)]
        for archive in self.archive_paths:
            handle = self._zip(archive)
            names = self._zip_names.setdefault(archive, tuple(handle.namelist()))
            for prefix in prefixes:
                for member in names:
                    if not member.startswith(prefix):
                        continue
                    tail = member[len(prefix) :]
                    if tail and "/" not in tail and not member.endswith("/") and tail not in result:
                        result[tail] = handle.read(member)
        return result

    def find_addon_rmp(self, addon_name: str) -> tuple[str, str]:
        addon_name = safe_resource_path(addon_name)
        candidates = (
            f"addons/{addon_name}/{addon_name}.rmp",
            f"{addon_name}/{addon_name}.rmp",
        )
        for candidate in candidates:
            try:
                return candidate, self.read_text(candidate)
            except LocError:
                continue
        raise LocError(
            f"Could not find {addon_name}.rmp in content/addons packages under {self.root}"
        )


_HEADER_RE = re.compile(r"(?m)^#\(([^)\r\n]*)\)([^\r\n]*)(\r\n|\n|\r|$)")
_TFI_RE = re.compile(r"^TFI(?:[ \t]+|$)")
_CREDITS_LAYOUT_RE = re.compile(
    r"^\d+[ \t]+[LCR](?:/\d+)?(?:,[LCR](?:/\d+)?)*(?:[ \t]*)$"
)
_SCRIPT_PATH_RE = re.compile(r"^base/cutscene/(?:intro|ending)/.*\.txt$", re.I)


def _split_trailing_newlines(value: str) -> tuple[str, str]:
    pos = len(value)
    while pos and value[pos - 1] in "\r\n":
        pos -= 1
    return value[:pos], value[pos:]


def _normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _detect_eol(text: str) -> str:
    match = re.search(r"\r\n|\n|\r", text)
    return match.group(0) if match else "\n"


def _audio_from_suffix(suffix: str) -> str | None:
    pieces = suffix.strip().split()
    return pieces[0] if pieces else None


def _entry_unit(path: str, body: str) -> tuple[str, int | None, str | None]:
    """Return (kind, payload_start, visible source)."""
    normalized = _normalize_newlines(body)
    if _SCRIPT_PATH_RE.match(path):
        match = _TFI_RE.match(normalized)
        if not match:
            return "immutable", None, None
        return "slideshow-tfi", match.end(), normalized[match.end() :]
    if path.lower().endswith("/cutscene/credits/credits.txt"):
        first, separator, rest = normalized.partition("\n")
        if separator and _CREDITS_LAYOUT_RE.fullmatch(first):
            return "credits-text", len(first) + 1, rest
        return "immutable", None, None
    return "whole", 0, normalized


def _entry_contract(entry: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "index",
        "label",
        "header_suffix",
        "audio",
        "header_eol",
        "body_suffix",
        "body",
        "unit_kind",
        "payload_start",
        "source",
    )
    return {key: entry.get(key) for key in keys}


def document_contract(document: dict[str, Any]) -> str:
    contract = {
        "format": document.get("format"),
        "source_path": document.get("source_path"),
        "resource_ids": document.get("resource_ids"),
        "resource_types": document.get("resource_types"),
        "auxiliary": document.get("auxiliary", False),
        "newline": document.get("newline"),
        "preamble": document.get("preamble"),
        "entries": [_entry_contract(entry) for entry in document.get("entries", [])],
    }
    return sha256_bytes(canonical_json(contract))


def parse_string_document(
    raw: bytes,
    source_path: str,
    resource_ids: Sequence[str],
    resource_types: Sequence[str],
    *,
    auxiliary: bool = False,
) -> dict[str, Any]:
    source_path = safe_resource_path(source_path)
    if raw.startswith(b"\xef\xbb\xbf"):
        raise LocError(f"{source_path}: BOM is forbidden because the first # would be hidden")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LocError(f"{source_path}: invalid UTF-8: {exc}") from exc
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        raise LocError(f"{source_path}: no #(label) entries found")
    entries: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body_raw, body_suffix = _split_trailing_newlines(text[match.end() : body_end])
        body = _normalize_newlines(body_raw)
        unit_kind, payload_start, visible_source = _entry_unit(source_path, body)
        header_suffix = match.group(2)
        entries.append(
            {
                "index": index,
                "label": match.group(1),
                "header_suffix": header_suffix,
                "audio": _audio_from_suffix(header_suffix),
                "header_eol": match.group(3) or _detect_eol(text),
                "body_suffix": body_suffix,
                "body": body,
                "unit_kind": unit_kind,
                "payload_start": payload_start,
                "source": visible_source,
                "translation": visible_source,
            }
        )
    document = {
        "format": WORKSPACE_FORMAT,
        "source_path": source_path,
        "resource_ids": sorted(set(resource_ids)),
        "resource_types": sorted(set(resource_types)),
        "auxiliary": auxiliary,
        "source_sha256": sha256_bytes(raw),
        "newline": _detect_eol(text),
        "preamble": text[: matches[0].start()],
        "entries": entries,
    }
    document["contract_sha256"] = document_contract(document)
    return document


def render_document(document: dict[str, Any]) -> bytes:
    eol = document.get("newline", "\n")
    if eol not in {"\n", "\r\n", "\r"}:
        raise LocError(f"{document.get('source_path')}: invalid newline marker")
    chunks = [document.get("preamble", "")]
    for entry in document.get("entries", []):
        label = entry["label"]
        chunks.append(f"#({label}){entry['header_suffix']}{entry['header_eol']}")
        kind = entry["unit_kind"]
        if kind == "immutable":
            body = entry["body"]
        else:
            translation = entry.get("translation")
            if not isinstance(translation, str):
                raise LocError(
                    f"{document.get('source_path')} entry {entry['index']}: translation must be text"
                )
            if kind == "whole":
                body = translation
            elif kind in {"slideshow-tfi", "credits-text"}:
                body = entry["body"][: entry["payload_start"]] + translation
            else:
                raise LocError(f"Unknown translation unit kind: {kind}")
        chunks.append(body.replace("\n", eol))
        chunks.append(entry["body_suffix"])
    try:
        return "".join(chunks).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise LocError(f"{document.get('source_path')}: cannot encode UTF-8: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_json(path: Path) -> Any:
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise LocError(f"{path}: JSON files must not have a UTF-8 BOM")
        return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        if isinstance(exc, LocError):
            raise
        raise LocError(f"Cannot read JSON {path}: {exc}") from exc


def _json_relative_path(source_path: str) -> str:
    return f"resources/{source_path}.json"


def _find_script_calls(document: dict[str, Any]) -> Iterator[str]:
    for entry in document["entries"]:
        for line in entry["body"].split("\n"):
            match = re.fullmatch(r"CALL[ \t]+([^ \t]+\.txt)[ \t]*", line)
            if match:
                yield safe_resource_path(match.group(1))


def export_workspace(content_root: Path, rmp_path: str, output: Path) -> dict[str, Any]:
    if output.exists() and any(output.iterdir()):
        raise LocError(f"Export output must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    with ContentResolver(content_root) as resolver:
        rmp_text = resolver.read_text(rmp_path)
        rmp_entries = parse_rmp(rmp_text, rmp_path)
        grouped: dict[str, dict[str, set[str]]] = {}
        for entry in rmp_entries:
            if entry.resource_type not in TEXT_RESOURCE_TYPES:
                continue
            source_path = safe_resource_path(entry.fields[0])
            group = grouped.setdefault(source_path, {"ids": set(), "types": set()})
            group["ids"].add(entry.resource_id)
            group["types"].add(entry.resource_type)

        documents: dict[str, dict[str, Any]] = {}
        pending = [(path, False) for path in sorted(grouped)]
        while pending:
            source_path, auxiliary = pending.pop(0)
            if source_path in documents:
                continue
            group = grouped.get(source_path, {"ids": set(), "types": {"SCRIPT"}})
            document = parse_string_document(
                resolver.read_bytes(source_path),
                source_path,
                sorted(group["ids"]),
                sorted(group["types"]),
                auxiliary=auxiliary,
            )
            documents[source_path] = document
            for dependency in _find_script_calls(document):
                if dependency not in documents:
                    pending.append((dependency, True))

        manifest_resources: list[dict[str, Any]] = []
        for source_path, document in sorted(documents.items()):
            relative_json = _json_relative_path(source_path)
            write_json(output / relative_json, document)
            manifest_resources.append(
                {
                    "source_path": source_path,
                    "json": relative_json,
                    "resource_ids": document["resource_ids"],
                    "resource_types": document["resource_types"],
                    "auxiliary": document["auxiliary"],
                    "entry_count": len(document["entries"]),
                    "contract_sha256": document["contract_sha256"],
                }
            )
        manifest = {
            "format": WORKSPACE_FORMAT,
            "source_rmp": safe_resource_path(rmp_path),
            "source_rmp_sha256": sha256_bytes(rmp_text.encode("utf-8")),
            "text_resource_count": len(grouped),
            "document_count": len(documents),
            "resources": manifest_resources,
        }
        write_json(output / "manifest.json", manifest)
        return manifest


def load_workspace(workspace: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = read_json(workspace / "manifest.json")
    if manifest.get("format") != WORKSPACE_FORMAT:
        raise LocError(f"{workspace}: unsupported or missing workspace format")
    documents: list[dict[str, Any]] = []
    for item in manifest.get("resources", []):
        json_path = safe_resource_path(item["json"])
        document = read_json(workspace.joinpath(*PurePosixPath(json_path).parts))
        if document.get("format") != WORKSPACE_FORMAT:
            raise LocError(f"{json_path}: unsupported document format")
        actual_contract = document_contract(document)
        expected_contract = item.get("contract_sha256")
        if actual_contract != expected_contract or document.get("contract_sha256") != expected_contract:
            raise LocError(
                f"{json_path}: immutable labels/audio/source/template changed; re-export instead"
            )
        if document.get("source_path") != item.get("source_path"):
            raise LocError(f"{json_path}: source path does not match manifest")
        documents.append(document)
    if len(documents) != manifest.get("document_count"):
        raise LocError("Workspace document count does not match manifest")
    return manifest, documents


def import_workspace(workspace: Path, output: Path) -> int:
    if output.exists() and any(output.iterdir()):
        raise LocError(f"Import output must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    _, documents = load_workspace(workspace)
    for document in documents:
        destination = output.joinpath(*PurePosixPath(document["source_path"]).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(render_document(document))
    return len(documents)


def iter_translations(documents: Iterable[dict[str, Any]]) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for document in documents:
        for entry in document["entries"]:
            if entry["unit_kind"] != "immutable":
                yield document, entry
