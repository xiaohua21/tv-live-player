# -*- coding: utf-8 -*-
"""
数据解析层：解析 vbskycn/iptv 的 txt / m3u 直播源文件，
合并去重生成统一结构的 channels.json。

输出结构:
{
  "categories": ["央视频道", "卫视频道", ...],
  "channels": [
    {"name": "CCTV1", "category": "央视频道", "logo": "https://...png",
     "sources": ["http://...m3u8", "http://...m3u8"]},
    ...
  ],
  "meta": {"total_channels": N, "total_sources": M, "updated": "..."}
}
"""

import json
import os
import re
from collections import OrderedDict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 匹配 m3u EXTINF 行内的 key="value" 属性(顺序无关、可缺失)
M3U_ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')


def parse_extinf(line):
    """解析 #EXTINF 行: 返回 (display_name, attrs_dict)。
    取最后一个逗号前的部分为属性区,逗号后为显示名。"""
    content = line[len("#EXTINF:"):]
    if "," in content:
        attrs_part, display = content.rsplit(",", 1)
    else:
        attrs_part, display = content, ""
    attrs = dict(M3U_ATTR.findall(attrs_part))
    display = display.strip()
    if not display:
        display = attrs.get("tvg-name", "").strip()
    return display, attrs


def parse_txt(path):
    """解析 txt 格式: '频道名,URL' 与 '分类名,#genre#'"""
    channels = []
    cur_cat = "未分类"
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.endswith("#genre#"):
                cur_cat = line.replace("#genre#", "").split(",")[0].strip() or "未分类"
                continue
            if "," not in line:
                continue
            name, url = line.split(",", 1)
            name = name.strip()
            url = url.strip()
            if not name or not url.startswith(("http://", "https://")):
                continue
            channels.append({"name": name, "url": url, "category": cur_cat})
    return channels


def parse_m3u(path):
    """解析 m3u 格式: #EXTINF 行(带属性) + 下一行 URL"""
    channels = []
    lines = open(path, "r", encoding="utf-8-sig", errors="ignore").readlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            name, attrs = parse_extinf(line)
            logo = attrs.get("tvg-logo", "")
            group = attrs.get("group-title", "") or "未分类"
            # 下一行是 URL
            if i + 1 < len(lines):
                url = lines[i + 1].strip()
                if url.startswith(("http://", "https://")):
                    channels.append({"name": name, "url": url, "category": group.strip(), "logo": logo})
                i += 2
                continue
        i += 1
    return channels


def merge_channels(channel_records):
    """按 (分类, 频道名) 合并多 URL，保留 logo"""
    merged = OrderedDict()
    for rec in channel_records:
        key = (rec.get("category", "未分类"), rec["name"])
        if key not in merged:
            merged[key] = {
                "name": rec["name"],
                "category": rec.get("category", "未分类"),
                "logo": rec.get("logo", ""),
                "sources": [],
            }
        if rec.get("logo") and not merged[key]["logo"]:
            merged[key]["logo"] = rec["logo"]
        merged[key]["sources"].append(rec["url"])
    return list(merged.values())


def load_sources():
    """加载全部源文件并合并去重"""
    all_records = []
    for file in ["iptv4.txt", "iptv4.m3u", "iptv6.txt", "iptv6.m3u"]:
        path = os.path.join(DATA_DIR, file)
        if not os.path.exists(path):
            print(f"[parser] 跳过缺失文件: {file}")
            continue
        if file.endswith(".txt"):
            recs = parse_txt(path)
            print(f"[parser] {file}: {len(set(r['name'] for r in recs))} 个频道 / {len(recs)} 条源")
        else:
            recs = parse_m3u(path)
            print(f"[parser] {file}: {len(set(r['name'] for r in recs))} 个频道 / {len(recs)} 条源")
        all_records.extend(recs)

    channels = merge_channels(all_records)
    # 分类保持源文件顺序
    categories = list(dict.fromkeys(c["category"] for c in channels))

    result = {
        "categories": categories,
        "channels": channels,
        "meta": {
            "total_channels": len(channels),
            "total_sources": sum(len(c["sources"]) for c in channels),
            "updated": None,
        },
    }
    return result


def build():
    data = load_sources()
    out_path = os.path.join(DATA_DIR, "channels.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print("=" * 52)
    print(f"分类数       : {len(data['categories'])}")
    print(f"频道数       : {data['meta']['total_channels']}")
    print(f"总源数       : {data['meta']['total_sources']}")
    print(f"多源频道数   : {sum(1 for c in data['channels'] if len(c['sources'])>1)}")
    print(f"含logo频道数 : {sum(1 for c in data['channels'] if c.get('logo'))}")
    print(f"输出文件     : {out_path}")
    print("分类列表     :", " | ".join(data["categories"]))
    return out_path


if __name__ == "__main__":
    build()