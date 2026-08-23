from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile


# This patch is deliberately chained after patch_uqm_hd_menu_highlight.py.  It
# accepts only the exact already-localized Beta 1 executable and is therefore
# unable to alter an unknown build accidentally.
ORIGINAL_SHA256 = "638a9ae53678df63fcf1cd43ffe48e62446f094c67ab730c5c11a02a6ef86907"
LEGACY_V1_SHA256 = (
    "40e99978b96f3ec3b75d9acd5ba6308be21b0f0986362b144afd97ef9f380ac0"
)
LEGACY_V2_SHA256 = "1af8f5fdcefd18b59cc14007a7ca9a98f5317bebf6f4ac46a29fa28086de5214"
LEGACY_V3_SHA256 = "425b175a4da3d5a93dc238e0d545ebb5f63abf0abe8441b515d5b3b30f94c419"
PATCHED_SHA256 = "3d2174f5dab4ce9b7a2dcd0eec7c59473f543239953b18664c51fff631f36bc9"

HOOK_OFFSET = 0x60977
CAVE_OFFSET = 0x7329E
PE_CHECKSUM_OFFSET = 0x170

ORIGINAL_HOOK = bytes.fromhex("8B 46 10 C6 46 27 00")
PATCHED_HOOK = bytes.fromhex("E9 22 29 01 00 90 90")
ORIGINAL_CAVE = bytes([0xCC]) * 50
LEGACY_V1_CAVE_PREFIX = bytes.fromhex(
    "E8 00 00 00 00 "
    "58 "
    "80 B8 DD A6 0C 00 00 "
    "75 0F "
    "F6 45 FC 20 "
    "74 09 "
    "66 81 88 DD A6 0C 00 00 40 "
    "8B 46 10 "
    "C6 46 27 00 "
    "E9 B6 D6 FE FF"
)
LEGACY_V1_CAVE = LEGACY_V1_CAVE_PREFIX + bytes([0xCC]) * (
    len(ORIGINAL_CAVE) - len(LEGACY_V1_CAVE_PREFIX)
)
LEGACY_V2_CAVE_PREFIX = bytes.fromhex(
    "E8 00 00 00 00 "
    "58 "
    "80 B8 DD A6 0C 00 00 "
    "75 12 "
    "83 B8 4D A9 0C 00 00 "
    "74 09 "
    "66 81 88 DD A6 0C 00 00 40 "
    "8B 46 10 "
    "C6 46 27 00 "
    "E9 B3 D6 FE FF"
)
LEGACY_V2_CAVE = LEGACY_V2_CAVE_PREFIX + bytes([0xCC]) * (
    len(ORIGINAL_CAVE) - len(LEGACY_V2_CAVE_PREFIX)
)
LEGACY_V3_CAVE_PREFIX = bytes.fromhex(
    "E8 00 00 00 00 "
    "58 "
    "80 B8 DD A6 0C 00 00 "
    "75 12 "
    "83 B8 4D A9 0C 00 00 "
    "74 09 "
    "66 81 A0 DD A6 0C 00 FF FD "
    "8B 46 10 "
    "C6 46 27 00 "
    "E9 B3 D6 FE FF"
)
LEGACY_V3_CAVE = LEGACY_V3_CAVE_PREFIX + bytes([0xCC]) * (
    len(ORIGINAL_CAVE) - len(LEGACY_V3_CAVE_PREFIX)
)
PATCHED_CAVE_PREFIX = bytes.fromhex(
    "E8 00 00 00 00 "
    "58 "
    "80 B8 DD A6 0C 00 00 "
    "75 12 "
    "83 B8 75 A9 0C 00 00 "
    "74 09 "
    "66 81 A0 DD A6 0C 00 FF FD "
    "8B 46 10 "
    "C6 46 27 00 "
    "E9 B3 D6 FE FF"
)
PATCHED_CAVE = PATCHED_CAVE_PREFIX + bytes([0xCC]) * (
    len(ORIGINAL_CAVE) - len(PATCHED_CAVE_PREFIX)
)
ORIGINAL_PE_CHECKSUM = bytes.fromhex("C7 92 13 00")
LEGACY_V1_PE_CHECKSUM = bytes.fromhex("53 E3 12 00")
LEGACY_V2_PE_CHECKSUM = bytes.fromhex("E6 CE 13 00")
LEGACY_V3_PE_CHECKSUM = bytes.fromhex("BC CE 13 00")
PATCHED_PE_CHECKSUM = bytes.fromhex("BD F6 12 00")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_at(data: bytes, signature: bytes, offset: int, description: str) -> None:
    if data.count(signature) != 1 or data.find(signature) != offset:
        raise ValueError(f"{description} is not unique at its verified file offset")


def patched_bytes(data: bytes) -> tuple[bytes, bool]:
    digest = sha256_bytes(data)
    if digest == PATCHED_SHA256:
        _unique_at(data, PATCHED_HOOK, HOOK_OFFSET, "patched Escape hook")
        _unique_at(data, PATCHED_CAVE, CAVE_OFFSET, "patched Escape code cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != PATCHED_PE_CHECKSUM:
            raise ValueError("patched PE checksum does not match the verified executable")
        return data, False
    if digest not in {
        ORIGINAL_SHA256,
        LEGACY_V1_SHA256,
        LEGACY_V2_SHA256,
        LEGACY_V3_SHA256,
    }:
        raise ValueError(f"unsupported uqm.exe SHA-256: {digest}")

    if digest == ORIGINAL_SHA256:
        _unique_at(data, ORIGINAL_HOOK, HOOK_OFFSET, "original input hook")
        _unique_at(data, ORIGINAL_CAVE, CAVE_OFFSET, "original INT3 code cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != ORIGINAL_PE_CHECKSUM:
            raise ValueError("original PE checksum does not match the verified executable")
    elif digest == LEGACY_V1_SHA256:
        _unique_at(data, PATCHED_HOOK, HOOK_OFFSET, "legacy v1 Escape hook")
        _unique_at(data, LEGACY_V1_CAVE, CAVE_OFFSET, "legacy v1 Escape code cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != LEGACY_V1_PE_CHECKSUM:
            raise ValueError("legacy v1 PE checksum does not match the verified executable")
    elif digest == LEGACY_V2_SHA256:
        _unique_at(data, PATCHED_HOOK, HOOK_OFFSET, "legacy v2 Escape hook")
        _unique_at(data, LEGACY_V2_CAVE, CAVE_OFFSET, "legacy v2 Escape code cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != LEGACY_V2_PE_CHECKSUM:
            raise ValueError("legacy v2 PE checksum does not match the verified executable")
    else:
        _unique_at(data, PATCHED_HOOK, HOOK_OFFSET, "legacy v3 Escape hook")
        _unique_at(data, LEGACY_V3_CAVE, CAVE_OFFSET, "legacy v3 Escape code cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != LEGACY_V3_PE_CHECKSUM:
            raise ValueError("legacy v3 PE checksum does not match the verified executable")

    result = bytearray(data)
    if digest == ORIGINAL_SHA256:
        result[HOOK_OFFSET : HOOK_OFFSET + len(PATCHED_HOOK)] = PATCHED_HOOK
    result[CAVE_OFFSET : CAVE_OFFSET + len(PATCHED_CAVE)] = PATCHED_CAVE
    result[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] = PATCHED_PE_CHECKSUM
    result = bytes(result)
    if sha256_bytes(result) != PATCHED_SHA256:
        raise ValueError("patched executable did not produce the expected SHA-256")
    return result, True


def patch_file(path: Path, *, check_only: bool = False) -> bool:
    result, changed = patched_bytes(path.read_bytes())
    if not changed or check_only:
        return changed
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(result)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)
    if sha256_bytes(path.read_bytes()) != PATCHED_SHA256:
        raise ValueError("atomic replacement failed post-write verification")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Make Escape end only the active UQM-HD Super Melee bout."
    )
    parser.add_argument("executable", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    executable = args.executable.resolve()
    if not executable.is_file():
        raise SystemExit(f"Executable not found: {executable}")
    needs_change = patch_file(executable, check_only=args.check)
    if args.check:
        print("needs-patch" if needs_change else "patched")
    else:
        print("patched" if needs_change else "already-patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
