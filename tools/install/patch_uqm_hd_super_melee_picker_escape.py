from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile


# This patch is deliberately chained after the menu-highlight, active-bout
# Escape, and Player 1 RightAlt patches.  It accepts only that exact executable
# and uses a separate, verified compiler-alignment INT3 cave.
ORIGINAL_SHA256 = "14bb155c41af889e81f2d88ea341749b7a6cda4886c4aa75b9978ef61d7878ae"
PATCHED_SHA256 = "84d2b879e0029684013f86fcf9771c5ac9c12d7f1a1d7a6542de6d8615671b41"

HOOK_OFFSET = 0xEA975
CAVE_OFFSET = 0x68061
PE_CHECKSUM_OFFSET = 0x170

# DoGetMelee() originally begins its per-player selection pass by setting its
# local `done` flag to true.  The hook calls PulsedInputToBattleInput(0), checks
# Player 1's BATTLE_ESCAPE bit (physical Escape in the managed default profile),
# and calls the same ConfirmExit() routine used by the red X.  All cave calls
# and jumps are image-base-relative, so the patch remains safe under ASLR.
# ConfirmExit() sets CHECK_ABORT only for Yes; DoGetMelee observes it on the
# next input frame and follows its existing abort cleanup path back to the
# Super Melee team-setup screen.
ORIGINAL_HOOK = bytes.fromhex("C7 45 08 01 00 00 00")
PATCHED_HOOK = bytes.fromhex("E9 E7 D6 F7 FF 90 90")
ORIGINAL_CAVE = bytes([0xCC]) * 31
PATCHED_CAVE_PREFIX = bytes.fromhex(
    "6A 00 "                 # push Player 1
    "E8 A8 6F 00 00 "        # call PulsedInputToBattleInput
    "59 "                    # discard argument
    "A8 20 "                 # test al, BATTLE_ESCAPE
    "74 05 "                 # je displaced instruction
    "E8 CE 6F 00 00 "        # call ConfirmExit
    "C7 45 08 01 00 00 00 "  # mov dword ptr [ebp+8], 1 (displaced)
    "E9 FE 28 08 00"         # jmp DoGetMelee continuation
)
PATCHED_CAVE = PATCHED_CAVE_PREFIX + bytes([0xCC]) * (
    len(ORIGINAL_CAVE) - len(PATCHED_CAVE_PREFIX)
)
ORIGINAL_PE_CHECKSUM = bytes.fromhex("66 68 13 00")
PATCHED_PE_CHECKSUM = bytes.fromhex("2B 79 13 00")


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
        _unique_at(data, PATCHED_HOOK, HOOK_OFFSET, "patched picker-Escape hook")
        _unique_at(data, PATCHED_CAVE, CAVE_OFFSET, "patched picker-Escape cave")
        if data[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != PATCHED_PE_CHECKSUM:
            raise ValueError("patched PE checksum does not match the verified executable")
        return data, False
    if digest != ORIGINAL_SHA256:
        raise ValueError(f"unsupported uqm.exe SHA-256: {digest}")

    # This common local assignment occurs elsewhere too; the exact input hash
    # and verified file offset identify the DoGetMelee instance.
    _at(data, ORIGINAL_HOOK, HOOK_OFFSET, "original picker instruction")
    _unique_at(data, ORIGINAL_CAVE, CAVE_OFFSET, "original picker INT3 cave")
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
        description=(
            "Make physical Escape use the Super Melee ship picker's red-X "
            "confirmation path."
        )
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
