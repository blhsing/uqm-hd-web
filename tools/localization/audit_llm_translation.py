#!/usr/bin/env python3
"""Quality audit for the LLM-authored Traditional Chinese UQM record set."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
CJK_RE = re.compile(r"[\u3400-\u9fff]")
# High-signal simplified-only forms; this is a warning list, not a converter.
SIMPLIFIED_RE = re.compile(
    "[这们为个发觉产东丝丢两严丧丰临义乌乐习乡书买乱争亏亚亲亿仅从仓仪价众优伞伟传伤伦体侠侣侦侧侨侩侪侬俩俭债倾偿储儿兑党兰关兴养兽冈册写军农冲决况冻净凉减几凤凭凯击凿刍划刘则刚创删别剂剑剧劝办务动劳势勋匀区医华协单卖卢卫却厂历厉压厌厕厢厦厨县叁参双变叙叶号叹吓吗听启吴员呛呜咏咙咸响哑哗哟唤啧喷嘱团园围国图圆圣场坏块坚坛坝坞坟坠垄垒垦执扩扫扬扰抚抛护报担拟拢拣拥拦拧拨择挂挚挛挜挝挞挟挠挡挣挤挥挽捞损换捣据掳掷掺揽搀搁搂搅携摄摆摇摊撑撵敌敛数斋斓斗断无旧时旷显晋晓晕暂术机杀杂权条来杨极构枪柜标栋栏树样桥桨梦检楼欢欧歼残殴毁毕气汇汉汤沟没沥沦沧沪泛泞泪泻泼泽洁洒浅浆浇浊测济浓涛涝涡涣涤润涧涨涩淀渊渔渗温湾湿溃溅滚滞满滤滥滨滩潜潴澜濑灭灯灵灾灿炉炖炼烁烂烛烟烦烧烩烫热爱爷牵犹狈狞独狭狮狱猎猪猫献玛环现玑玺电画畅疗疟疡疯痪瘫皑皱盖盗盘着睁睐瞒矿码砖砚砾础硕确碍礼祸禅离秃种积称稳窃竞笔笼笾筑筛签简箩篮篱类粮紧纠红纤约级纪纯纱纲纳纵纷纸纹纺纽线练组细织终绍经绑绒结绕绘给络绝绞统绣继绩绪续绳维绵绷综绿缀缄缅缆缓编缘缚缝缠缩缴网罗罚罢羡耸联聪肃肠肤肿胀胆胜胧脉胶脏脑脓脚脱脸腊腻腾舰舱艳艺节芜苇苏范茧荐药获莲莱萝营萧萨蓝虚虫虽虾蚀蚁蚂蛊蜕蜗蝇蝉蝼蠢补袭装裤见观规觅视览觉触订计认讨让训议讯记讲讳讴讶许论讼设访证评识诈诉诊词译试诗诚诛话该详语误诱说请诸诺读课谁调谈谊谋谢谣谬谭谱贝贞负贡财责贤败账货质贩贪贫贯贵贷费贺贼贾赃资赋赌赏赔赖赚赛赞赠赵赶趋跃践踪车轨轩转轮软轰轻载较辅辆辈辉辐辑输辕辖辙辞辩辽达迁过迈运还进远违连迟适选逊递逻遗邮邻郑酝酱酿释鉴针钉钙钝钞钟钢钦钥钩钱钳钻铁铃铅铎铜铠铢铭铲银铸铺链销锁锈锅锋锐错锚锡锤锦键锯锰锻镰长门闪闭问闯闷闸闹闻阁阀阅队阳阴阵阶际陆陈陨险随隐难雏雾静顶项顺须顾颂预颅领颇颈颗题颜额风飒飘飞饥饭饮饰饱饲饵饼饿馆馋马驭驯驰驱驳驴驶驷驹驻骑骗骚骤鱼鲁鲍鲜鸟鸡鸣鸥鸦鸭鸯鸳鸿鹅鹏鹰麦黄齐齿龙龟]"
)


def load(path: Path) -> list[dict[str, str]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(value, dict):
        value = value["records"]
    return value


def term_pattern(term: str) -> re.Pattern[str]:
    left = r"(?<![A-Za-z0-9_])" if term and (term[0].isalnum() or term[0] == "_") else ""
    right = r"(?![A-Za-z0-9_])" if term and (term[-1].isalnum() or term[-1] == "_") else ""
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--translation", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    source_rows = load(args.source)
    translated_rows = load(args.translation)
    source = {row["id"]: row["text"] for row in source_rows}
    translated = {row["id"]: row["text"] for row in translated_rows}
    glossary = json.loads(args.glossary.read_text(encoding="utf-8-sig"))

    unchanged: list[str] = []
    english_heavy: list[dict[str, object]] = []
    simplified: list[dict[str, str]] = []
    invalid_unicode: list[str] = []
    glossary_warnings: list[dict[str, object]] = []
    for record_id, text in translated.items():
        original = source[record_id]
        if (
            text == original
            and "/cutscene/spins/" not in record_id.replace("\\", "/")
            and not record_id.replace("\\", "/").startswith("base/ui/joyalpha.txt::")
            and len(original) >= 20
            and ASCII_WORD_RE.search(original)
        ):
            unchanged.append(record_id)
        ascii_letters = sum(character.isascii() and character.isalpha() for character in text)
        cjk = len(CJK_RE.findall(text))
        if len(original) >= 60 and ascii_letters > max(24, cjk):
            english_heavy.append({"id": record_id, "ascii_letters": ascii_letters, "cjk": cjk})
        chars = sorted(set(SIMPLIFIED_RE.findall(text)))
        if chars:
            simplified.append({"id": record_id, "characters": "".join(chars)})
        if "\ufffd" in text or any(ord(character) > 0xFFFF for character in text):
            invalid_unicode.append(record_id)

    for term, target in glossary.items():
        if term.casefold() == target.casefold():
            continue
        pattern = term_pattern(term)
        for record_id, original in source.items():
            occurrences = len(pattern.findall(original))
            if occurrences and translated[record_id].count(target) < occurrences:
                glossary_warnings.append({
                    "id": record_id,
                    "term": term,
                    "target": target,
                    "source_occurrences": occurrences,
                    "target_occurrences": translated[record_id].count(target),
                })

    report = {
        "records": len(translated_rows),
        "source_characters": sum(len(row["text"]) for row in source_rows),
        "translated_characters": sum(len(row["text"]) for row in translated_rows),
        "cjk_characters": sum(len(CJK_RE.findall(row["text"])) for row in translated_rows),
        "unchanged_long_records": unchanged,
        "english_heavy_records": english_heavy,
        "simplified_character_warnings": simplified,
        "invalid_unicode_records": invalid_unicode,
        "glossary_warnings": glossary_warnings,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered)
    return 1 if unchanged or invalid_unicode else 0


if __name__ == "__main__":
    raise SystemExit(main())
