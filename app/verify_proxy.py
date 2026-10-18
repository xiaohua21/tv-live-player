# -*- coding: utf-8 -*-
"""验证本地代理: 用真实 CCTV-1 源走 /proxy, 检查 m3u8 重写 + 分片可拉 + CORS 头"""
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import proxy

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(BASE, "data", "channels.json"), encoding="utf-8") as f:
    data = json.load(f)

target = None
for ch in data["channels"]:
    name = ch["name"].upper().replace(" ", "")
    if name in ("CCTV-1", "CCTV1", "CCTV-1综合", "CCTV1综合") or name.startswith("CCTV-1"):
        target = ch
        break
if not target:
    print("!! 未找到 CCTV1 频道"); sys.exit(1)
print("频道:", target["name"], "| 源数:", len(target["sources"]))

port = proxy.start_proxy()
pre = f"http://127.0.0.1:{port}/proxy?url="
print("代理端口:", port)

for src in target["sources"]:
    u = pre + urllib.parse.quote(src, safe="")
    try:
        r = urllib.request.urlopen(u, timeout=25)
        body = r.read(6000).decode("utf-8", "ignore")
        cors = r.headers.get("Access-Control-Allow-Origin")
        print("\n== 源:", src[:70])
        print("   状态:", r.status, "| CORS:", cors, "| 内容长度:", len(body))
        if "#EXTM3U" not in body:
            print("   非 m3u8(可能是 ts 直链), 前 16 字节:", body[:16].encode(errors="replace")[:16])
            break
        proxied = [l for l in body.splitlines() if "/proxy?url=" in l]
        direct = [l for l in body.splitlines() if l.startswith("http") and "/proxy?url=" not in l]
        print("   已重写为代理的地址行数:", len(proxied), "| 残留真实地址行数:", len(direct))
        for line in body.splitlines()[:10]:
            print("     ", line[:100])
        # 拉第一个分片
        seg = None
        for line in body.splitlines():
            if "/proxy?url=" in line and not line.startswith("#"):
                seg = line.strip()
                break
        if seg:
            r2 = urllib.request.urlopen(seg, timeout=25)
            b2 = r2.read(400)
            print("   分片请求:", seg[:90])
            print("   分片状态:", r2.status, "| CORS:", r2.headers.get("Access-Control-Allow-Origin"),
                  "| 大小:", len(b2), "| 开头字节:", b2[:12].hex())
        break
    except Exception as e:
        print("\n!! 源失败:", src[:70], "->", str(e)[:120])