from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile


# This patch is deliberately chained after the menu-highlight and active-bout
# Escape patches.  It accepts only that exact executable and uses a distinct,
# verified INT3 padding cave.
ORIGINAL_SHA256 = "3d2174f5dab4ce9b7a2dcd0eec7c59473f543239953b18664c51fff631f36bc9"
PATCHED_SHA256 = "14bb155c41af889e81f2d88ea341749b7a6cda4886c4aa75b9978ef61d7878ae"

HOOK_OFFSET = 0x2D612
CAVE_OFFSET = 0x75351
PE_CHECKSUM_OFFSET = 0x170

# ProcessInputEvent() normally calls VControl_HandleEvent() directly.  The
# position-independent hook maps an SDLK_RALT event to SDLK_RSHIFT immediately
# before that call, so the stock RightShift binding remains effective without
# embedding any ASLR-sensitive absolute addresses in the new code.
ORIGINAL_HOOK = bytes.fromhex("E8 F9 13 00 00")
PATCHED_HOOK = bytes.fromhex("E8 3A 7D 04 00")
ORIGINAL_CAVE = bytes([0xCC]) * 31
PATCHED_CAVE_PREFIX = bytes.fromhex(
    "8B 44 24 04 "          # mov eax, [esp + 4] (SDL_Event *)
    "81 78 08 33 01 00 00 " # cmp event->key.keysym.sym, SDLK_RALT
    "75 07 "                # skip replacement for every other key
    "C7 40 08 2F 01 00 00 " # mov event->key.keysym.sym, SDLK_RSHIFT
    "50 "                   # push event
    "E8 A5 96 FB FF "       # call VControl_HandleEvent
    "83 C4 04 "             # discard argument
    "C3"                    # return to ProcessInputEvent
)
PATCHED_CAVE = PATCHED_CAVE_PREFIX + bytes([0xCC]) * (
    len(ORIGINAL_CAVE) - len(PATCHED_CAVE_PREFIX)
)
ORIGINAL_PE_CHECKSUM = bytes.fromhex("BD F6 12 00")
PATCHED_PE_CHECKSUM = bytes.fromhex("66 68 13 00")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_at(data: bytes, signature: bytes, offset: int, description: str) -> None:
    if data.count(signature) != 1 or data.find(signature) != offset:
        raise ValueError(f"{description} is not unique at its verified file offset")


def _at(data: bytes, signature: bytes, offset: int, description: str) -> None:
    if data[offset : offset + len(signature)] != signature:
        raise ValueError(f"{description} is not present at its verified file offset")


def patched_bytes(data: bytes) -> tuple[bytes, bool]:
    digest = sha256_bytes(data)
    if digest == PATCHED_SHA256:
        _unique_at(data, PATCHED_HOOK, HOOK_OFFSET, "patched input hook")
        _unique_at(data, PATCHED_CAVE, CAVE_OFFSET, "patched RightAlt code cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != PATCHED_PE_CHECKSUM:
            raise ValueError("patched PE checksum does not match the verified executable")
        return data, False
    if digest != ORIGINAL_SHA256:
        raise ValueError(f"unsupported uqm.exe SHA-256: {digest}")

    _unique_at(data, ORIGINAL_HOOK, HOOK_OFFSET, "original input hook")
    # Multiple compiler-alignment runs happen to be 31 INT3 bytes long; the
    # exact executable hash plus exact offset safely identifies this one.
    _at(data, ORIGINAL_CAVE, CAVE_OFFSET, "original INT3 code cave")
    if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != ORIGINAL_PE_CHECKSUM:
        raise ValueError("original PE checksum does not match the verified executable")

    result = bytearray(data)
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
        description="Bind RightAlt to Player 1's special ability in UQM-HD."
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
