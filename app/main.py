# -*- coding: utf-8 -*-
"""
电视直播 - 主程序入口
基于 PyWebView(Edge WebView2) + hls.js 的桌面电视直播应用
启动: python app/main.py
"""

import json
import os
import sys
import threading
import webview

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")
UI_DIR = os.path.join(BASE_DIR, "ui")
DATA_DIR = os.path.join(BASE_DIR, "data")

sys.path.insert(0, APP_DIR)

import parser as Parser
import storage as Store
import fetcher as Fetcher
import checker as Checker
import proxy as Proxy

# 全局锁, 避免多个后端方法并发写同一 JSON
_locks = {}


def _lock(name):
    if name not in _locks:
        _locks[name] = threading.Lock()
    return _locks[name]


class Api:
    """暴露给前端 pywebview.api 的方法"""

    def get_proxy_base(self):
        """返回本地代理基址, 前端用它把直播源包成 /proxy?url= 再播放"""
        return Proxy.PROXY_BASE

    def get_channels(self):
        """返回 {categories, channels, meta}"""
        path = os.path.join(DATA_DIR, "channels.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            data = Parser.build()
            return data

    def get_cache(self):
        """返回源可用性缓存"""
        path = os.path.join(DATA_DIR, "source_cache.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def get_prefs(self):
        return Store.load_prefs()

    def set_favorite(self, name, fav):
        with _lock("prefs"):
            Store.set_favorite(name, bool(fav))
        return True

    def add_history(self, name):
        with _lock("prefs"):
            Store.add_history(name)
        return True

    def get_history(self):
        return Store.get_history()

    def check_sources(self):
        """重新检测全部源可用性(后台线程, 避免卡 UI)"""
        def run():
            try:
                Checker.build_cache()
            except Exception as e:
                print("[main] check_sources error:", e)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return True

    def update_sources(self):
        """从 GitHub 拉取最新源并重新解析"""
        def run():
            try:
                res = Fetcher.update_sources()
                print("[main] update_sources ok:", res["message"])
            except Exception as e:
                print("[main] update_sources error:", e)
        t = threading.Thread(target=run, daemon=True)
        t.start()
        return {"message": "后台更新中，完成后点[检查源]刷新可用性"}


def main():
    port = Proxy.start_proxy()
    print(f"[main] 本地代理已启动: http://127.0.0.1:{port}/proxy?url=")
    api = Api()
    window = webview.create_window(
        "电视直播 - TV Live",
        url=os.path.join(UI_DIR, "index.html"),
        js_api=api,
        width=1200,
        height=760,
        min_size=(960, 600),
        background_color="#0f1318",
    )

    def on_loaded():
        print("[main] 窗口加载完成")

    window.events.loaded += on_loaded
    webview.start(debug=False)


if __name__ == "__main__":
    main()