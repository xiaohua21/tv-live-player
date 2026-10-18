# -*- coding: utf-8 -*-
"""
本地流媒体代理：解决浏览器 CORS 限制导致 hls.js 无法拉取直播源的问题。

原理:
  WebView2(PyWebView) 里的 hls.js 是浏览器环境, 对跨域 http 直播源有 CORS 限制,
  源不返回 Access-Control-Allow-Origin 头 -> 全部 Failed to fetch -> 一直转圈。
  本代理监听 127.0.0.1:随机端口, 前端把源 URL 拼成 /proxy?url=... 请求,
  由 Python 侧(无跨域限制)去取流再原样转回, 响应带 CORS 头, 前端即可正常播放。

核心设计:
  代理把 m3u8 正文里的【所有内部 URL】(分片/key/子列表) 一律重写为
  /proxy?url=<真实地址> 的形式。这样 hls.js 拿到的播放列表里全部指向
  本地 127.0.0.1(同源, 无 CORS), 每一个分片请求又回到代理去真实服务器拉。
  浏览器侧永远只连 localhost, 彻底绕开跨域。

额外能力:
  - 透传 Range 请求(hls.js 拉 ts 分片用)
  - 统一带 User-Agent / Referer, 解决部分源需要 Referer 才给流的问题
"""

import http.server
import re
import socketserver
import threading
import urllib.parse
import urllib.request

CHUNK = 65536
TIMEOUT = 25

PROXY_BASE = ""  # 启动后形如 http://127.0.0.1:port/proxy?url=, 供前端/后端拼地址

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
REFERER = "https://www.baidu.com/"


def _abs(base_url, ref):
    """把 m3u8 内的相对 URL 解析为基于 base_url 的绝对 URL"""
    if ref.startswith(("http://", "https://")):
        return ref
    return urllib.parse.urljoin(base_url, ref)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    self_prefix = "http://127.0.0.1:0/proxy?url="  # 启动时由 start_proxy 覆写

    # ---------------- 内部工具 ----------------
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Range, Content-Type, Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")

    def _wrap(self, url):
        """把任意真实 URL 包装成本地代理地址"""
        if url.startswith(self.self_prefix):
            return url
        return self.self_prefix + urllib.parse.quote(url, safe="")

    def _rewrite_m3u8(self, text, real_url):
        """把 m3u8 里所有内部 URL 重写为本地代理地址, 让浏览器全程只连 localhost"""
        lines = text.splitlines()
        out = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i].rstrip("\r")
            # #EXTINF 的下一行是分片 URL
            if line.startswith("#EXTINF:"):
                out.append(line)
                if i + 1 < n and not lines[i + 1].lstrip().startswith("#"):
                    out.append(self._wrap(_abs(real_url, lines[i + 1].strip())))
                    i += 2
                    continue
            # #EXT-X-STREAM-INF 的下一行是子 m3u8 URL
            elif line.startswith("#EXT-X-STREAM-INF:"):
                out.append(line)
                if i + 1 < n and not lines[i + 1].lstrip().startswith("#"):
                    out.append(self._wrap(_abs(real_url, lines[i + 1].strip())))
                    i += 2
                    continue
            # #EXT-X-KEY / #EXT-X-MEDIA 里的 URI="..."(加密 key / 音轨)
            elif line.startswith(("#EXT-X-KEY", "#EXT-X-MEDIA")) and 'URI="' in line:
                line = re.sub(r'URI="([^"]*)"',
                              lambda m: 'URI="%s"' % self._wrap(_abs(real_url, m.group(1))),
                              line)
                out.append(line)
            else:
                out.append(line)
            i += 1
        return "\n".join(out)

    # ---------------- HTTP 方法 ----------------
    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors()
        self.end_headers()

    def do_HEAD(self):
        self._serve(stream_only=True)

    def do_GET(self):
        self._serve()

    def _serve(self, stream_only=False):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        target = qs.get("url", [""])[0]
        if not target or not target.startswith(("http://", "https://")):
            self.send_error(400, "bad url")
            return

        headers = {"User-Agent": UA, "Referer": REFERER}
        rng = self.headers.get("Range")
        if rng:
            headers["Range"] = rng

        req = urllib.request.Request(target, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        except Exception as e:
            try:
                self.send_error(502, str(e)[:120])
            except Exception:
                pass
            return

        code = resp.status
        ctype = resp.headers.get("Content-Type", "application/octet-stream")

        # 判断是否为 m3u8 文本
        is_m3u = ("mpegurl" in ctype) or ("application/vnd.apple" in ctype)
        if not is_m3u and not stream_only:
            head = resp.read(2048)
            is_m3u = b"#EXTM3U" in head
            if not is_m3u:
                # 非 m3u8: 前面已读 2048 字节, 需要拼回流
                rest = resp.read()
                self._stream(head + rest, code, ctype, resp)
                resp.close()
                return
            else:
                rest = resp.read()
                body = head + rest
        elif is_m3u and not stream_only:
            body = resp.read()
        else:
            # 流式转发(ts 分片等) —— HEAD 或直接流
            self._stream(None, code, ctype, resp)
            resp.close()
            return

        # m3u8: 重写内部 URL 后返回
        text = body.decode("utf-8", errors="ignore")
        text = self._rewrite_m3u8(text, resp.geturl() or target)
        encoded = text.encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self._send_cors()
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        resp.close()

    def _stream(self, first_bytes, code, ctype, resp):
        """流式转发响应(处理少量已读数据 + Range)"""
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self._send_cors()
            self.send_header("Cache-Control", "no-cache")
            clen = resp.headers.get("Content-Length")
            if first_bytes is not None:
                # 已读部分, 长度需重新表述
                if clen:
                    try:
                        rest_len = max(0, int(clen) - len(first_bytes))
                        self.send_header("Content-Length", str(rest_len + len(first_bytes)))
                    except ValueError:
                        self.close_connection = True
                        self.send_header("Connection", "close")
                else:
                    self.close_connection = True
                    self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(first_bytes)
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            else:
                if clen:
                    self.send_header("Content-Length", clen)
                else:
                    self.close_connection = True
                    self.send_header("Connection", "close")
                self.end_headers()
                while True:
                    chunk = resp.read(CHUNK)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def log_message(self, *args):
        pass


def start_proxy(port=0):
    """启动本地代理, 返回监听端口号"""
    global PROXY_BASE
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", port), _Handler)
    actual_port = httpd.server_address[1]
    PROXY_BASE = f"http://127.0.0.1:{actual_port}/proxy?url="
    _Handler.self_prefix = PROXY_BASE
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return actual_port


if __name__ == "__main__":
    p = start_proxy()
    print(f"代理已启动: http://127.0.0.1:{p}/proxy?url=<直播源地址>")
    import time
    time.sleep(3600)