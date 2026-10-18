# -*- coding: utf-8 -*-
"""
源更新层：从 GitHub vbskycn/iptv 拉取最新直播源文件(通过系统代理)。
"""

import datetime
import os
import re
import urllib.request

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

RAW_BASE = "https://raw.githubusercontent.com/vbskycn/iptv/master/tv/"
FILES = ["iptv4.txt", "iptv4.m3u", "iptv6.txt", "iptv6.m3u"]


def get_system_proxy():
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


def fetch_file(filename):
    url = RAW_BASE + filename
    proxy = get_system_proxy()
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers) if handlers else urllib.request.build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TVLive/1.0"})
    with opener.open(req, timeout=30) as resp:
        content = resp.read()
    if not content:
        raise RuntimeError(f"{filename} 下载为空")
    with open(os.path.join(DATA_DIR, filename), "wb") as f:
        f.write(content)
    return len(content)


def update_sources():
    """下载最新源文件并重新解析生成 channels.json；返回消息字符串"""
    messages = []
    for fn in FILES:
        try:
            size = fetch_file(fn)
            messages.append(f"{fn} {size // 1024}KB")
        except Exception as e:
            messages.append(f"{fn} 失败({e})")

    # 重新解析
    from parser import build
    build()

    return {
        "message": "更新完成: " + " | ".join(messages),
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


if __name__ == "__main__":
    print(update_sources()["message"])