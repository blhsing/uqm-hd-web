from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import zipfile


LOCAL_HEADER = struct.Struct("<IHHHHHIIIHH")
CENTRAL_HEADER = struct.Struct("<IHHHHHHIIIHHHHHII")
LOCAL_SIGNATURE = 0x04034B50
CENTRAL_SIGNATURE = 0x02014B50
PADDING_NAME = ".__uqm_padding__"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _assert_clean_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise ValueError(f"{path}: CRC failure in {bad_member}")


def fit_zip_to_size(source: Path, destination: Path, target_size: int) -> None:
    """Copy a ZIP and add one inert stored entry so it has an exact size."""
    _assert_clean_zip(source)
    with zipfile.ZipFile(source) as archive:
        if PADDING_NAME in archive.namelist():
            raise ValueError(f"{source}: already contains {PADDING_NAME}")

    source_size = source.stat().st_size
    encoded_name = PADDING_NAME.encode("ascii")
    # A non-ZIP64 stored member adds one local header, one central-directory
    # entry, its name twice, and its uncompressed payload.
    member_overhead = 30 + 46 + 2 * len(encoded_name)
    payload_size = target_size - source_size - member_overhead
    if payload_size < 0:
        raise ValueError(
            f"{source}: cannot fit {source_size} bytes into {target_size} bytes"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    with zipfile.ZipFile(destination, mode="a", allowZip64=False) as archive:
        info = zipfile.ZipInfo(PADDING_NAME, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, bytes(payload_size), compress_type=zipfile.ZIP_STORED)

    actual_size = destination.stat().st_size
    if actual_size != target_size:
        destination.unlink(missing_ok=True)
        raise ValueError(
            f"{destination}: padding produced {actual_size} bytes, expected {target_size}"
        )
    _assert_clean_zip(destination)


def _member_layout(path: Path, member: str) -> tuple[zipfile.ZipInfo, int, int]:
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(member)
        if info.compress_type != zipfile.ZIP_STORED:
            raise ValueError(f"{path}: {member} is not stored")
        if info.flag_bits & 0x08:
            raise ValueError(f"{path}: {member} uses a data descriptor")
        central_start = archive.start_dir

    with path.open("rb") as stream:
        stream.seek(info.header_offset)
        local = stream.read(LOCAL_HEADER.size)
        if len(local) != LOCAL_HEADER.size:
            raise ValueError(f"{path}: truncated local header for {member}")
        fields = LOCAL_HEADER.unpack(local)
        if fields[0] != LOCAL_SIGNATURE:
            raise ValueError(f"{path}: invalid local header for {member}")
        name_length, extra_length = fields[-2:]
        raw_name = stream.read(name_length)
        if raw_name != member.encode("utf-8"):
            raise ValueError(f"{path}: unexpected local member name {raw_name!r}")
        data_offset = info.header_offset + LOCAL_HEADER.size + name_length + extra_length

        central_offset = central_start
        while True:
            stream.seek(central_offset)
            fixed = stream.read(CENTRAL_HEADER.size)
            if len(fixed) != CENTRAL_HEADER.size:
                raise ValueError(f"{path}: central entry for {member} was not found")
            fields = CENTRAL_HEADER.unpack(fixed)
            if fields[0] != CENTRAL_SIGNATURE:
                raise ValueError(f"{path}: central entry for {member} was not found")
            name_length = fields[10]
            extra_length = fields[11]
            comment_length = fields[12]
            raw_name = stream.read(name_length)
            local_offset = fields[16]
            if raw_name == member.encode("utf-8") and local_offset == info.header_offset:
                return info, data_offset, central_offset
            central_offset += CENTRAL_HEADER.size + name_length + extra_length + comment_length


def patch_stored_member(outer: Path, member: str, replacement: Path) -> None:
    """Atomically replace an equal-size stored ZIP member and both CRC fields."""
    replacement_bytes = replacement.read_bytes()
    replacement_crc = binascii.crc32(replacement_bytes) & 0xFFFFFFFF
    _assert_clean_zip(replacement)
    info, data_offset, central_offset = _member_layout(outer, member)
    if len(replacement_bytes) != info.file_size or info.file_size != info.compress_size:
        raise ValueError(
            f"{outer}: replacement is {len(replacement_bytes)} bytes; "
            f"stored member is {info.file_size} bytes"
        )

    with tempfile.NamedTemporaryFile(
        prefix=f".{outer.name}.", suffix=".tmp", dir=outer.parent, delete=False
    ) as temp:
        temporary = Path(temp.name)
    try:
        shutil.copy2(outer, temporary)
        with temporary.open("r+b") as stream:
            stream.seek(data_offset)
            if (binascii.crc32(stream.read(info.file_size)) & 0xFFFFFFFF) != info.CRC:
                raise ValueError(f"{outer}: existing member payload fails its CRC")
            stream.seek(data_offset)
            stream.write(replacement_bytes)
            stream.seek(info.header_offset + 14)
            stream.write(struct.pack("<I", replacement_crc))
            stream.seek(central_offset + 16)
            stream.write(struct.pack("<I", replacement_crc))

        _assert_clean_zip(temporary)
        with zipfile.ZipFile(temporary) as archive:
            if archive.read(member) != replacement_bytes:
                raise ValueError(f"{outer}: post-patch member comparison failed")
        os.replace(temporary, outer)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fit a nested ZIP to a stored member and replace it atomically."
    )
    parser.add_argument("--outer", type=Path, required=True)
    parser.add_argument("--member", required=True)
    parser.add_argument("--replacement", type=Path, required=True)
    parser.add_argument("--fitted", type=Path, required=True)
    args = parser.parse_args()

    outer = args.outer.resolve()
    replacement = args.replacement.resolve()
    fitted = args.fitted.resolve()
    with zipfile.ZipFile(outer) as archive:
        target_size = archive.getinfo(args.member).file_size
    if fitted.exists():
        raise SystemExit(f"Fitted output already exists: {fitted}")

    fit_zip_to_size(replacement, fitted, target_size)
    patch_stored_member(outer, args.member, fitted)
    print(
        json.dumps(
            {
                "outer": str(outer),
                "member": args.member,
                "member_bytes": target_size,
                "member_sha256": _sha256(fitted),
                "outer_sha256": _sha256(outer),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
