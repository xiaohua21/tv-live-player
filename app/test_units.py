# -*- coding: utf-8 -*-
"""
集成测试：不启动 GUI, 直接验证数据层→检测层→存储层全链路。
运行: python app/test_units.py
"""

import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")
DATA_DIR = os.path.join(BASE_DIR, "data")
sys.path.insert(0, APP_DIR)

import parser as Parser
import storage as Store
import fetcher as Fetcher
import checker as Checker

PASS = 0
FAIL = 0


def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def test_parser():
    print("\n=== 1. 数据解析 ===")
    data = Parser.load_sources()
    ok("生成 channels", data["meta"]["total_channels"] > 400,
       f"channel={data['meta']['total_channels']}")
    ok("总源数合理", data["meta"]["total_sources"] > 1000,
       f"src={data['meta']['total_sources']}")
    ok("分类数合理", 5 < len(data["categories"]) < 30,
       f"cat={len(data['categories'])}")
    cctv1 = next((c for c in data["channels"] if c["name"] == "CCTV1"), None)
    ok("CCTV1 存在", cctv1 is not None)
    if cctv1:
        ok("CCTV1 多源", len(cctv1["sources"]) >= 2, f"n={len(cctv1['sources'])}")
        ok("CCTV1 有 logo", bool(cctv1.get("logo")), cctv1.get("logo", "")[:40])
    # 检查所有源 URL 合法
    bad_urls = [c["name"] for c in data["channels"] for s in c["sources"]
                if not str(s).startswith(("http://", "https://"))]
    ok("全部源 URL 合法", not bad_urls, f"bad={bad_urls[:3]}")
    return data


def test_checker():
    print("\n=== 2. 源可用性检测(缓存) ===")
    if not os.path.exists(os.path.join(DATA_DIR, "source_cache.json")):
        print("  (无缓存,先跑一次小范围检测)")
        Checker.build_cache()
    cache = json.load(open(os.path.join(DATA_DIR, "source_cache.json"), encoding="utf-8"))
    stats = cache["stats"]
    ok("检测有结果", stats["total"] > 0, f"{stats}")
    ok("可用率>50%", stats["ok_ratio"] > 0.5, f"ratio={stats['ok_ratio']}")
    ok("by_channel 有效", len(cache["by_channel"]) > 300)
    return cache


def test_storage():
    print("\n=== 3. 存储层 ===")
    Store.set_favorite("__test_ch__", True)
    ok("添加收藏", "__test_ch__" in Store.get_favorites())
    Store.add_history("__test_ch__")
    ok("历史记录", Store.get_history()[0] == "__test_ch__")
    Store.set_favorite("__test_ch__", False)
    ok("移除收藏", "__test_ch__" not in Store.get_favorites())
    # 清理测试痕迹
    prefs = Store.load_prefs()
    prefs["history"] = [h for h in prefs["history"] if h != "__test_ch__"]
    prefs["last_channel"] = None
    Store.save_prefs(prefs)


def test_fetcher_proxy():
    print("\n=== 4. 系统代理识别(fetcher) ===")
    proxy = Fetcher.get_system_proxy()
    ok("能识别系统代理", proxy is not None, f"proxy={proxy}")


if __name__ == "__main__":
    print("=" * 56)
    print("电视直播 - 单元/集成测试")
    print("=" * 56)
    test_parser()
    test_checker()
    test_storage()
    test_fetcher_proxy()
    print("\n" + "=" * 56)
    print(f"结果: PASS {PASS} / FAIL {FAIL}")
    sys.exit(0 if FAIL == 0 else 1)