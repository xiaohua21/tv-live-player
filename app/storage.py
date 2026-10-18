# -*- coding: utf-8 -*-
"""
存储层：收藏、播放历史的本地持久化（JSON 文件）。
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFS_PATH = os.path.join(BASE_DIR, "data", "prefs.json")

DEFAULTS = {
    "favorites": [],
    "history": [],
    "last_channel": None,
}


def load_prefs():
    try:
        with open(PREFS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception:
        return dict(DEFAULTS)


def save_prefs(prefs):
    with open(PREFS_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=1)


def get_favorites():
    return load_prefs().get("favorites", [])


def set_favorite(name, fav):
    prefs = load_prefs()
    favs = prefs.setdefault("favorites", [])
    if fav and name not in favs:
        favs.append(name)
    elif not fav and name in favs:
        favs.remove(name)
    save_prefs(prefs)
    return prefs


def add_history(name):
    prefs = load_prefs()
    history = prefs.setdefault("history", [])
    if name in history:
        history.remove(name)
    history.insert(0, name)
    prefs["history"] = history[:200]
    prefs["last_channel"] = name
    save_prefs(prefs)
    return prefs


def get_history():
    return load_prefs().get("history", [])