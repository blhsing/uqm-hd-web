from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from patch_uqm_hd_super_melee_escape import (
    LEGACY_V1_SHA256,
    LEGACY_V2_SHA256,
    LEGACY_V3_SHA256,
    PATCHED_SHA256,
    patch_file,
    sha256_bytes,
)


MARKER_NAME = ".uqm-hd-zh-tw-install.json"
PRODUCT_ID = "uqm-hd-zh-tw"


def _write_json_atomic(path: Path, value: object) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(payload)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def update_install(install_root: Path) -> bool:
    install_root = install_root.resolve()
    marker_path = install_root / MARKER_NAME
    marker = json.loads(marker_path.read_text(encoding="utf-8-sig"))

    if marker.get("SchemaVersion") != 1:
        raise ValueError("unsupported install marker schema")
    if marker.get("ProductId") != PRODUCT_ID or marker.get("State") != "complete":
        raise ValueError("target is not a complete UQM-HD zh-TW managed installation")
    if Path(marker.get("InstallRoot", "")).resolve() != install_root:
        raise ValueError("marker InstallRoot does not match the requested installation")
    if marker.get("Executable") != "uqm.exe":
        raise ValueError("marker does not identify the expected executable")

    matches = [entry for entry in marker.get("Files", []) if entry.get("Path") == "uqm.exe"]
    if len(matches) != 1:
        raise ValueError("marker must contain exactly one uqm.exe manifest entry")
    entry = matches[0]
    executable = install_root / "uqm.exe"
    before = sha256_bytes(executable.read_bytes())
    recorded = str(entry.get("Sha256", "")).lower()
    supported_hashes = {
        LEGACY_V1_SHA256,
        LEGACY_V2_SHA256,
        LEGACY_V3_SHA256,
        PATCHED_SHA256,
    }
    if before not in supported_hashes:
        raise ValueError(f"installed uqm.exe has an unsupported SHA-256: {before}")
    if recorded not in supported_hashes:
        raise ValueError(f"manifest records an unsupported uqm.exe SHA-256: {recorded}")
    if before != recorded and not (
        before == PATCHED_SHA256
        and recorded in {LEGACY_V1_SHA256, LEGACY_V2_SHA256, LEGACY_V3_SHA256}
    ):
        raise ValueError("installed uqm.exe and its managed manifest entry disagree")

    executable_changed = patch_file(executable)
    after = sha256_bytes(executable.read_bytes())
    if after != PATCHED_SHA256:
        raise ValueError("installed uqm.exe did not reach the verified final SHA-256")

    marker_changed = recorded != PATCHED_SHA256 or entry.get("Length") != executable.stat().st_size
    if marker_changed:
        entry["Length"] = executable.stat().st_size
        entry["Sha256"] = PATCHED_SHA256
        marker["UpdatedAtUtc"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _write_json_atomic(marker_path, marker)

    return executable_changed or marker_changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upgrade a managed UQM-HD zh-TW installation to the final Super Melee Escape patch."
    )
    parser.add_argument("install_root", type=Path)
    args = parser.parse_args()
    changed = update_install(args.install_root)
    print("updated" if changed else "already-current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
