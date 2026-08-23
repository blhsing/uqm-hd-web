from __future__ import annotations

from .core import LocError


def native_resolution_manifest(
    raw: bytes,
    source_path: str,
    *,
    scale: int,
    native_frames: set[str] | None = None,
) -> bytes:
    """Mark selected ANI frames as already authored at native resolution.

    The source-built runtime understands an optional sixth numeric field.  A
    value of one suppresses its automatic 4x-to-native enlargement for that
    frame.  Hotspots for those frames must therefore be enlarged here too.
    Unmarked frames retain their 4x dimensions and are enlarged by the loader.
    """

    if scale < 1:
        raise LocError(f"{source_path}: invalid native animation scale {scale}")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise LocError(f"{source_path}: expected an ASCII animation manifest") from exc

    output: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) < 5:
            raise LocError(f"{source_path}: malformed animation row: {line!r}")
        filename = fields[0]
        is_native = native_frames is None or filename in native_frames
        try:
            hotspot_x = int(fields[3])
            hotspot_y = int(fields[4])
        except ValueError as exc:
            raise LocError(f"{source_path}: invalid animation hotspot: {line!r}") from exc
        if is_native:
            hotspot_x *= scale
            hotspot_y *= scale
        output.append(
            " ".join(
                (
                    filename,
                    fields[1],
                    fields[2],
                    str(hotspot_x),
                    str(hotspot_y),
                    "1" if is_native else "0",
                )
            )
        )
    if not output:
        raise LocError(f"{source_path}: animation manifest is empty")
    return ("\n".join(output) + "\n").encode("ascii")
