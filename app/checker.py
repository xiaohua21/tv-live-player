# -*- coding: utf-8 -*-
"""
源可用性检测层：并发探测全部直播源，按频道保留探测延迟与可用状态。

注意：直接访问海外/被墙源会超时挂起，这里先用系统代理策略探测——探测时
读取 Windows 系统代理(注册表)并跟随，保证最多的源能被探通。

输出: data/source_cache.json
{
  "checked_at": "2026-10-17 21:10:00",
  "stats": {"total": 1213, "ok": 866, "fail": 347, "ok_ratio": 0.71},
  "by_channel": {
     "CCTV1": {"latency_ms": 168, "source_index": 1, "ok": true},
     ...
  },
  "source_status": { "url": {"ok": true, "latency_ms": 190}, ... }
}
"""

import json
import os
import re
import sys
import datetime
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_PATH = os.path.join(DATA_DIR, "source_cache.json")

MAX_WORKERS = 40
CONNECT_TIMEOUT = 5     # 连接超时秒数
HEAD_TIMEOUT = 4.0      # 读取响应头超时

sys.path.insert(0, os.path.join(BASE_DIR, "app"))
from parser import load_sources


def get_system_proxy():
    """读取 Windows 系统代理设置(注册表), 返回 http 代理地址或 None"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Internet Settings")
        enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
        server, _ = winreg.QueryValueEx(key, "ProxyServer")
        winreg.CloseKey(key)
        if enable and server:
            server = re.sub(r"^https?://", "", server).split(";")[0].strip()
            return f"http://{server}"
    except Exception:
        pass
    return None


def probe(url, proxy=None):
    """探测单个源: 请求首个分片(Range 0-500)，返回 (ok, latency_ms)"""
    req = urllib.request.Request(url, method="GET", headers={
        "Range": "bytes=0-500",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TVLive/1.0",
        "Referer": "https://www.baidu.com/",
    })
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else \
        urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(handler)
    start = datetime.datetime.now()
    try:
        with opener.open(req, timeout=HEAD_TIMEOUT) as resp:
            code = resp.status
            # 200/206 有效; 301/302/303/307/308 视为可跳转但需再跟随; 404/403/5xx 判失败
            ok = code in (200, 206) or code in (301, 302, 303, 307, 308)
            if code in (301, 302, 303, 307, 308):
                # 允许自动跟随的重定向交给 urllib, 这里仅记录首次状态
                ok = True
            latency = int((datetime.datetime.now() - start).total_seconds() * 1000)
            return ok, latency
    except Exception:
        return False, -1


def build_cache(use_proxy=True):
    print("[checker] 加载频道数据 ...")
    data = load_sources()
    if os.path.exists(CACHE_PATH):
        os.remove(CACHE_PATH)

    proxy = get_system_proxy() if use_proxy else None
    if proxy:
        print(f"[checker] 跟随系统代理: {proxy}")
    else:
        print("[checker] 无系统代理, 直连探测")

    # 收集全部 (index, url) 去重
    all_sources = []
    seen = set()
    for ch in data["channels"]:
        for idx, url in enumerate(ch["sources"]):
            if url not in seen:
                seen.add(url)
                all_sources.append((ch["name"], idx, url))

    total = len(all_sources)
    print(f"[checker] 待探测源: {total} 条, 并发 {MAX_WORKERS}")

    source_status = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(probe, url, proxy): url for _, _, url in all_sources}
        done = 0
        ok_count = 0
        for fut in as_completed(futures):
            url = futures[fut]
            ok, lat = fut.result()
            source_status[url] = {"ok": ok, "latency_ms": lat}
            done += 1
            if ok:
                ok_count += 1
            if done % 200 == 0 or done == total:
                print(f"  进度 {done}/{total}  可用 {ok_count}")

    # 每频道选择最快可用源
    by_channel = {}
    for ch in data["channels"]:
        name = ch["name"]
        best = None
        best_lat = None
        for idx, url in enumerate(ch["sources"]):
            st = source_status.get(url, {"ok": False, "latency_ms": -1})
            if st["ok"]:
                if best is None or st["latency_ms"] < best_lat:
                    best = idx
                    best_lat = st["latency_ms"]
        by_channel[name] = {
            "ok": best is not None,
            "source_index": best if best is not None else 0,
            "latency_ms": best_lat if best_lat is not None else -1,
        }

    ratio = round(ok_count / total, 3) if total else 0
    cache = {
        "checked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stats": {"total": total, "ok": ok_count, "fail": total - ok_count, "ok_ratio": ratio},
        "by_channel": by_channel,
        "source_status": source_status,
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    print("=" * 52)
    print(f"探测完成: 源 {total} | 可用 {ok_count} | 失效 {total-ok_count} | 可用率 {ratio*100:.1f}%")
    print(f"输出文件: {CACHE_PATH}")
    return cache


if __name__ == "__main__":
    build_cache()