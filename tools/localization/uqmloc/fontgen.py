from __future__ import annotations

import io
import re
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .core import ContentResolver, LocError
from .wrapping import is_renderable_character


_PNG_NAME_RE = re.compile(r"^([0-9a-fA-F]{5})\.png$")
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class FontMetrics:
    width: int
    height: int
    sample_count: int


def png_dimensions(raw: bytes) -> tuple[int, int]:
    if len(raw) < 24 or raw[:8] != _PNG_SIGNATURE or raw[12:16] != b"IHDR":
        raise LocError("Invalid PNG while observing a bitmap font")
    width, height = struct.unpack(">II", raw[16:24])
    if width < 1 or height < 1:
        raise LocError("Bitmap font contains a zero-size PNG")
    return width, height


def _mode(values: Iterable[int]) -> int:
    counts = Counter(values)
    if not counts:
        raise LocError("Cannot observe metrics from an empty bitmap font")
    # Prefer the larger value on an exact frequency tie.
    return max(counts, key=lambda value: (counts[value], value))


def observe_font_metrics(files: dict[str, bytes]) -> FontMetrics:
    samples: dict[int, tuple[int, int]] = {}
    for name, raw in files.items():
        match = _PNG_NAME_RE.fullmatch(name)
        if match:
            samples[int(match.group(1), 16)] = png_dimensions(raw)
    if not samples:
        raise LocError("No five-hex-digit PNG glyphs were found in the source font")
    uppercase = [samples[codepoint] for codepoint in range(0x41, 0x5B) if codepoint in samples]
    metric_samples = uppercase or list(samples.values())
    height = _mode(size[1] for size in metric_samples)
    same_height_widths = [width for width, item_height in metric_samples if item_height == height]
    if not same_height_widths:
        same_height_widths = [width for width, _ in metric_samples]
    # Han glyphs are square-ish. The widest capital is a useful observed upper bound,
    # while 80% of the fixed canvas height prevents narrow fonts becoming unreadable.
    width = max(max(same_height_widths), round(height * 0.80), 1)
    return FontMetrics(width=width, height=height, sample_count=len(samples))


def translation_charset(texts: Iterable[str]) -> set[str]:
    result: set[str] = set()
    for text in texts:
        for character in text:
            if ord(character) > 0xFFFF:
                raise LocError(
                    f"U+{ord(character):X} cannot be loaded by UQM HD's bitmap-font loader"
                )
            if ord(character) > 0x7F and is_renderable_character(character):
                result.add(character)
    return result


def glyph_filename(character: str) -> str:
    codepoint = ord(character)
    if codepoint > 0xFFFF:
        raise LocError(f"U+{codepoint:X} exceeds the font loader's U+FFFF limit")
    return f"{codepoint:05x}.png"


class NotoRenderer:
    def __init__(self, font_path: Path, *, weight: int = 500, supersample: int = 4):
        self.font_path = font_path.resolve()
        self.weight = weight
        self.supersample = supersample
        if not self.font_path.is_file():
            raise LocError(f"Noto Sans TC font file not found: {self.font_path}")
        if not 100 <= self.weight <= 900:
            raise LocError(f"Font weight must be between 100 and 900: {self.weight}")
        if not 2 <= self.supersample <= 8:
            raise LocError(
                f"Font supersampling factor must be between 2 and 8: {self.supersample}"
            )
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore
        except ImportError as exc:
            raise LocError(
                "Bitmap generation requires Pillow. Run: python -m pip install -r requirements.txt"
            ) from exc
        self.Image = Image
        self.ImageDraw = ImageDraw
        self.ImageFont = ImageFont
        self._font_cache: dict[int, object] = {}

    def _font(self, size: int):
        if size not in self._font_cache:
            try:
                font = self.ImageFont.truetype(
                    str(self.font_path), size=size
                )
                # NotoSansTC-VF.ttf defaults to its minimum weight (Thin/100).
                # Medium/500 retains open counters and fine strokes while still
                # surviving UQM's bitmap-font compositor at the 4x tier.
                try:
                    axes = font.get_variation_axes()
                    values = [axis["default"] for axis in axes]
                    for index, axis in enumerate(axes):
                        name = axis.get("name", b"")
                        if isinstance(name, bytes):
                            name = name.decode("ascii", errors="ignore")
                        if str(name).lower() == "weight":
                            values[index] = min(
                                axis["maximum"], max(axis["minimum"], self.weight)
                            )
                    if axes:
                        font.set_variation_by_axes(values)
                except (AttributeError, OSError):
                    # A static Bold font is also a valid input.
                    pass
                self._font_cache[size] = font
            except OSError as exc:
                raise LocError(f"Pillow cannot load {self.font_path}: {exc}") from exc
        return self._font_cache[size]

    def render(self, character: str, metrics: FontMetrics) -> bytes:
        # A one-pixel inset consumes most of a 6x8 or 9x9 Han canvas. Small
        # compatibility-mode fonts need the full bitmap; larger fonts retain
        # the inset to avoid clipping antialiased edges.
        padding_x = 0 if min(metrics.width, metrics.height) <= 12 else 1
        # The SIS labels occupy unusually tight vertical bands. Two vertical
        # pixels keep supersampled accents and descenders inside those bands
        # instead of letting the engine clip their final antialiased row.
        padding_y = 0 if min(metrics.width, metrics.height) <= 12 else 2
        available_width = max(1, metrics.width - padding_x * 2)
        available_height = max(1, metrics.height - padding_y * 2)
        chosen = None
        bbox = None
        for size in range(max(metrics.width, metrics.height) + 2, 1, -1):
            font = self._font(size * self.supersample)
            candidate = font.getbbox(character)
            if candidate is None:
                continue
            glyph_width = candidate[2] - candidate[0]
            glyph_height = candidate[3] - candidate[1]
            if (
                0 < glyph_width <= available_width * self.supersample
                and 0 < glyph_height <= available_height * self.supersample
            ):
                chosen = font
                bbox = candidate
                break
        if chosen is None or bbox is None:
            raise LocError(
                f"Noto Sans TC did not yield a nonempty fitting glyph for U+{ord(character):04X} "
                f"on {metrics.width}x{metrics.height}"
            )
        render_size = (
            metrics.width * self.supersample,
            metrics.height * self.supersample,
        )
        image = self.Image.new("RGBA", render_size, (255, 255, 255, 0))
        draw = self.ImageDraw.Draw(image)
        glyph_width = bbox[2] - bbox[0]
        glyph_height = bbox[3] - bbox[1]
        x = (render_size[0] - glyph_width) // 2 - bbox[0]
        y = (render_size[1] - glyph_height) // 2 - bbox[1]
        draw.text((x, y), character, font=chosen, fill=(255, 255, 255, 255))
        image = image.resize(
            (metrics.width, metrics.height),
            resample=self.Image.Resampling.LANCZOS,
        )
        # Lanczos deliberately produces a very faint one-pixel ringing fringe.
        # UQM treats any non-zero alpha as ink when calculating bitmap bounds,
        # so remove only that sub-visible halo while retaining the smoothly
        # antialiased edge proper.
        alpha = image.getchannel("A").point(lambda value: 0 if value < 8 else value)
        image.putalpha(alpha)
        buffer = io.BytesIO()
        # The build emits thousands of tiny glyphs and the outer UQM archive is
        # Deflate-compressed as well. Pillow's exhaustive PNG optimizer makes a
        # complete rebuild several times slower for negligible package savings.
        # Level 1 remains lossless and deterministic while keeping rebuilds
        # practical on older hosts.
        image.save(buffer, format="PNG", optimize=False, compress_level=1)
        return buffer.getvalue()


def build_font_directory(
    resolver: ContentResolver,
    source_path: str,
    destination: Path,
    characters: set[str],
    renderer: NotoRenderer,
    *,
    copy_original: bool,
    metric_override: tuple[int, int] | None = None,
    source_scale: int = 1,
) -> tuple[FontMetrics, int]:
    if source_scale < 1:
        raise LocError(f"Invalid source bitmap-font scale: {source_scale}")
    files = resolver.list_files(source_path)
    metrics = observe_font_metrics(files)
    if metric_override is not None:
        width, height = metric_override
        if width < 1 or height < 1:
            raise LocError(f"Invalid bitmap-font metric override: {metric_override}")
        metrics = FontMetrics(width=width, height=height, sample_count=metrics.sample_count)
    elif source_scale != 1:
        metrics = FontMetrics(
            width=metrics.width * source_scale,
            height=metrics.height * source_scale,
            sample_count=metrics.sample_count,
        )
    destination.mkdir(parents=True, exist_ok=True)
    if copy_original:
        for name, raw in sorted(files.items()):
            if "/" in name or "\\" in name:
                raise LocError(f"Unsafe filename in source font {source_path}: {name!r}")
            if source_scale != 1 and _PNG_NAME_RE.fullmatch(name):
                try:
                    original = renderer.Image.open(io.BytesIO(raw)).convert("RGBA")
                except OSError as exc:
                    raise LocError(
                        f"Cannot enlarge source glyph {source_path}/{name}: {exc}"
                    ) from exc
                enlarged = original.resize(
                    (
                        original.width * source_scale,
                        original.height * source_scale,
                    ),
                    resample=renderer.Image.Resampling.LANCZOS,
                )
                buffer = io.BytesIO()
                enlarged.save(
                    buffer, format="PNG", optimize=False, compress_level=1
                )
                raw = buffer.getvalue()
                enlarged.close()
                original.close()
            (destination / name).write_bytes(raw)
    count = 0
    for character in sorted(characters, key=ord):
        filename = glyph_filename(character)
        (destination / filename).write_bytes(renderer.render(character, metrics))
        count += 1
    missing = [glyph_filename(character) for character in characters if not (destination / glyph_filename(character)).is_file()]
    if missing:
        raise LocError(f"Generated font {destination} is missing {len(missing)} glyph(s)")
    return metrics, count
