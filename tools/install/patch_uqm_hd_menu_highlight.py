from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import tempfile


ORIGINAL_SHA256 = "c43c258aa41c4effe5d092c8541560a517cdd7be91e3c576a10a4ad306f776d3"
UNCHECKSUMMED_PATCH_SHA256 = (
    "d25ebf74d4549be95d11c84df7bf2bc312ba7bd0a296bcc75492a4293062b6a7"
)
PATCHED_SHA256 = "638a9ae53678df63fcf1cd43ffe48e62446f094c67ab730c5c11a02a6ef86907"

# restart.c passes (-3, 3, 16) to Flash_setMergeFactors.  In this 32-bit
# release those three cdecl immediates are uniquely encoded as follows.
# Replace them with (3, 6, 16), keeping the yellow selection overlay visible
# throughout its pulse instead of crossing through gray and into red/blue.
ORIGINAL_CALL_ARGUMENTS = bytes.fromhex("6a106a036afd")
PATCHED_CALL_ARGUMENTS = bytes.fromhex("6a106a066a03")
EXPECTED_OFFSET = 0x8432B
PE_CHECKSUM_OFFSET = 0x170
ORIGINAL_PE_CHECKSUM = bytes.fromhex("be931300")
PATCHED_PE_CHECKSUM = bytes.fromhex("c7921300")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patched_bytes(data: bytes) -> tuple[bytes, bool]:
    digest = sha256_bytes(data)
    if digest == PATCHED_SHA256:
        if data.count(PATCHED_CALL_ARGUMENTS) != 1:
            raise ValueError("patched executable no longer has the expected unique call")
        return data, False
    if digest not in {ORIGINAL_SHA256, UNCHECKSUMMED_PATCH_SHA256}:
        raise ValueError(f"unsupported uqm.exe SHA-256: {digest}")
    if digest == ORIGINAL_SHA256:
        if data.count(ORIGINAL_CALL_ARGUMENTS) != 1:
            raise ValueError("original highlight call is not unique")
        if data.find(ORIGINAL_CALL_ARGUMENTS) != EXPECTED_OFFSET:
            raise ValueError("original highlight call moved from its verified file offset")
        result = bytearray(data)
        result[EXPECTED_OFFSET : EXPECTED_OFFSET + len(ORIGINAL_CALL_ARGUMENTS)] = (
            PATCHED_CALL_ARGUMENTS
        )
    else:
        if data.count(PATCHED_CALL_ARGUMENTS) != 1:
            raise ValueError("intermediate executable lacks the expected patched call")
        result = bytearray(data)
    if result[PE_CHECKSUM_OFFSET : PE_CHECKSUM_OFFSET + 4] != ORIGINAL_PE_CHECKSUM:
        raise ValueError("original PE checksum does not match the verified release")
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
        description="Make the UQM-HD main-menu highlight pulse positive-only."
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
