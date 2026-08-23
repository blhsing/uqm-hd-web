from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from uqmloc.builder import _zip_tree


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Pack one generated UQM add-on tree.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--exclude-root",
        action="store_true",
        help="Root archive members at the source directory's contents.",
    )
    parser.add_argument("--compress-level", type=int, default=1)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        raise SystemExit(f"Source tree does not exist: {source}")
    if output.exists():
        raise SystemExit(f"Output already exists: {output}")
    count = _zip_tree(
        source,
        output,
        include_root=not args.exclude_root,
        compresslevel=args.compress_level,
    )
    print(
        json.dumps(
            {
                "source": str(source),
                "output": str(output),
                "files": count,
                "bytes": output.stat().st_size,
                "sha256": _sha256(output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
