from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json

JST = timezone(timedelta(hours=9))
UA = {"User-Agent": "FukushimaDisasterDashboard/2026"}
FEED = "https://www.data.jma.go.jp/developer/xml/feed/extra.xml"
BASE_JSON = "https://raw.githubusercontent.com/wara326-glitch/saigaijouhou/main/data/jma.json"

REGIONS = {
    "県北": ["07201","07210","07213","07214","07301","07303","07308","07322"],
    "県中": ["07203","07207","07211","07342","07344","07501","07502","07503","07504","07505","07521","07522"],
    "県南": ["07205","07461","07464","07465","07466","07481","07482","07483","07484"],
    "会津": ["07202","07208","07402","07405","07407","07408","07421","07422","07423","07444","07445","07446","07447"],
    "南会津": ["07362","07364","07367","07368"],
    "相双": ["07209","07212","07541","07542","07543","07544","07545","07546","07547","07548","07561","07564"],
    "いわき": ["07204"],
}
MUNICIPAL_CODES = {c for codes in REGIONS.values() for c in codes}


def get(url):
    with urlopen(Request(url, headers=UA), timeout=30) as r:
        return r.read()


def local(tag):
    return tag.split("}")[-1]


def first_text(node, name):
    for x in node.iter():
        if local(x.tag) == name and x.text:
            return x.text.strip()
    return ""


def entries():
    root = ET.fromstring(get(FEED))
    out = []
    for e in root.iter():
        if local(e.tag) != "entry":
            continue
        d = {}
        for x in e:
            n = local(x.tag)
            if n in ("title", "updated", "id") and x.text:
                d[n] = x.text.strip()
            if n == "link" and x.attrib.get("href"):
                d["link"] = x.attrib["href"]
        if d.get("link"):
            out.append(d)
    return out


def active(status):
    s = (status or "").strip()
    if not s:
        return True
    return not any(k in s for k in ("解除", "なし", "発表なし"))


def severity(name):
    s = (name or "").replace(" ", "").replace("　", "")
    if "レベル5" in s: return 4
    if "レベル4" in s: return 3
    if "レベル3" in s: return 2
    if "レベル2" in s: return 1
    if "特別警報" in s or "危険警報" in s: return 3
    if "警報" in s and "注意報" not in s: return 2
    if "注意報" in s: return 1
    return 0


def label(level):
    return ["発表なし", "注意", "警戒", "危険", "災害切迫"][max(0, min(4, level))]


def municipality_code(area_code):
    """Normalize JMA secondary-area codes to the parent municipality.
    Since May 2026 some cities are split into subareas (e.g. 0720301), so
    exact five-digit matching drops valid current warnings. Parent municipality
    is the first five digits for Fukushima class20-derived codes.
    """
    s = str(area_code or "").strip()
    if len(s) >= 5 and s[:5] in MUNICIPAL_CODES:
        return s[:5]
    return None


def parse_items(root):
    """Read the current Fukushima state from one VPWS50 aggregate bulletin.
    Multiple split JMA areas belonging to one municipality are merged by maximum
    severity and union of active warning/advisory names.
    """
    result = {c: {"name": "", "items": [], "level": 0, "jma_areas": []} for c in MUNICIPAL_CODES}
    found = set()

    for item in root.iter():
        if local(item.tag) not in ("Item", "Warning"):
            continue
        area = next((x for x in item.iter() if local(x.tag) == "Area"), None)
        if area is None:
            continue
        raw_code = first_text(area, "Code")
        code = municipality_code(raw_code)
        if not code:
            continue
        found.add(code)
        area_name = first_text(area, "Name")
        if area_name:
            result[code]["jma_areas"].append(area_name)
            if not result[code]["name"]:
                # Strip common split-area suffix only for compact display; retain
                # all exact JMA area names in jma_areas for audit/verification.
                result[code]["name"] = area_name

        for kind in item.iter():
            if local(kind.tag) != "Kind":
                continue
            kname = first_text(kind, "Name")
            status = first_text(kind, "Status")
            if not kname or not active(status):
                continue
            if any(k in kname for k in ("注意報", "警報", "危険警報", "特別警報")):
                result[code]["items"].append(kname)

    for d in result.values():
        d["items"] = list(dict.fromkeys(d["items"]))
        d["jma_areas"] = list(dict.fromkeys(d["jma_areas"]))
        d["level"] = max([severity(x) for x in d["items"]] or [0])
    return result, found


def latest_fukushima_aggregate():
    candidates = [e for e in entries() if "集約通報" in e.get("title", "")]
    errors = []
    for e in candidates[:250]:
        try:
            root = ET.fromstring(get(e["link"]))
            body = " ".join((x.text or "") for x in root.iter())
            if "福島県" not in body:
                continue
            municipal, found = parse_items(root)
            # All 59 parent municipalities should be represented after normalizing
            # split secondary areas. Fail closed on schema/data mismatch.
            if len(found) != 59:
                errors.append(f"Fukushima parent municipalities {len(found)}/59")
                continue
            return municipal, e
        except Exception as ex:
            errors.append(str(ex))
    raise RuntimeError("福島県の最新VPWS50集約通報を確認できません: " + "; ".join(errors[-3:]))


def load_base():
    try:
        return json.loads(get(BASE_JSON).decode("utf-8"))
    except Exception:
        return {"prefectures": {}}


def main():
    data = load_base()
    data.setdefault("prefectures", {})
    now = datetime.now(JST)
    try:
        municipal, source = latest_fukushima_aggregate()
        regions = {}
        for rn, codes in REGIONS.items():
            level = max(municipal[c]["level"] for c in codes)
            items = list(dict.fromkeys(x for c in codes for x in municipal[c]["items"]))
            affected = [municipal[c]["name"] or c for c in codes if municipal[c]["level"] > 0]
            regions[rn] = {"level": level, "label": label(level), "items": items,
                           "affected": affected, "source": "JMA VPWS50"}

        all_items = list(dict.fromkeys(x for d in municipal.values() for x in d["items"]))
        pref_level = max(d["level"] for d in municipal.values())
        data["regions"] = regions
        data["fukushima_municipalities"] = municipal
        data["prefectures"]["福島県"] = {
            "level": pref_level, "label": label(pref_level),
            "dominant": "気象" if pref_level else "平常",
            "detail": "・".join(all_items[:20]) if all_items else "現在、発表中の対象情報はありません。",
            "hazards": {"気象": {"level": pref_level, "items": all_items,
                "municipality_count": sum(1 for d in municipal.values() if d["level"] > 0),
                "source": "JMA VPWS50 current aggregate bulletin", "published": source.get("updated", "")},
                "避難情報": {"level": None, "detail": "自動取得未接続"}},
        }
        data["fukushima_source"] = {"status": "ok", "title": source.get("title", ""),
            "updated": source.get("updated", ""), "url": source.get("link", ""),
            "municipality_count": len(municipal), "normalization": "split JMA areas -> 59 municipalities"}
    except Exception as ex:
        data["regions"] = {rn: {"level": None, "label": "取得不能", "items": [], "affected": []} for rn in REGIONS}
        data["prefectures"]["福島県"] = {"level": 0, "label": "取得不能", "dominant": "取得不能",
            "detail": str(ex), "data_error": True,
            "hazards": {"気象": {"level": None, "items": [], "error": str(ex)}}}
        data["fukushima_source"] = {"status": "error", "error": str(ex)}

    data["updated"] = now.isoformat()
    data["fukushima_updated"] = now.isoformat()
    out = Path("data/jma.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
