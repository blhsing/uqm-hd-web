from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .ani import native_resolution_manifest
from .core import ContentResolver, LocError


MENU_LABELS = ("新遊戲", "載入遊戲", "超級對戰", "設定", "離開")
MENU_FONT_WEIGHT = 500
# The restart menu does not alpha-composite its selected frame.  It adds and
# subtracts that frame at only 3/16 strength.  A neutral base plus a yellow
# effect map therefore makes the selected label pulse blue <-> yellow, while
# every unselected label remains a steady light gray.  Baking red into the
# base can never produce a cyan selected label because the red channel is
# already saturated before the effect is applied.
MENU_NORMAL_COLOR = (160, 160, 160, 255)
MENU_SELECTED_COLOR = (255, 240, 0, 255)
MENU_KEY_HELP = "↑↓ 選擇　Enter 確認"
MENU_KEY_HELP_COLOR = (175, 225, 235, 255)

# ClearShipStatus() paints the body of each combat status panel with
# MAKE_RGB15(0x0A, 0x0A, 0x0A).  The PC status animation declares RGB black as
# its transparent colour, and the SDL renderer consequently disables the PNG
# surface's per-pixel alpha for an ordinary DrawStamp().  Give zero-alpha
# pixels the panel RGB instead of black so that the enlarged Chinese label
# restores the panel behind it.  DrawFilledStamp() still reads the PNG alpha
# channel when it creates the low-energy recolour, so the zero alpha is
# deliberately retained.
STATUS_PANEL_BACKGROUND = (82, 82, 82)
_STATUS_LABEL_ANI_RE = re.compile(
    rb"(?m)^([ \t]*status-(?:004|005)\.png[ \t]+)-?\d+([ \t]+[^\r\n]*(?:\r?\n|$))"
)


@dataclass(frozen=True)
class MenuVariant:
    addon: str
    stem: str
    native_scale: int


@dataclass(frozen=True)
class MenuFrame:
    filename: str
    width: int
    height: int
    x: int
    y: int


MENU_VARIANTS = (
    MenuVariant("native1080-zh_TW", "newgame4x", 2),
)


@dataclass(frozen=True)
class KeyHelpVariant:
    addon: str
    source_path: str
    output_path: str
    native_scale: int


KEY_HELP_VARIANTS = (
    KeyHelpVariant(
        "native1080-zh_TW",
        "addons/hires4x/ui/submenustarmapkeys-000.png",
        "addons/hires4x/ui/submenustarmapkeys-000.png",
        2,
    ),
)


@dataclass(frozen=True)
class StatusLabelVariant:
    addon: str
    source_prefix: str
    output_prefix: str
    crew_size: tuple[int, int]
    energy_size: tuple[int, int]
    crew_output_size: tuple[int, int]
    energy_output_size: tuple[int, int]
    font_weight: int
    font_size: int


STATUS_LABEL_VARIANTS = (
    StatusLabelVariant(
        "native1080-zh_TW",
        "addons/hires4x/ui",
        "addons/hires4x/ui",
        (44, 9),
        (44, 9),
        (88, 36),
        (88, 36),
        350,
        32,
    ),
)


@dataclass(frozen=True)
class SuperMeleeVariant:
    addon: str
    source_prefix: str
    output_prefix: str
    scale: int


SUPER_MELEE_VARIANTS = (
    SuperMeleeVariant(
        "native1080-zh_TW", "addons/hires4x/ui", "addons/hires4x/ui", 8
    ),
)

SUPER_MELEE_FONT_WEIGHT = 500
SUPER_MELEE_TITLE = "超級對戰"
SUPER_MELEE_CONTROL_LABELS = (
    ("玩家", "操控"),
    ("簡易", "電腦"),
    ("普通", "電腦"),
    ("最強", "電腦"),
)
SUPER_MELEE_NETWORK_LABEL = ("網路", "操控")
SUPER_MELEE_BUTTON_LABELS = {
    "LOAD": "載入",
    "SAVE": "儲存",
    "NET": "連線",
    "BATTLE": "開戰！",
    "QUIT": "離開",
}


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError as exc:
        raise LocError(
            "Main-menu generation requires Pillow. Run: python -m pip install -r requirements.txt"
        ) from exc
    return Image, ImageDraw, ImageFont


def _menu_font(
    ImageFont,
    font_path: Path,
    size: int,
    weight: int = MENU_FONT_WEIGHT,
):
    try:
        font = ImageFont.truetype(str(font_path), size=size)
        axes = font.get_variation_axes()
        values = [axis["default"] for axis in axes]
        for index, axis in enumerate(axes):
            name = axis.get("name", b"")
            if isinstance(name, bytes):
                name = name.decode("ascii", errors="ignore")
            if str(name).lower() == "weight":
                values[index] = min(axis["maximum"], max(axis["minimum"], weight))
        if axes:
            font.set_variation_by_axes(values)
        return font
    except (AttributeError, OSError) as exc:
        if isinstance(exc, OSError) and "variation" not in str(exc).lower():
            raise LocError(f"Pillow cannot load {font_path}: {exc}") from exc
        try:
            return ImageFont.truetype(str(font_path), size=size)
        except OSError as inner:
            raise LocError(f"Pillow cannot load {font_path}: {inner}") from inner


def _parse_frames(
    resolver: ContentResolver, stem: str, Image
) -> tuple[bytes, list[MenuFrame]]:
    ani_path = f"base/ui/{stem}.ani"
    raw = resolver.read_bytes(ani_path)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise LocError(f"{ani_path}: expected an ASCII animation manifest") from exc
    rows = [line for line in text.splitlines() if line.strip()]
    if len(rows) != 6:
        raise LocError(f"{ani_path}: expected six menu frames, found {len(rows)}")
    frames: list[MenuFrame] = []
    for row in rows:
        fields = row.split()
        if len(fields) != 5:
            raise LocError(f"{ani_path}: malformed animation row: {row!r}")
        filename = fields[0]
        try:
            hotspot_x, hotspot_y = int(fields[-2]), int(fields[-1])
        except ValueError as exc:
            raise LocError(f"{ani_path}: invalid animation hotspot: {row!r}") from exc
        image = Image.open(io.BytesIO(resolver.read_bytes(f"base/ui/{filename}")))
        try:
            width, height = image.size
        finally:
            image.close()
        frames.append(
            MenuFrame(filename, width, height, -hotspot_x, -hotspot_y)
        )
    return raw, frames


def _measure_tracked(draw, text: str, font, tracking: int, stroke_width: int):
    boxes = [
        draw.textbbox((0, 0), character, font=font, stroke_width=stroke_width)
        for character in text
    ]
    width = sum(box[2] - box[0] for box in boxes) + tracking * max(0, len(text) - 1)
    top = min(box[1] for box in boxes)
    bottom = max(box[3] for box in boxes)
    return boxes, width, top, bottom


def _draw_tracked_centered(
    image,
    ImageDraw,
    ImageFont,
    font_path: Path,
    text: str,
    *,
    fill: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    # Menu labels are large artwork, not the tiny in-game bitmap font. Medium
    # weight without a synthetic outline matches the original menu's lighter
    # visual rhythm while remaining clear in the 4x artwork.
    stroke_width = 0
    size = max(8, round(image.height * 0.74))
    while True:
        font = _menu_font(ImageFont, font_path, size)
        tracking = max(1, round(size * 0.12))
        boxes, width, top, bottom = _measure_tracked(
            draw, text, font, tracking, stroke_width
        )
        if width <= image.width * 0.90 or size <= 8:
            break
        size -= 1
    x = (image.width - width) / 2
    y = (image.height - (bottom - top)) / 2 - top
    for character, box in zip(text, boxes):
        draw.text(
            (round(x - box[0]), round(y)),
            character,
            font=font,
            fill=fill,
        )
        x += box[2] - box[0] + tracking


def _effect_map_from_mask(Image, mask, color: tuple[int, int, int, int]):
    """Encode antialias coverage in RGB for UQM's additive draw mode.

    The legacy additive renderer treats every non-transparent PNG pixel as a
    full-strength sample, so a conventional variable-alpha edge turns into a
    hard fringe.  Premultiplying the effect color into RGB and using binary
    alpha preserves the intended coverage in this particular compositor.
    """

    channels = [
        mask.point(lambda coverage, component=component: round(coverage * component / 255))
        for component in color[:3]
    ]
    alpha = mask.point(lambda coverage: 255 if coverage else 0)
    return Image.merge("RGBA", (*channels, alpha))


def _draw_menu_key_help(background, Image, ImageDraw, ImageFont, font_path: Path) -> None:
    draw = ImageDraw.Draw(background)
    size = max(9, round(background.height * 0.029))
    while True:
        font = _menu_font(ImageFont, font_path, size, weight=550)
        box = draw.textbbox((0, 0), MENU_KEY_HELP, font=font)
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width <= background.width * 0.78 or size <= 9:
            break
        size -= 1

    x = round((background.width - width) / 2)
    y = round(background.height - height - max(3, size * 0.45) - box[1])
    padding_x = max(4, round(size * 0.65))
    padding_y = max(2, round(size * 0.28))
    layer = Image.new("RGBA", background.size, (0, 0, 0, 0))
    layer_draw = ImageDraw.Draw(layer)
    layer_draw.rounded_rectangle(
        (
            x - padding_x,
            y + box[1] - padding_y,
            x + width + padding_x,
            y + box[3] + padding_y,
        ),
        radius=max(2, round(size * 0.35)),
        fill=(0, 5, 8, 185),
        outline=(55, 125, 140, 210),
        width=max(1, round(size / 16)),
    )
    layer_draw.text((x, y), MENU_KEY_HELP, font=font, fill=MENU_KEY_HELP_COLOR)
    background.alpha_composite(layer)


def _clear_text_region(image, box: tuple[int, int, int, int]) -> None:
    """Remove old glyph pixels without flattening the panel's blue gradient."""

    x0, y0, x1, y1 = box
    pixels = image.load()
    for y in range(y0, y1):
        candidates = []
        for x in range(x0, x1):
            red, green, blue = pixels[x, y][:3]
            if blue >= 90 and blue > red * 1.6 and blue > green * 1.6:
                candidates.append((red, green, blue))
        fill = Counter(candidates).most_common(1)[0][0] if candidates else (0, 0, 165)
        for x in range(x0, x1):
            red, green, _ = pixels[x, y][:3]
            # Every stock panel background pixel is blue-only.  White or
            # magenta text introduces red/green, including its antialiasing.
            if red > 2 or green > 2:
                pixels[x, y] = fill


def _draw_text_at(draw, ImageFont, font_path: Path, text: str, xy, size: int, color) -> None:
    font = _menu_font(ImageFont, font_path, size, weight=500)
    draw.multiline_text(xy, text, font=font, fill=color, spacing=max(0, size // 7))


def build_localized_key_help(
    resolver: ContentResolver,
    shadow_trees_root: Path,
    font_path: Path,
) -> dict[str, dict[str, object]]:
    """Localize the supersampled native-resolution starmap key-help panel."""

    Image, ImageDraw, ImageFont = _load_pillow()
    report: dict[str, dict[str, object]] = {}
    for variant in KEY_HELP_VARIANTS:
        try:
            image = Image.open(io.BytesIO(resolver.read_bytes(variant.source_path))).convert("RGB")
        except OSError as exc:
            raise LocError(f"Cannot load key-help image {variant.source_path}: {exc}") from exc

        if image.size != (186, 307):
            raise LocError(f"Unexpected source key-help size: {image.size}")
        scale = variant.native_scale
        image = image.resize(
            (image.width * scale, image.height * scale),
            resample=Image.Resampling.LANCZOS,
        )

        def scaled_box(box):
            return tuple(value * scale for value in box)

        for box in (
            (45, 4, 150, 36),
            (47, 40, 185, 92),
            (47, 112, 185, 151),
            (47, 178, 185, 218),
            (47, 240, 185, 279),
        ):
            _clear_text_region(image, scaled_box(box))
        draw = ImageDraw.Draw(image)
        title = "按鍵說明"
        title_font = _menu_font(ImageFont, font_path, 22 * scale, weight=550)
        title_box = draw.textbbox((0, 0), title, font=title_font)
        title_x = round((image.width - (title_box[2] - title_box[0])) / 2)
        draw.text((title_x, 5 * scale), title, font=title_font, fill=(181, 90, 255))
        _draw_text_at(draw, ImageFont, font_path, "舊式星圖／\n顯示星座", (54 * scale, 45 * scale), 14 * scale, (181, 90, 255))
        _draw_text_at(draw, ImageFont, font_path, "放大", (60 * scale, 119 * scale), 17 * scale, (181, 90, 255))
        _draw_text_at(draw, ImageFont, font_path, "縮小", (60 * scale, 186 * scale), 17 * scale, (181, 90, 255))
        _draw_text_at(draw, ImageFont, font_path, "搜尋星體", (54 * scale, 248 * scale), 16 * scale, (181, 90, 255))

        destination = shadow_trees_root / variant.addon
        destination = destination.joinpath(*PurePosixPath(variant.output_path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # These panels are opaque pixel artwork.  An indexed palette preserves
        # the gradients and antialiased Han glyphs while avoiding several KB
        # of redundant RGB data in every mounted shadow archive.
        encoded = image.quantize(
            colors=128,
            method=Image.Quantize.MEDIANCUT,
            dither=Image.Dither.NONE,
        )
        encoded.save(destination, format="PNG", optimize=True)
        encoded.close()

        source_ani_path = variant.source_path.rsplit("-", 1)[0] + ".ani"
        output_ani_path = variant.output_path.rsplit("-", 1)[0] + ".ani"
        ani_destination = shadow_trees_root / variant.addon
        ani_destination = ani_destination.joinpath(
            *PurePosixPath(output_ani_path).parts
        )
        ani_destination.parent.mkdir(parents=True, exist_ok=True)
        ani_destination.write_bytes(
            native_resolution_manifest(
                resolver.read_bytes(source_ani_path),
                source_ani_path,
                scale=scale,
                native_frames={PurePosixPath(variant.output_path).name},
            )
        )
        report[variant.addon] = {
            "resource": variant.output_path,
            "canvas": list(image.size),
            "labels": ["舊式星圖／顯示星座", "放大", "縮小", "搜尋星體"],
            "animation": output_ani_path,
        }
        image.close()
    return report


def _status_text_mask(
    Image,
    ImageDraw,
    ImageFont,
    font_path: Path,
    text: str,
    size,
    *,
    font_weight: int = 500,
    font_size: int | None = None,
):
    width, height = size
    mask = Image.new("L", size, 0)
    compact_glyphs = {
        "人": ("00100", "00100", "01010", "01010", "10001"),
        "力": ("01110", "00010", "01110", "01010", "10010"),
    }
    if height == 5 and text in compact_glyphs:
        x0 = (width - 5) // 2
        for y, row in enumerate(compact_glyphs[text]):
            for x, value in enumerate(row):
                if value == "1":
                    mask.putpixel((x0 + x, y), 255)
        return mask
    draw = ImageDraw.Draw(mask)
    if font_size is None:
        font_size = max(7, round(height * 1.6))
    while True:
        font = _menu_font(ImageFont, font_path, font_size, weight=font_weight)
        box = draw.textbbox((0, 0), text, font=font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        if (text_width <= width and text_height <= height) or font_size <= 5:
            break
        font_size -= 1
    x = round((width - text_width) / 2 - box[0])
    y = round((height - text_height) / 2 - box[1])
    draw.text((x, y), text, font=font, fill=255)
    return mask


def _row_colors(source, *, energy: bool) -> list[tuple[int, int, int]]:
    rgba = source.convert("RGBA")
    colors: list[tuple[int, int, int] | None] = []
    channel = 0 if energy else 1
    for y in range(rgba.height):
        opaque = [
            pixel[:3]
            for pixel in (rgba.getpixel((x, y)) for x in range(rgba.width))
            if pixel[3] and pixel[channel] > max(pixel[1 - channel], pixel[2])
        ]
        colors.append(max(opaque, key=lambda pixel: pixel[channel]) if opaque else None)
    fallback = (124, 0, 0) if energy else (6, 69, 6)
    populated = [color for color in colors if color is not None]
    if populated:
        fallback = populated[0]
    resolved = [color if color is not None else fallback for color in colors]
    brightened = [
        tuple(
            min(255, round(component * (2.0 if index == channel else 1.5)))
            for index, component in enumerate(color)
        )
        for color in resolved
    ]
    peak = max(color[channel] for color in brightened)
    floor = round(peak * 0.45)
    normalized = []
    for color in brightened:
        if color[channel] >= floor or color[channel] == 0:
            normalized.append(color)
            continue
        scale = floor / color[channel]
        normalized.append(tuple(min(255, round(component * scale)) for component in color))
    return normalized


def _render_status_label(
    Image,
    ImageDraw,
    ImageFont,
    source,
    font_path: Path,
    text: str,
    *,
    energy: bool,
    output_size: tuple[int, int] | None = None,
    font_weight: int = 500,
    font_size: int | None = None,
):
    if output_size is None:
        output_size = source.size
    mask = _status_text_mask(
        Image,
        ImageDraw,
        ImageFont,
        font_path,
        text,
        output_size,
        font_weight=font_weight,
        font_size=font_size,
    )
    colors = _row_colors(source, energy=energy)
    # The stock labels use a five- or nine-pixel vertical gradient.  Stretching
    # that gradient made the larger Han glyphs look soft, so use its brightest
    # row as a solid high-contrast foreground at every output resolution.
    channel = 0 if energy else 1
    brightest = max(colors, key=lambda color: color[channel])
    colors = [brightest] * output_size[1]

    # Always emit true-colour status labels.
    # An indexed frame can either expose its transparent backdrop (leaving the
    # stock black gauge rectangle visible) or make that backdrop part of the
    # low-energy fill mask; it cannot encode the two runtime behaviours
    # independently.  RGBA lets RGB restore the normal panel while alpha keeps
    # the recolour mask limited to the Han glyphs.
    output = Image.new("RGBA", output_size, (*STATUS_PANEL_BACKGROUND, 0))
    for y, color in enumerate(colors):
        for x in range(output_size[0]):
            alpha = mask.getpixel((x, y))
            if alpha:
                output.putpixel((x, y), (*color, alpha))
    return output


def _status_ani_with_rgb_color_key(raw: bytes, source_path: str) -> bytes:
    """Make the two text frames use RGB black as their transparency key.

    The localized RGBA frames intentionally use RGB for their normal backdrop
    and alpha for their fill mask, so the two frames must take the true-colour
    RGB-key path in process_image().
    """

    normalized, count = _STATUS_LABEL_ANI_RE.subn(rb"\g<1>0\g<2>", raw)
    if count != 2:
        raise LocError(
            f"Expected exactly status-004.png and status-005.png in {source_path}; "
            f"matched {count} localized status frames"
        )
    return normalized


def build_localized_status_labels(
    resolver: ContentResolver,
    shadow_trees_root: Path,
    font_path: Path,
) -> dict[str, dict[str, object]]:
    """Replace the PC-mode combat labels CREW/BATT with 船員/能量."""

    Image, ImageDraw, ImageFont = _load_pillow()
    report: dict[str, dict[str, object]] = {}
    for variant in STATUS_LABEL_VARIANTS:
        files: list[str] = []
        for frame, label, energy in ((4, "船員", False), (5, "能量", True)):
            source_path = f"{variant.source_prefix}/status-{frame:03d}.png"
            source = Image.open(io.BytesIO(resolver.read_bytes(source_path)))
            expected_size = variant.energy_size if energy else variant.crew_size
            output_size = (
                variant.energy_output_size if energy else variant.crew_output_size
            )
            if source.size != expected_size:
                source.close()
                raise LocError(
                    f"Unexpected {variant.addon} status label size for {source_path}: {source.size}"
                )
            rendered = _render_status_label(
                Image,
                ImageDraw,
                ImageFont,
                source,
                font_path,
                label,
                energy=energy,
                output_size=output_size,
                font_weight=variant.font_weight,
                font_size=variant.font_size,
            )
            output_path = f"{variant.output_prefix}/status-{frame:03d}.png"
            destination = shadow_trees_root / variant.addon
            destination = destination.joinpath(*PurePosixPath(output_path).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            save_args = {"format": "PNG", "optimize": True}
            if rendered.mode == "P":
                save_args["transparency"] = 0
            rendered.save(destination, **save_args)
            rendered.close()
            source.close()
            files.append(output_path)

        source_ani_path = f"{variant.source_prefix}/status.ani"
        output_ani_path = f"{variant.output_prefix}/status.ani"
        destination = shadow_trees_root / variant.addon
        destination = destination.joinpath(*PurePosixPath(output_ani_path).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        status_raw = _status_ani_with_rgb_color_key(
            resolver.read_bytes(source_ani_path), source_ani_path
        )
        native_scale = variant.crew_output_size[0] // variant.crew_size[0]
        destination.write_bytes(
            native_resolution_manifest(
                status_raw,
                source_ani_path,
                scale=native_scale,
                native_frames={"status-004.png", "status-005.png"},
            )
        )
        files.append(output_ani_path)
        report[variant.addon] = {
            "labels": {"CREW": "船員", "BATT": "能量"},
            "compact_labels": None,
            "font_weight": variant.font_weight,
            "font_size": variant.font_size,
            "panel_background_rgb": list(STATUS_PANEL_BACKGROUND),
            "normal_transparency": "rgb-black-color-key",
            "low_energy_mask": "png-alpha",
            "source_canvases": {
                "CREW": list(variant.crew_size),
                "BATT": list(variant.energy_size),
            },
            "canvases": {
                "CREW": list(variant.crew_output_size),
                "BATT": list(variant.energy_output_size),
            },
            "files": files,
        }
    return report


def _parse_super_melee_frames(
    resolver: ContentResolver, variant: SuperMeleeVariant, Image
) -> tuple[bytes, list[MenuFrame]]:
    ani_path = f"{variant.source_prefix}/meleemenu.ani"
    raw = resolver.read_bytes(ani_path)
    try:
        rows = [line for line in raw.decode("ascii").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise LocError(f"{ani_path}: expected an ASCII animation manifest") from exc
    if len(rows) != 39:
        raise LocError(f"{ani_path}: expected 39 Super Melee frames, found {len(rows)}")
    frames: list[MenuFrame] = []
    for row in rows:
        fields = row.split()
        if len(fields) != 5:
            raise LocError(f"{ani_path}: malformed animation row: {row!r}")
        filename = fields[0]
        try:
            hotspot_x, hotspot_y = int(fields[-2]), int(fields[-1])
        except ValueError as exc:
            raise LocError(f"{ani_path}: invalid animation hotspot: {row!r}") from exc
        image = Image.open(
            io.BytesIO(resolver.read_bytes(f"{variant.source_prefix}/{filename}"))
        )
        try:
            width, height = image.size
        finally:
            image.close()
        frames.append(MenuFrame(filename, width, height, -hotspot_x, -hotspot_y))
    native_scale = variant.scale // 4
    if native_scale < 1 or variant.scale % 4:
        raise LocError(f"{ani_path}: invalid native Super Melee scale {variant.scale}")
    frames = [
        MenuFrame(
            frame.filename,
            frame.width * native_scale,
            frame.height * native_scale,
            frame.x * native_scale,
            frame.y * native_scale,
        )
        for frame in frames
    ]
    return raw, frames


def _fit_melee_font(
    draw,
    ImageFont,
    font_path: Path,
    lines: tuple[str, ...],
    box: tuple[int, int, int, int],
    *,
    weight: int,
    stroke_width: int,
):
    width = max(1, box[2] - box[0])
    height = max(1, box[3] - box[1])
    max_size = max(3, round(height / max(1, len(lines)) * 1.25))
    for size in range(max_size, 1, -1):
        font = _menu_font(ImageFont, font_path, size, weight=weight)
        bounds = [
            draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
            for line in lines
        ]
        line_heights = [bound[3] - bound[1] for bound in bounds]
        spacing = max(0, round(size * 0.10)) if len(lines) > 1 else 0
        if (
            max(bound[2] - bound[0] for bound in bounds) <= width
            and sum(line_heights) + spacing * (len(lines) - 1) <= height
        ):
            return font, bounds, spacing
    font = _menu_font(ImageFont, font_path, 2, weight=weight)
    bounds = [
        draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        for line in lines
    ]
    return font, bounds, 0


def _draw_melee_lines(
    image,
    ImageDraw,
    ImageFont,
    font_path: Path,
    lines: tuple[str, ...],
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int, int],
    weight: int = SUPER_MELEE_FONT_WEIGHT,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255),
) -> None:
    draw = ImageDraw.Draw(image)
    font, bounds, spacing = _fit_melee_font(
        draw,
        ImageFont,
        font_path,
        lines,
        box,
        weight=weight,
        stroke_width=stroke_width,
    )
    heights = [bound[3] - bound[1] for bound in bounds]
    total_height = sum(heights) + spacing * (len(lines) - 1)
    y = box[1] + (box[3] - box[1] - total_height) / 2
    for line, bound, line_height in zip(lines, bounds, heights):
        line_width = bound[2] - bound[0]
        x = box[0] + (box[2] - box[0] - line_width) / 2 - bound[0]
        draw.text(
            (round(x), round(y - bound[1])),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        y += line_height + spacing


def _load_melee_template(Image, root: Path, name: str, expected_size: tuple[int, int]):
    path = root / name
    if not path.is_file():
        raise LocError(f"Clean Super Melee template not found: {path}")
    image = Image.open(path).convert("RGBA")
    if image.size != expected_size:
        found = image.size
        image.close()
        raise LocError(
            f"Unexpected clean Super Melee template size for {path}: "
            f"expected {expected_size}, found {found}"
        )
    return image


def _resized_melee_template(Image, source, target_size: tuple[int, int]):
    if source.size == target_size:
        return source.copy()
    return source.resize(target_size, resample=Image.Resampling.LANCZOS)


def _battle_label_box(size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    return (12, 14, width - 12, min(height, 62))


def build_localized_super_melee_assets(
    resolver: ContentResolver,
    shadow_trees_root: Path,
    font_path: Path,
    clean_assets_root: Path,
) -> dict[str, dict[str, object]]:
    """Localize all labels visible on the Super Melee fleet-setup screen."""

    Image, ImageDraw, ImageFont = _load_pillow()
    clean_assets_root = clean_assets_root.resolve()
    clean_background = _load_melee_template(
        Image, clean_assets_root, "background-4x.png", (1280, 960)
    )
    clean_battle = _load_melee_template(
        Image, clean_assets_root, "battle-4x.png", (193, 258)
    )
    control_templates = {
        (control, selected): _load_melee_template(
            Image,
            clean_assets_root,
            f"{control}-{'selected' if selected else 'normal'}-4x.png",
            (232, 116),
        )
        for control in ("human", "weak", "good", "awesome")
        for selected in (False, True)
    }
    network_templates = {
        selected: _load_melee_template(
            Image,
            clean_assets_root,
            f"network-{'selected' if selected else 'normal'}-4x.png",
            (232, 116),
        )
        for selected in (False, True)
    }
    report: dict[str, dict[str, object]] = {}
    try:
        for variant in SUPER_MELEE_VARIANTS:
            ani_raw, frames = _parse_super_melee_frames(resolver, variant, Image)
            output_dir = shadow_trees_root / variant.addon
            output_dir = output_dir.joinpath(*PurePosixPath(variant.output_prefix).parts)
            output_dir.mkdir(parents=True, exist_ok=True)
            files: set[str] = set()

            background = _resized_melee_template(
                Image,
                clean_background,
                (frames[0].width, frames[0].height),
            )
            title_width = min(background.width, 256 * variant.scale)
            _draw_melee_lines(
                background,
                ImageDraw,
                ImageFont,
                font_path,
                (SUPER_MELEE_TITLE,),
                (4 * variant.scale, 2 * variant.scale, title_width - 4 * variant.scale, 27 * variant.scale),
                fill=(246, 190, 255, 255),
                weight=600,
                stroke_width=max(1, variant.scale // 2),
                stroke_fill=(105, 0, 125, 255),
            )
            background_labels = {
                17: "載入",
                18: "儲存",
                21: "儲存",
                22: "載入",
                29: "離開",
                35: "連線",
                37: "連線",
            }
            for index, label in background_labels.items():
                frame = frames[index]
                _draw_melee_lines(
                    background,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    (label,),
                    (frame.x, frame.y, frame.x + frame.width, frame.y + frame.height),
                    fill=(145, 145, 140, 255),
                )
            background.save(output_dir / frames[0].filename, format="PNG", optimize=True)
            files.add(frames[0].filename)
            background.close()

            controls = ("human", "weak", "good", "awesome")
            for index in range(1, 17):
                local_index = (index - 1) % 8
                control_index = local_index % 4
                selected = local_index >= 4
                frame = frames[index]
                image = _resized_melee_template(
                    Image,
                    control_templates[(controls[control_index], selected)],
                    (frame.width, frame.height),
                )
                _draw_melee_lines(
                    image,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    SUPER_MELEE_CONTROL_LABELS[control_index],
                    (
                        max(1, variant.scale),
                        max(1, variant.scale),
                        round(frame.width * 0.68),
                        frame.height - max(1, variant.scale),
                    ),
                    fill=(170, 255, 255, 255) if selected else (18, 169, 226, 255),
                    stroke_width=variant.scale // 2 if selected else 0,
                    stroke_fill=(0, 70, 180, 230),
                )
                image.save(output_dir / frame.filename, format="PNG", optimize=True)
                image.close()
                files.add(frame.filename)

            button_labels = {
                17: ("載入", False),
                18: ("儲存", False),
                19: ("載入", True),
                20: ("儲存", True),
                21: ("儲存", False),
                22: ("載入", False),
                23: ("儲存", True),
                24: ("載入", True),
                29: ("離開", False),
                30: ("離開", True),
            }
            for index, (label, selected) in button_labels.items():
                frame = frames[index]
                image = Image.new("RGBA", (frame.width, frame.height), (0, 0, 0, 0))
                _draw_melee_lines(
                    image,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    (label,),
                    (0, 0, frame.width, frame.height),
                    fill=(255, 235, 0, 255) if selected else (145, 145, 140, 255),
                    stroke_width=variant.scale // 3 if selected else 0,
                    stroke_fill=(55, 25, 0, 255),
                )
                image.save(output_dir / frame.filename, format="PNG", optimize=True)
                image.close()
                files.add(frame.filename)

            for index in (25, 26):
                frame = frames[index]
                selected = index == 26
                image = _resized_melee_template(
                    Image, clean_battle, (frame.width, frame.height)
                )
                box = _battle_label_box(image.size)
                label = "開戰！"
                _draw_melee_lines(
                    image,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    (label,),
                    box,
                    fill=(255, 240, 0, 255) if selected else (255, 255, 255, 255),
                    weight=600,
                    stroke_width=max(1, variant.scale // 2),
                    stroke_fill=(35, 0, 35, 255),
                )
                image.save(output_dir / frame.filename, format="PNG", optimize=True)
                image.close()
                files.add(frame.filename)

            for index in range(31, 35):
                frame = frames[index]
                selected = index in (32, 34)
                image = _resized_melee_template(
                    Image,
                    network_templates[selected],
                    (frame.width, frame.height),
                )
                _draw_melee_lines(
                    image,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    SUPER_MELEE_NETWORK_LABEL,
                    (
                        max(1, variant.scale),
                        max(1, variant.scale),
                        round(frame.width * 0.67),
                        frame.height - max(1, variant.scale),
                    ),
                    fill=(170, 255, 255, 255) if selected else (18, 169, 226, 255),
                    stroke_width=variant.scale // 2 if selected else 0,
                    stroke_fill=(0, 70, 180, 230),
                )
                image.save(output_dir / frame.filename, format="PNG", optimize=True)
                image.close()
                files.add(frame.filename)

            for filename, selected in (("netplay-004.png", False), ("netplay-005.png", True)):
                matching = next(frame for frame in frames if frame.filename == filename)
                image = Image.new(
                    "RGBA", (matching.width, matching.height), (0, 0, 0, 0)
                )
                label = "連線"
                _draw_melee_lines(
                    image,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    (label,),
                    (0, 0, matching.width, matching.height),
                    fill=(255, 235, 0, 255) if selected else (145, 145, 140, 255),
                    stroke_width=variant.scale // 3 if selected else 0,
                    stroke_fill=(55, 25, 0, 255),
                )
                image.save(output_dir / filename, format="PNG", optimize=True)
                image.close()
                files.add(filename)

            native_scale = variant.scale // 4
            (output_dir / "meleemenu.ani").write_bytes(
                native_resolution_manifest(
                    ani_raw,
                    f"{variant.source_prefix}/meleemenu.ani",
                    scale=native_scale,
                    # Frame 27 is generated by shipinfoassets immediately
                    # after this function. Frame 28 remains stock and is
                    # enlarged by the runtime.
                    native_frames={*files, "meleemenu-027.png"},
                )
            )
            files.add("meleemenu.ani")
            report[variant.addon] = {
                "resource": f"{variant.output_prefix}/meleemenu.ani",
                "title": SUPER_MELEE_TITLE,
                "controls": ["".join(lines) for lines in SUPER_MELEE_CONTROL_LABELS],
                "network_control": "".join(SUPER_MELEE_NETWORK_LABEL),
                "buttons": dict(SUPER_MELEE_BUTTON_LABELS),
                "font_weight": SUPER_MELEE_FONT_WEIGHT,
                "frame_count": len(frames),
                "files": sorted(files),
            }
    finally:
        clean_background.close()
        clean_battle.close()
        for image in control_templates.values():
            image.close()
        for image in network_templates.values():
            image.close()
    return report


def build_localized_main_menus(
    resolver: ContentResolver,
    shadow_trees_root: Path,
    clean_background: Path,
    font_path: Path,
) -> dict[str, dict[str, object]]:
    Image, ImageDraw, ImageFont = _load_pillow()
    clean_background = clean_background.resolve()
    if not clean_background.is_file():
        raise LocError(f"Clean main-menu background not found: {clean_background}")
    try:
        source = Image.open(clean_background).convert("RGB")
    except OSError as exc:
        raise LocError(f"Cannot load clean main-menu background {clean_background}: {exc}") from exc
    if source.width * 3 != source.height * 4:
        source.close()
        raise LocError(
            f"Clean main-menu background must be exactly 4:3, found {source.width}x{source.height}"
        )

    report: dict[str, dict[str, object]] = {}
    try:
        for variant in MENU_VARIANTS:
            ani_raw, frames = _parse_frames(resolver, variant.stem, Image)
            frames = [
                MenuFrame(
                    frame.filename,
                    frame.width * variant.native_scale,
                    frame.height * variant.native_scale,
                    frame.x * variant.native_scale,
                    frame.y * variant.native_scale,
                )
                for frame in frames
            ]
            background_frame = frames[0]
            output_dir = shadow_trees_root / variant.addon / "base" / "ui"
            output_dir.mkdir(parents=True, exist_ok=True)
            background = source.resize(
                (background_frame.width, background_frame.height),
                resample=Image.Resampling.LANCZOS,
            ).convert("RGBA")
            _draw_menu_key_help(background, Image, ImageDraw, ImageFont, font_path)
            for label, frame in zip(MENU_LABELS, frames[1:]):
                overlay = Image.new("RGBA", (frame.width, frame.height), (255, 255, 255, 0))
                _draw_tracked_centered(
                    overlay,
                    ImageDraw,
                    ImageFont,
                    font_path,
                    label,
                    fill=(255, 255, 255, 255),
                )
                coverage = overlay.getchannel("A")
                overlay = _effect_map_from_mask(
                    Image, coverage, MENU_SELECTED_COLOR
                )
                colored = Image.new("RGBA", overlay.size, MENU_NORMAL_COLOR)
                colored.putalpha(coverage)
                background.alpha_composite(colored, (frame.x, frame.y))
                overlay.save(output_dir / frame.filename, format="PNG", optimize=True)
            background.convert("RGB").save(
                output_dir / background_frame.filename, format="PNG", optimize=True
            )
            ani_path = f"base/ui/{variant.stem}.ani"
            (output_dir / f"{variant.stem}.ani").write_bytes(
                native_resolution_manifest(
                    ani_raw,
                    ani_path,
                    scale=variant.native_scale,
                )
            )
            report[variant.addon] = {
                "resource": f"base/ui/{variant.stem}.ani",
                "labels": list(MENU_LABELS),
                "font_weight": MENU_FONT_WEIGHT,
                "normal_color": list(MENU_NORMAL_COLOR),
                "selected_color": list(MENU_SELECTED_COLOR),
                "canvas": [background_frame.width, background_frame.height],
                "files": 7,
            }
    finally:
        source.close()
    return report
