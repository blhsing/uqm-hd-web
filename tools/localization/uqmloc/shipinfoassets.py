from __future__ import annotations

import io
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .ani import native_resolution_manifest
from .core import ContentResolver, LocError


@dataclass(frozen=True)
class ShipInfoVariant:
    addon: str
    ui_prefix: str
    spin_prefix: str
    canvas: tuple[int, int]
    native_scale: int


@dataclass(frozen=True)
class ShipInfoPage:
    index: int
    stem: str
    name: str
    tagline: str
    crew: int
    energy: int
    cost: int
    movement: str
    weapon: str
    special: str
    tactics: str


SHIP_INFO_VARIANTS = (
    ShipInfoVariant(
        "native1080-zh_TW",
        "addons/hires4x/ui",
        "addons/hires4x/cutscene/spins",
        (2560, 1920),
        2,
    ),
)


# The descriptions intentionally mirror the terminology used by README.md.
# Keeping this data in source form makes the baked image translation reviewable
# and reproducible instead of hiding it in manually edited PNG files.
SHIP_INFO_PAGES = (
    ShipInfoPage(
        0,
        "androsynth",
        "安德羅辛斯・守護艦",
        "追蹤酸泡泡與高速彗星衝撞",
        20,
        24,
        15,
        "極速 24（彗星 60）　加速 0.33 秒　轉向 3.33 秒（彗星 1.33 秒）",
        "發射耐久、長壽命的追蹤酸泡泡。",
        "化為高速彗星，以船體衝撞造成傷害。",
        "先用泡泡封鎖航線，再變形追擊；能量耗盡會強制復原。",
    ),
    ShipInfoPage(
        1,
        "arilou",
        "阿里盧拉萊萊・小艇",
        "無慣性近戰艦與隨機瞬移",
        6,
        20,
        16,
        "極速 40　加速 0.04 秒　轉向 0.67 秒",
        "近距離雷射會自動瞄準敵艦。",
        "隨機瞬移到戰場另一處。",
        "可立即改向並繞背；船員少、射程短，瞬移落點也不可控。",
    ),
    ShipInfoPage(
        2,
        "chenjesu",
        "陳傑蘇・育巢艦",
        "重型水晶炮與干擾衛星",
        36,
        30,
        28,
        "極速 27　加速 1.88 秒　轉向 4.67 秒",
        "水晶彈傷害高；放開射擊鍵可炸成碎片。",
        "放出干擾衛星，撞擊時推開敵艦並抽走能量。",
        "擅長區域控制，但加速與轉向緩慢；召喚衛星需要滿能量。",
    ),
    ShipInfoPage(
        3,
        "chmmr",
        "克姆爾混合種・化身艦",
        "近距雷射、護航衛星與牽引光束",
        42,
        42,
        30,
        "極速 35　加速 1.25 秒　轉向 2.67 秒",
        "連續雷射配合三枚自動攔截、攻擊的護航衛星。",
        "牽引光束把敵艦拉向本艦。",
        "把敵人拖入雷射殺傷圈；體型大、轉向慢，衛星也可能被擊毀。",
    ),
    ShipInfoPage(
        4,
        "druuge",
        "德魯吉・重擊艦",
        "超長射程重炮與強烈後座力",
        14,
        32,
        17,
        "極速 20　加速 0.83 秒　轉向 3.33 秒",
        "遠程炮彈造成高傷害，並把本艦向後猛推。",
        "犧牲一名船員，立即回復大量能量。",
        "利用後座力移動與狙擊；自然回能極慢，必須珍惜船員。",
    ),
    ShipInfoPage(
        5,
        "earthling",
        "地球人・巡洋艦",
        "長距追蹤核彈與點防禦",
        18,
        18,
        11,
        "極速 24　加速 1.67 秒　轉向 1.33 秒",
        "發射長距離追蹤核彈。",
        "近距離點防禦雷射會攻擊周遭威脅。",
        "遠距離消耗並攔截來襲武器；核彈可被擊落，近戰較弱。",
    ),
    ShipInfoPage(
        6,
        "ilwrath",
        "伊爾拉斯・復仇艦",
        "隱形突襲與近距火焰",
        22,
        16,
        10,
        "極速 25　加速 0.21 秒　轉向 2.00 秒",
        "船首噴出高傷害的短距離火焰。",
        "進入隱形；隱形中開火會自動朝向敵艦。",
        "隱形接近後貼身噴火；沒有遠程手段，位置仍可被推測。",
    ),
    ShipInfoPage(
        7,
        "kohr-ah",
        "克爾阿・掠奪艦",
        "旋鋸雷區與環形火焰氣雲",
        42,
        42,
        30,
        "極速 30　加速 1.46 秒　轉向 3.33 秒",
        "最多部署八枚耐久旋鋸，放開射擊後會追蹤近敵。",
        "向十六個方向爆出火焰氣雲。",
        "擅長布置雷區與近身清場；環形爆發會消耗一半能量。",
    ),
    ShipInfoPage(
        8,
        "melnorme",
        "梅爾諾姆・商旅艦",
        "四級蓄力炮與混亂射線",
        20,
        42,
        18,
        "極速 36　加速 1.25 秒　轉向 3.33 秒",
        "能量彈可蓄力四級，傷害逐級倍增。",
        "混亂射線迫使敵艦轉向，並暫時封鎖其特殊動作。",
        "先以射線控制，再用滿蓄力彈收尾；兩種攻擊都需要能量管理。",
    ),
    ShipInfoPage(
        9,
        "mmrnmhrm",
        "姆爾恩姆赫姆・變形艦",
        "靈活飛碟與高速火箭雙形態",
        20,
        10,
        19,
        "飛碟：極速 20　加速 0.33 秒　轉向 2.00 秒；火箭：極速 50　加速 0.21 秒　轉向 10.00 秒",
        "飛碟使用雙雷射；火箭使用追蹤飛彈。",
        "消耗全部能量，在飛碟與火箭形態間切換。",
        "依對手切換靈活近戰或高速遠攻；兩種形態各有明顯弱點。",
    ),
    ShipInfoPage(
        10,
        "mycon",
        "邁康・孢子艦",
        "追蹤等離子體與船員再生",
        20,
        40,
        21,
        "極速 27　加速 0.88 秒　轉向 4.67 秒",
        "追蹤等離子體初始威力高，飛行越久越弱。",
        "消耗全部能量，恢復最多四名船員。",
        "適合遠距消耗與長局續戰；船體遲鈍，等離子體可被攔截。",
    ),
    ShipInfoPage(
        11,
        "orz",
        "奧茲・復仇女神艦",
        "旋轉炮塔與太空陸戰隊",
        16,
        20,
        23,
        "極速 35　加速 0.29 秒　轉向 1.33 秒",
        "炮塔可獨立旋轉，航行時仍能向其他方向射擊。",
        "派出太空陸戰隊；每隊暫時占用一名本艦船員。",
        "陸戰隊能直接削減敵船員；過度部署也會掏空本艦人力。",
    ),
    ShipInfoPage(
        12,
        "pkunk",
        "普坎克・狂怒艦",
        "三向射擊、辱罵回能與機率復活",
        8,
        12,
        20,
        "極速 64　加速 0.17 秒　轉向 0.67 秒",
        "同時向前方、左側與右側射擊。",
        "辱罵敵人回復能量；被摧毀時有一半機率復活。",
        "速度與轉向極佳，但船員少、單發傷害低，復活也全憑運氣。",
    ),
    ShipInfoPage(
        13,
        "shofixti",
        "索菲克斯提・偵察艦",
        "低費用炮艦與榮光自爆裝置",
        6,
        4,
        5,
        "極速 35　加速 0.29 秒　轉向 1.33 秒",
        "發射威力較弱的正面炮彈。",
        "連續觸發可啟動榮光裝置，自爆重創近敵。",
        "適合用低費用交換昂貴大船；常規戰力弱，自爆也會失去本艦。",
    ),
    ShipInfoPage(
        14,
        "slylandro",
        "斯萊蘭卓・探測器",
        "固定高速、追蹤閃電與小行星充能",
        12,
        20,
        17,
        "固定極速 60　瞬時加速　轉向 0.67 秒",
        "近距離閃電會追蹤敵艦。",
        "吸收完整的小行星即可補滿能量；推進鍵會立即反轉。",
        "永遠高速且不能停船；沒有自然回能，必須尋找小行星。",
    ),
    ShipInfoPage(
        15,
        "spathi",
        "斯帕西・逃逸艦",
        "高速逃逸與船尾追蹤飛彈",
        30,
        10,
        18,
        "極速 48　加速 0.33 秒　轉向 1.33 秒",
        "船首發射威力較弱的常規彈。",
        "從船尾發射追蹤飛彈。",
        "一面逃跑一面反向射擊；必須讓敵艦保持在船尾方向。",
    ),
    ShipInfoPage(
        16,
        "supox",
        "蘇波克斯・刀鋒艦",
        "快速正面炮與全向平移",
        12,
        16,
        16,
        "極速 40　加速 0.21 秒　轉向 1.33 秒",
        "發射快速的正面炮彈。",
        "配合方向鍵可後退、側移或斜移，艦首方向不變。",
        "能保持瞄準並閃避，操作上限高；船員少且常規火力較弱。",
    ),
    ShipInfoPage(
        17,
        "syreen",
        "賽琳・穿透艦",
        "船員召喚與近距兵力奪取",
        12,
        16,
        13,
        "極速 36　加速 0.33 秒　轉向 1.33 秒",
        "發射簡單而快速的正面炮。",
        "歌聲使近敵船員飄出太空；接觸後可收編。",
        "貼近高船員目標能反轉兵力差；接近過程危險，對無人艦無效。",
    ),
    ShipInfoPage(
        18,
        "thraddash",
        "瑟拉達什・火炬艦",
        "後燃器衝刺與傷害火焰軌跡",
        8,
        24,
        10,
        "極速 28（後燃 72）　加速 0.17 秒　轉向 1.33 秒",
        "發射威力較低的常規炮彈。",
        "後燃器提供爆發高速，並留下可傷敵的火焰。",
        "適合突襲、脫離或誘敵追入火焰；船員少，十分依賴路線規劃。",
    ),
    ShipInfoPage(
        19,
        "umgah",
        "烏姆加・無人機",
        "反物質錐與高速倒衝",
        10,
        30,
        7,
        "極速 18　加速 0.50 秒　轉向 3.33 秒",
        "船首反物質錐持續攻擊，也能摧毀近距彈體。",
        "朝船尾方向高速倒衝。",
        "用倒衝貼近或逃離，再以錐形武器磨碎敵人；射程極短。",
    ),
    ShipInfoPage(
        20,
        "ur-quan",
        "烏爾關・無畏艦",
        "重型融合炮與載人戰鬥機",
        42,
        42,
        30,
        "極速 30　加速 1.46 秒　轉向 3.33 秒",
        "船首發射重型融合彈。",
        "派出載人戰鬥機追擊敵艦；返艦後船員才會歸隊。",
        "耐久、火力與持續騷擾俱佳；體型大、轉向慢，戰機也可能損失。",
    ),
    ShipInfoPage(
        21,
        "utwig",
        "烏特維格・巨獸艦",
        "免費齊射與吸收傷害的護盾",
        20,
        20,
        22,
        "極速 36　加速 1.75 秒　轉向 1.33 秒",
        "多管正面齊射不消耗能量。",
        "護盾消耗能量，並把吸收的武器傷害轉回能量。",
        "善於反制高傷害彈體；沒有自然回能，空按護盾會耗乾電池。",
    ),
    ShipInfoPage(
        22,
        "vux",
        "VUX・入侵艦",
        "近距雷射、寄生體與開場突進",
        20,
        40,
        12,
        "極速 21　加速 0.63 秒　轉向 4.67 秒",
        "近距離連續雷射造成高傷害。",
        "追蹤寄生體會永久降低敵艦的加速與轉向。",
        "開戰常躍遷到近敵位置；突擊失敗後，本艦低速弱點十分明顯。",
    ),
    ShipInfoPage(
        23,
        "yehat",
        "耶哈特・終結艦",
        "快速雙炮與短暫全向護盾",
        20,
        10,
        23,
        "極速 30　加速 0.63 秒　轉向 2.00 秒",
        "快速發射兩枚並列炮彈。",
        "啟動短暫的全向護盾。",
        "機動良好，可在護盾間隙換血；能量槽小，誤開會快速失去防禦。",
    ),
    ShipInfoPage(
        24,
        "zoqfot",
        "佐克－福特－皮克・毒刺艦",
        "低費用炮艦與致命近距舌擊",
        10,
        10,
        6,
        "極速 40　加速 0.17 秒　轉向 1.33 秒",
        "發射威力較弱的正面炮彈。",
        "極短距離舌擊消耗 7 點能量，造成 12 點傷害。",
        "低費用伏擊艦；貼身舌擊能擊殺昂貴目標，但距離非常短。",
    ),
)


SHIP_PICK_LABELS = {
    "pick_ship": "選擇船艦",
    "ship_info": "船艦資料",
    "more_ships": "想要更多船艦？",
    "project": "試試 Project 6014！",
}


# The stock CREW/BATT words sit below their vertical gauges.  Keep the
# localized replacement inside that wording band: the gauge artwork reaches
# y=303 on the 4x canvas, while the English glyphs occupy y=320..331.  The
# previous erase rectangles began at y=307 and consequently painted over the
# bottom of both gauges.
SHIP_INFO_GAUGE_LABEL_ERASE_BOXES = (
    (29, 315, 132, 352),
    (168, 315, 276, 352),
)
SHIP_INFO_GAUGE_LABEL_TEXT_BOXES = (
    (31, 315, 130, 348),
    (172, 315, 272, 348),
)
SHIP_INFO_PANEL_SAMPLE_BOX = (132, 315, 166, 350)


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError as exc:
        raise LocError(
            "Ship-info generation requires Pillow. Run: "
            "python -m pip install -r requirements.txt"
        ) from exc
    return Image, ImageDraw, ImageFont


def _font(ImageFont, font_path: Path, size: int, weight: int = 500):
    try:
        font = ImageFont.truetype(str(font_path), size=max(2, size))
        axes = font.get_variation_axes()
        values = [axis["default"] for axis in axes]
        for index, axis in enumerate(axes):
            name = axis.get("name", b"")
            if isinstance(name, bytes):
                name = name.decode("ascii", errors="ignore")
            if str(name).lower() == "weight":
                values[index] = min(
                    axis["maximum"], max(axis["minimum"], weight)
                )
        if axes:
            font.set_variation_by_axes(values)
        return font
    except (AttributeError, OSError) as exc:
        if isinstance(exc, OSError) and "variation" not in str(exc).lower():
            raise LocError(f"Pillow cannot load {font_path}: {exc}") from exc
        try:
            return ImageFont.truetype(str(font_path), size=max(2, size))
        except OSError as inner:
            raise LocError(f"Pillow cannot load {font_path}: {inner}") from inner


def _scaled_box(
    canvas: tuple[int, int], box: tuple[int, int, int, int]
) -> tuple[int, int, int, int]:
    sx = canvas[0] / 1280
    sy = canvas[1] / 960
    return tuple(
        round(value * (sx if index % 2 == 0 else sy))
        for index, value in enumerate(box)
    )


def _text_width(draw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _nearby_panel_background(image, canvas: tuple[int, int]):
    """Return the dominant neutral panel color beside the gauge labels."""

    sample_box = _scaled_box(canvas, SHIP_INFO_PANEL_SAMPLE_BOX)
    sample = image.crop(sample_box).convert("RGBA")
    try:
        pixels = [pixel for pixel in sample.get_flattened_data() if pixel[3]]
    finally:
        sample.close()
    neutral = [
        pixel[:3]
        for pixel in pixels
        if max(pixel[:3]) - min(pixel[:3]) <= 4
    ]
    candidates = neutral or [pixel[:3] for pixel in pixels]
    if not candidates:
        return (80, 80, 80, 255)
    color = Counter(candidates).most_common(1)[0][0]
    return (*color, 255)


def _fill_scaled_box(draw, canvas, box, *, fill) -> None:
    """Fill a scaled half-open box without touching its right/bottom edge."""

    x0, y0, x1, y1 = _scaled_box(canvas, box)
    if x1 <= x0 or y1 <= y0:
        return
    # ImageDraw.rectangle includes both endpoints.  Treating our layout boxes
    # as half-open keeps the stock x=276 divider and y=352 separator intact at
    # the native 4x tier.
    draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=fill)


def _wrap_cjk(draw, text: str, font, max_width: int) -> list[str]:
    closing_punctuation = frozenset("，。！？；：、）》】」』〕〉…‧")
    lines: list[str] = []
    current = ""
    for character in text:
        if character == "\n":
            lines.append(current)
            current = ""
            continue
        candidate = current + character
        if current and _text_width(draw, candidate, font) > max_width:
            # Never leave a closing mark alone at the start of a line.  Move
            # the previous Han character with it; the font-fitting pass can
            # then reduce the size if that two-character unit is still wide.
            if character in closing_punctuation and len(current) > 1:
                lines.append(current[:-1])
                current = current[-1] + character
            elif character in closing_punctuation:
                current += character
            else:
                lines.append(current)
                current = character
        else:
            current = candidate
    if current or not lines:
        lines.append(current)
    return lines


def _fit_wrapped(
    draw,
    ImageFont,
    font_path: Path,
    text: str,
    box: tuple[int, int, int, int],
    *,
    max_size: int,
    min_size: int,
    weight: int,
    max_lines: int,
):
    width = max(1, box[2] - box[0])
    height = max(1, box[3] - box[1])
    for size in range(max_size, min_size - 1, -1):
        font = _font(ImageFont, font_path, size, weight)
        lines = _wrap_cjk(draw, text, font, width)
        spacing = max(0, round(size * 0.18))
        line_boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_heights = [bounds[3] - bounds[1] for bounds in line_boxes]
        total_height = sum(line_heights) + spacing * max(0, len(lines) - 1)
        if len(lines) <= max_lines and total_height <= height:
            return font, lines, line_boxes, spacing
    font = _font(ImageFont, font_path, min_size, weight)
    lines = _wrap_cjk(draw, text, font, width)[:max_lines]
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    return font, lines, boxes, 0


def _draw_wrapped(
    draw,
    ImageFont,
    font_path: Path,
    text: str,
    box: tuple[int, int, int, int],
    *,
    fill,
    max_size: int,
    min_size: int,
    weight: int = 500,
    max_lines: int = 4,
    center: bool = False,
) -> None:
    font, lines, bounds, spacing = _fit_wrapped(
        draw,
        ImageFont,
        font_path,
        text,
        box,
        max_size=max_size,
        min_size=min_size,
        weight=weight,
        max_lines=max_lines,
    )
    heights = [bound[3] - bound[1] for bound in bounds]
    total_height = sum(heights) + spacing * max(0, len(lines) - 1)
    y = box[1] + (box[3] - box[1] - total_height) / 2
    for line, bound, line_height in zip(lines, bounds, heights):
        width = bound[2] - bound[0]
        x = box[0] + ((box[2] - box[0] - width) / 2 if center else 0) - bound[0]
        draw.text((round(x), round(y - bound[1])), line, font=font, fill=fill)
        y += line_height + spacing


def _draw_card(
    overlay,
    ImageDraw,
    ImageFont,
    font_path: Path,
    canvas: tuple[int, int],
    box4x: tuple[int, int, int, int],
    heading: str,
    body: str,
) -> None:
    box = _scaled_box(canvas, box4x)
    draw = ImageDraw.Draw(overlay, "RGBA")
    scale = canvas[0] / 320
    radius = max(1, round(scale * 2.5))
    line_width = max(1, round(scale))
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=(0, 4, 35, 214),
        outline=(88, 224, 142, 245),
        width=line_width,
    )
    padding = max(2, round(10 * canvas[0] / 1280))
    heading_height = max(7, round(37 * canvas[1] / 960))
    heading_box = (
        box[0] + padding,
        box[1] + padding,
        box[2] - padding,
        min(box[3] - padding, box[1] + padding + heading_height),
    )
    body_box = (
        box[0] + padding,
        heading_box[3],
        box[2] - padding,
        box[3] - padding,
    )
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        heading,
        heading_box,
        fill=(255, 228, 86, 255),
        max_size=max(5, round(25 * canvas[0] / 1280)),
        min_size=max(4, round(17 * canvas[0] / 1280)),
        weight=650,
        max_lines=1,
    )
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        body,
        body_box,
        fill=(181, 255, 197, 255),
        max_size=max(5, round(23 * canvas[0] / 1280)),
        min_size=max(4, round(15 * canvas[0] / 1280)),
        weight=450,
        max_lines=5,
    )


def _render_ship_info_frames(
    Image,
    ImageDraw,
    ImageFont,
    source,
    page: ShipInfoPage,
    font_path: Path,
):
    base = source.convert("RGBA")
    canvas = base.size
    if canvas[0] * 3 != canvas[1] * 4:
        base.close()
        raise LocError(f"Ship-info canvas must be exactly 4:3, found {canvas}")
    draw = ImageDraw.Draw(base, "RGBA")

    # Remove every English text-bearing region from the stock frame while
    # retaining the ship portrait, gauges, icon row, and battle artwork.
    draw.rectangle(_scaled_box(canvas, (185, 6, 1025, 91)), fill=(2, 5, 17, 255))
    # Long stock taglines begin left of the nominal centre header.  The narrow
    # gap beside the portrait is slightly darker than the main header, so
    # restore both source tones while removing every pale English pixel.
    draw.rectangle(_scaled_box(canvas, (281, 101, 340, 239)), fill=(80, 80, 80, 255))
    draw.rectangle(_scaled_box(canvas, (340, 101, 1025, 239)), fill=(88, 88, 88, 255))
    panel_background = _nearby_panel_background(base, canvas)
    for box in SHIP_INFO_GAUGE_LABEL_ERASE_BOXES:
        _fill_scaled_box(draw, canvas, box, fill=panel_background)
    draw.rectangle(_scaled_box(canvas, (1040, 256, 1250, 350)), fill=(4, 5, 91, 255))

    # The Shofixti pilot portrait contains a baked DESTRUCT readout.  It is
    # interface wording rather than vessel artwork, so localize that miniature
    # panel as well while preserving its green indicator at the far right.
    if page.stem == "shofixti":
        destruction_box = _scaled_box(canvas, (1036, 204, 1168, 232))
        draw.rectangle(destruction_box, fill=(84, 84, 84, 255))
        _draw_wrapped(
            draw,
            ImageFont,
            font_path,
            "自爆",
            destruction_box,
            fill=(168, 168, 168, 255),
            max_size=max(5, round(24 * canvas[0] / 1280)),
            min_size=max(4, round(15 * canvas[0] / 1280)),
            weight=600,
            max_lines=1,
            center=True,
        )

    title_scale = canvas[0] / 1280
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        "超級對戰",
        _scaled_box(canvas, (210, 10, 1000, 84)),
        fill=(244, 109, 255, 255),
        max_size=max(7, round(57 * title_scale)),
        min_size=max(6, round(38 * title_scale)),
        weight=650,
        max_lines=1,
        center=True,
    )
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        page.name,
        _scaled_box(canvas, (350, 109, 1015, 160)),
        fill=(236, 236, 236, 255),
        max_size=max(6, round(34 * title_scale)),
        min_size=max(5, round(24 * title_scale)),
        weight=600,
        max_lines=1,
        center=True,
    )
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        page.tagline,
        _scaled_box(canvas, (355, 163, 1010, 228)),
        fill=(190, 190, 190, 255),
        max_size=max(5, round(26 * title_scale)),
        min_size=max(4, round(18 * title_scale)),
        weight=450,
        max_lines=2,
        center=True,
    )
    for label, box in zip(
        ("船員", "能量"), SHIP_INFO_GAUGE_LABEL_TEXT_BOXES
    ):
        _draw_wrapped(
            draw,
            ImageFont,
            font_path,
            label,
            _scaled_box(canvas, box),
            fill=(20, 20, 20, 255),
            max_size=max(5, round(25 * title_scale)),
            min_size=max(4, round(17 * title_scale)),
            weight=600,
            max_lines=1,
            center=True,
        )
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        f"費用\n{page.cost}",
        _scaled_box(canvas, (1042, 263, 1248, 346)),
        fill=(74, 119, 255, 255),
        max_size=max(5, round(29 * title_scale)),
        min_size=max(4, round(18 * title_scale)),
        weight=600,
        max_lines=2,
        center=True,
    )

    overlay = Image.new("RGBA", canvas, (0, 0, 0, 0))
    _draw_card(
        overlay,
        ImageDraw,
        ImageFont,
        font_path,
        canvas,
        (24, 395, 432, 650),
        "武器",
        page.weapon,
    )
    _draw_card(
        overlay,
        ImageDraw,
        ImageFont,
        font_path,
        canvas,
        (848, 395, 1256, 650),
        "特殊能力",
        page.special,
    )
    stats = (
        f"船員 {page.crew}　能量 {page.energy}　費用 {page.cost}\n"
        f"{page.movement}\n{page.tactics}"
    )
    _draw_card(
        overlay,
        ImageDraw,
        ImageFont,
        font_path,
        canvas,
        (245, 694, 1035, 929),
        "性能與戰法",
        stats,
    )
    return base, overlay


def _parse_ship_animation(
    resolver: ContentResolver, path: str, page: ShipInfoPage
) -> bytes:
    raw = resolver.read_bytes(path)
    try:
        rows = [line for line in raw.decode("ascii").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise LocError(f"{path}: expected an ASCII animation manifest") from exc
    expected = (f"{page.stem}.png", f"{page.stem}-ovl.png")
    filenames = tuple(row.split()[0] for row in rows)
    if filenames != expected:
        raise LocError(
            f"{path}: expected frames {expected}, found {filenames}"
        )
    return raw


def _erase_side_wording(image, box: tuple[int, int, int, int]) -> None:
    """Replace a blue vertical English label with brushed-metal row colors."""

    pixels = image.load()
    x0, y0, x1, y1 = box
    for y in range(y0, y1):
        samples = []
        for x in range(x0, x1):
            red, green, blue = pixels[x, y][:3]
            if not (blue > 70 and blue > red * 1.22 and blue > green * 1.12):
                samples.append((red, green, blue))
        if not samples:
            fill = (125, 125, 122)
        else:
            samples.sort()
            fill = samples[len(samples) // 2]
        for x in range(x0, x1):
            pixels[x, y] = (*fill, 255)


def _draw_vertical_label(
    image,
    ImageDraw,
    ImageFont,
    font_path: Path,
    text: str,
    box: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width = box[2] - box[0]
    height = box[3] - box[1]
    size = max(5, round(width * 0.62))
    while size > 4:
        font = _font(ImageFont, font_path, size, weight=600)
        bounds = [draw.textbbox((0, 0), character, font=font) for character in text]
        spacing = max(1, round(size * 0.18))
        total = sum(bound[3] - bound[1] for bound in bounds) + spacing * (
            len(text) - 1
        )
        if total <= height and max(bound[2] - bound[0] for bound in bounds) <= width:
            break
        size -= 1
    y = box[1] + (height - total) / 2
    for character, bound in zip(text, bounds):
        char_width = bound[2] - bound[0]
        char_height = bound[3] - bound[1]
        x = box[0] + (width - char_width) / 2 - bound[0]
        draw.text(
            (round(x), round(y - bound[1])),
            character,
            font=font,
            fill=(20, 68, 205, 255),
            stroke_width=max(0, round(width / 30)),
            stroke_fill=(16, 34, 105, 255),
        )
        y += char_height + spacing


def _render_ship_picker_panel(
    Image,
    ImageDraw,
    ImageFont,
    source,
    font_path: Path,
):
    image = source.convert("RGBA")
    width, height = image.size
    if not (1.08 <= width / height <= 1.32):
        image.close()
        raise LocError(f"Unexpected Super Melee ship-picker canvas: {(width, height)}")
    sx = width / 508
    sy = height / 465
    left = tuple(
        round(value * (sx if index % 2 == 0 else sy))
        for index, value in enumerate((13, 74, 67, 445))
    )
    right = tuple(
        round(value * (sx if index % 2 == 0 else sy))
        for index, value in enumerate((440, 74, 495, 445))
    )
    _erase_side_wording(image, left)
    _erase_side_wording(image, right)
    _draw_vertical_label(
        image,
        ImageDraw,
        ImageFont,
        font_path,
        SHIP_PICK_LABELS["pick_ship"],
        left,
    )
    _draw_vertical_label(
        image,
        ImageDraw,
        ImageFont,
        font_path,
        SHIP_PICK_LABELS["ship_info"],
        right,
    )

    # Keep the mascot and the Project 6014 proper name, but localize its call
    # to action.  Only the original English text region is replaced.
    ad_box = (
        round(151 * sx),
        round(379 * sy),
        round(435 * sx),
        round(442 * sy),
    )
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rounded_rectangle(
        ad_box,
        radius=max(1, round(6 * sx)),
        fill=(205, 201, 195, 255),
    )
    _draw_wrapped(
        draw,
        ImageFont,
        font_path,
        f"{SHIP_PICK_LABELS['more_ships']}\n{SHIP_PICK_LABELS['project']}",
        (
            ad_box[0] + max(1, round(5 * sx)),
            ad_box[1] + max(1, round(3 * sy)),
            ad_box[2] - max(1, round(5 * sx)),
            ad_box[3] - max(1, round(3 * sy)),
        ),
        fill=(24, 22, 21, 255),
        max_size=max(5, round(20 * sx)),
        min_size=max(4, round(12 * sx)),
        weight=600,
        max_lines=2,
        center=True,
    )
    return image


def build_localized_ship_info_assets(
    resolver: ContentResolver,
    shadow_trees_root: Path,
    font_path: Path,
) -> dict[str, dict[str, object]]:
    """Build the supersampled ship picker and all 25 native ship-info pages."""

    Image, ImageDraw, ImageFont = _load_pillow()
    report: dict[str, dict[str, object]] = {}
    for variant in SHIP_INFO_VARIANTS:
        output_root = shadow_trees_root / variant.addon
        files: list[str] = []

        picker_path = f"{variant.ui_prefix}/meleemenu-027.png"
        try:
            picker_source = Image.open(io.BytesIO(resolver.read_bytes(picker_path)))
        except OSError as exc:
            raise LocError(f"Cannot load ship-picker image {picker_path}: {exc}") from exc
        picker_source = picker_source.resize(
            (
                picker_source.width * variant.native_scale,
                picker_source.height * variant.native_scale,
            ),
            resample=Image.Resampling.LANCZOS,
        )
        picker = _render_ship_picker_panel(
            Image, ImageDraw, ImageFont, picker_source, font_path
        )
        picker_source.close()
        picker_destination = output_root.joinpath(*PurePosixPath(picker_path).parts)
        picker_destination.parent.mkdir(parents=True, exist_ok=True)
        picker.save(picker_destination, format="PNG", optimize=True)
        picker.close()
        files.append(picker_path)

        for page in SHIP_INFO_PAGES:
            animation_path = f"{variant.spin_prefix}/ship{page.index:02d}.ani"
            animation = native_resolution_manifest(
                _parse_ship_animation(resolver, animation_path, page),
                animation_path,
                scale=variant.native_scale,
            )
            source_path = f"{variant.spin_prefix}/{page.stem}.png"
            try:
                source = Image.open(io.BytesIO(resolver.read_bytes(source_path)))
            except OSError as exc:
                raise LocError(f"Cannot load ship-info image {source_path}: {exc}") from exc
            expected_source = (
                variant.canvas[0] // variant.native_scale,
                variant.canvas[1] // variant.native_scale,
            )
            if source.size != expected_source:
                found = source.size
                source.close()
                raise LocError(
                    f"Unexpected {variant.addon} ship-info canvas for {source_path}: "
                    f"expected {expected_source}, found {found}"
                )
            source = source.resize(
                variant.canvas, resample=Image.Resampling.LANCZOS
            )
            base, overlay = _render_ship_info_frames(
                Image, ImageDraw, ImageFont, source, page, font_path
            )
            source.close()
            base_path = f"{variant.spin_prefix}/{page.stem}.png"
            overlay_path = f"{variant.spin_prefix}/{page.stem}-ovl.png"
            for output_path, image in ((base_path, base), (overlay_path, overlay)):
                destination = output_root.joinpath(*PurePosixPath(output_path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                image.save(destination, format="PNG", optimize=True)
                image.close()
                files.append(output_path)
            animation_destination = output_root.joinpath(
                *PurePosixPath(animation_path).parts
            )
            animation_destination.parent.mkdir(parents=True, exist_ok=True)
            animation_destination.write_bytes(animation)
            files.append(animation_path)

        report[variant.addon] = {
            "ship_picker": {
                "resource": picker_path,
                "labels": dict(SHIP_PICK_LABELS),
            },
            "ship_info": {
                "pages": len(SHIP_INFO_PAGES),
                "canvas": list(variant.canvas),
                "native_resolution": True,
                "stems": [page.stem for page in SHIP_INFO_PAGES],
            },
            "files": sorted(files),
        }
    return report
