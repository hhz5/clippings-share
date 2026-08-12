#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地后台服务（仅供本机运行，不部署到 GitHub Pages）。

提供：
  - 静态站点托管（与 GitHub Pages 一致的文件结构）
  - 后台管理 API：文章增删改、标签合并/重命名、作者重命名、重新生成

运行： python3 serve.py [--port 8000]
访问： http://127.0.0.1:8000/
后台管理入口在页面右上角 ⚙；公开 Pages 站点上该入口为只读。
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import generate as gen

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.environ.get("CLIPPINGS_SOURCE", gen.DEFAULT_SOURCE)
OUT = HERE


# ---------------- 源文件读写 ----------------
def id_map_path():
    return os.path.join(OUT, "assets", ".id_map.json")


def load_id_map():
    p = id_map_path()
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:
            return {}
    return {}


def src_of(id_):
    m = load_id_map()
    rel = m.get(id_)
    if not rel:
        return None
    return os.path.join(SOURCE, rel)


def serialize_frontmatter(meta, body):
    lines = ["---"]
    for k, v in meta.items():
        if k == "tags":
            lines.append("tags:")
            for t in (v or []):
                lines.append('  - "%s"' % t)
        else:
            if isinstance(v, (list, tuple)):
                v = ", ".join(str(x) for x in v)
            lines.append("%s: %s" % (k, json.dumps(v, ensure_ascii=False)))
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def write_article(id_, title, tags, body):
    path = src_of(id_)
    if not path or not os.path.exists(path):
        return False
    text = open(path, encoding="utf-8").read()
    meta, old_body = gen.parse_frontmatter(text)
    meta["标题"] = title
    meta["tags"] = tags
    # 保留其余字段（链接/作者/创建时间/摘要）
    new_text = serialize_frontmatter(meta, body)
    open(path, "w", encoding="utf-8").write(new_text)
    return True


def read_article(id_):
    path = src_of(id_)
    if not path or not os.path.exists(path):
        return None
    text = open(path, encoding="utf-8").read()
    meta, body = gen.parse_frontmatter(text)
    rel = os.path.relpath(path, SOURCE)
    author = rel.split(os.sep)[0]
    return {
        "id": id_,
        "title": meta.get("标题", ""),
        "author": author,
        "tags": meta.get("tags") or [],
        "body": body,
        "date": (meta.get("创建时间") or "")[:10],
    }


def create_article(author, title, tags, body):
    folder = os.path.join(SOURCE, author)
    os.makedirs(folder, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:80] or "untitled"
    path = os.path.join(folder, safe + ".md")
    if os.path.exists(path):
        path = os.path.join(folder, safe + "_" + datetime.now().strftime("%H%M%S") + ".md")
    meta = {
        "标题": title,
        "链接": "",
        "作者": "",
        "创建时间": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "摘要": "",
        "tags": tags,
    }
    open(path, "w", encoding="utf-8").write(serialize_frontmatter(meta, body))
    return True


def delete_article(id_):
    path = src_of(id_)
    if path and os.path.exists(path):
        os.remove(path)
        return True
    return False


def move_author(frm, to):
    src = os.path.join(SOURCE, frm)
    dst = os.path.join(SOURCE, to)
    if not os.path.isdir(src):
        return False
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        s = os.path.join(src, f)
        if os.path.isfile(s) and f.endswith(".md"):
            shutil.move(s, os.path.join(dst, f))
    try:
        os.rmdir(src)
    except OSError:
        pass
    return True


def update_alias(frm, to):
    p = os.path.join(OUT, "tag-aliases.json")
    data = {}
    if os.path.exists(p):
        data = json.load(open(p, encoding="utf-8"))
    aliases = data.get("aliases", {}) or {}
    aliases[frm] = to
    data["aliases"] = aliases
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return True


# ---------------- HTTP 处理 ----------------
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=OUT, **kw)

    def _send(self, code, obj=None, text=None, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if obj is not None:
            self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        elif text is not None:
            self.wfile.write(text.encode("utf-8"))

    def do_HEAD(self):
        if self.path.startswith("/__admin_status__"):
            self._send(200, {"ok": True})
            return
        super().do_HEAD()

    def do_GET(self):
        if self.path.startswith("/__admin_status__"):
            self._send(200, {"ok": True})
            return
        if self.path.startswith("/api/"):
            return self.handle_api("GET")
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self.handle_api("POST")
        self._send(405, {"error": "method not allowed"})
        return

    def do_PUT(self):
        if self.path.startswith("/api/"):
            return self.handle_api("PUT")
        self._send(405, {"error": "method not allowed"})
        return

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            return self.handle_api("DELETE")
        self._send(405, {"error": "method not allowed"})
        return

    def handle_api(self, method):
        parsed = urlparse(self.path)
        route = parsed.path
        qs = parse_qs(parsed.query)

        # GET 只读查询
        if route == "/api/articles" and method == "GET":
            q = (qs.get("q", [""])[0] or "").lower()
            data = gen_data()
            res = [{"id": a["id"], "title": a["title"], "author": a["author"], "tags": a["tags"], "date": a["date"]}
                   for a in data["articles"] if not q or q in a["title"].lower()]
            return self._send(200, res)
        if route == "/api/tags" and method == "GET":
            data = gen_data()
            return self._send(200, {"tags": data["tags"]})
        if route == "/api/authors" and method == "GET":
            data = gen_data()
            return self._send(200, data["authors"])
        m = re.match(r"^/api/article/([\w]+)$", route)
        if m and method == "GET":
            art = read_article(m.group(1))
            if not art:
                return self._send(404, {"error": "not found"})
            return self._send(200, art)

        # 写操作（仅本机）
        body = ""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(body) if body else {}

        if m and method == "PUT":
            ok = write_article(m.group(1), payload.get("title", ""), payload.get("tags", []), payload.get("body", ""))
            if not ok:
                return self._send(404, {"error": "not found"})
            gen.build(SOURCE, OUT)
            return self._send(200, {"ok": True})
        if m and method == "DELETE":
            delete_article(m.group(1))
            gen.build(SOURCE, OUT)
            return self._send(200, {"ok": True})
        if route == "/api/article/new" and method == "POST":
            create_article(payload.get("author", ""), payload.get("title", ""), payload.get("tags", []), payload.get("body", ""))
            gen.build(SOURCE, OUT)
            return self._send(200, {"ok": True})
        if route == "/api/tag" and method == "POST":
            update_alias(payload.get("from", ""), payload.get("to", ""))
            gen.build(SOURCE, OUT)
            return self._send(200, {"ok": True})
        if route == "/api/author" and method == "POST":
            move_author(payload.get("from", ""), payload.get("to", ""))
            gen.build(SOURCE, OUT)
            return self._send(200, {"ok": True})
        if route == "/api/regenerate" and method == "POST":
            gen.build(SOURCE, OUT)
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "unknown route"})

    def log_message(self, fmt, *args):
        pass  # 静默


_DATA_CACHE = {}
def gen_data():
    p = os.path.join(OUT, "assets", "data.js")
    txt = open(p, encoding="utf-8").read()
    m = re.search(r"window\.__SITE_DATA__\s*=\s*(\{[\s\S]*\})\s*;", txt)
    return json.loads(m.group(1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if not os.path.isdir(SOURCE):
        print("错误：源目录不存在：%s" % SOURCE)
        raise SystemExit(1)
    print("源目录：%s" % SOURCE)
    print("站点目录：%s" % OUT)
    print("后台： http://127.0.0.1:%d/  （页面右上角 ⚙ 进入管理）" % args.port)
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
