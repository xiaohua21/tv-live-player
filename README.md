# 电视直播 / TV Live

一个基于 **PyWebView（Edge WebView2）+ hls.js** 的桌面电视直播聚合播放器。

## 简介

- 聚合多个公开直播源，按央视频道 / 卫视 / 电影 / 体育等分类浏览；
- 内置本地代理转发跨域直播流，配合 hls.js 在 WebView 内直接播放；
- 可用性检测（延迟 / 成功率），自动挑选可用源；
- 收藏与播放历史（本地持久化）。

## 环境要求

- Windows（依赖 Edge WebView2 运行时，Win10/11 一般已内置）
- Python 3.10+

## 安装与运行

```bash
pip install -r requirements.txt
python app/main.py
```

## 更新直播源

应用内点击「更新源」会从 GitHub `vbskycn/iptv` 拉取最新的 `iptv4/iptv6` 源文件，
随后由 `parser` 重新解析生成 `data/channels.json`。

## 目录结构

```
电视直播/
├── app/                 # Python 后端（PyWebView）
│   ├── main.py          # 入口，暴露 API 给前端
│   ├── parser.py        # 解析 iptv 源文件 -> channels.json
│   ├── fetcher.py       # 从 GitHub 拉取最新源
│   ├── checker.py       # 源可用性检测，生成缓存
│   ├── proxy.py         # 本地代理，转发直播流
│   └── storage.py       # 收藏 / 历史本地持久化
├── ui/                  # 前端（HTML/CSS/JS + hls.js）
└── data/                # 频道库与源文件（source_cache / prefs 为本地运行时数据，不入库）
```

## 说明

频道数据来源于公开网络，仅供个人学习与技术测试使用。

作者：消化
