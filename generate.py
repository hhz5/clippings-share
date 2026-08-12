#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
剪藏分享网站生成器（零第三方依赖，仅用 Python 3 标准库）。

功能：
  - 扫描剪藏源目录的 .md 文件，按「子文件夹=作者、根目录=其他」归集
  - 解析 frontmatter（标题/链接/作者/创建时间/摘要/tags）
  - 按 tag-aliases.json 归一化标签（剔除 clippings、合并格式变体/同义）
  - 无 tags 的文章归入「未分类」
  - 将正文渲染为 HTML，生成静态站点（index.html + articles/*.html + assets/data.js）
  - 输出不含任何本地绝对路径 / 用户名等隐私信息

用法：
  python3 generate.py [--source /path/to/剪藏文件] [--out /path/to/剪藏分享]

SOURCE 默认取环境变量 CLIPPINGS_SOURCE，否则回退到脚本内置默认路径。
OUT 默认取本脚本所在目录（即站点仓库根）。
重新运行即可全量重建，便于接每周自动化增量更新。
"""

import argparse
import json
import os
import re
import shutil
import html
import urllib.parse as urllib_parse
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
# 源目录不写死在脚本里（避免把本地路径带进公开仓库）。
# 运行方式：python3 generate.py --source /path/to/剪藏文件
#          或：export CLIPPINGS_SOURCE=/path/to/剪藏文件 && python3 generate.py
DEFAULT_SOURCE = os.environ.get("CLIPPINGS_SOURCE", "")
INTERNAL_DIRS = {".workbuddy", ".git"}  # 排除的内部目录
UNCATEGORIZED = "未分类"

# ---------------------------------------------------------------------------
# frontmatter 解析
# ---------------------------------------------------------------------------
def parse_frontmatter(text):
    """返回 (meta:dict, body:str)。无法解析时 meta={}, body=全文。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    fm_raw, body = m.group(1), m.group(2)
    meta = {}
    lines = fm_raw.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        mm = re.match(r"^([A-Za-z一-龥_]+):\s*(.*)$", line)
        if not mm:
            i += 1
            continue
        key, val = mm.group(1), mm.group(2).strip()
        # 列表值（tags 等）：本行以冒号结束，后续缩进行 - "x"
        if val == "" or val == "[]":
            if i + 1 < n and re.match(r"^\s*-\s+", lines[i + 1]):
                items = []
                j = i + 1
                while j < n and re.match(r"^\s*-\s+", lines[j]):
                    item = re.sub(r"^\s*-\s+", "", lines[j]).strip()
                    item = item.strip('"').strip("'").strip()
                    if item:
                        items.append(item)
                    j += 1
                meta[key] = items
                i = j
                continue
            else:
                meta[key] = [] if val == "[]" else ""
                i += 1
                continue
        # 行内列表：tags: ["a", "b"]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1]
            items = [x.strip().strip('"').strip("'") for x in re.findall(r'"([^"]*)"|\'([^\']*)\'', inner)]
            meta[key] = [x for x in items if x]
            i += 1
            continue
        # 普通标量（去外层引号）
        meta[key] = val.strip('"').strip("'")
        i += 1
    return meta, body


# ---------------------------------------------------------------------------
# 标签归一化
# ---------------------------------------------------------------------------
def load_alias_map(path):
    remove = []
    aliases = {}
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
            remove = data.get("remove", []) or []
            aliases = data.get("aliases", {}) or {}
        except Exception:
            pass
    return set(remove), aliases


def normalize_tags(raw_tags, remove_set, aliases):
    out = []
    seen = set()
    for t in raw_tags:
        t = (t or "").strip()
        if not t:
            continue
        if t in remove_set:
            continue
        canon = aliases.get(t, t).strip()
        if not canon:
            continue
        if canon not in seen:
            seen.add(canon)
            out.append(canon)
    if not out:
        out = [UNCATEGORIZED]
    return out


# ---------------------------------------------------------------------------
# Markdown -> HTML（聚焦文章常见语法；允许内嵌 HTML 透传）
# ---------------------------------------------------------------------------
def _inline(text):
    # 行内代码优先占位，避免其中的 * _ [ 被再次解析
    codes = []

    def stash_code(m):
        codes.append(m.group(1))
        return "\x00CODE%d\x00" % (len(codes) - 1)

    text = re.sub(r"`([^`]+)`", stash_code, text)
    # 图片 ![alt](url)
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                  lambda m: '<img src="%s" alt="%s" loading="lazy">' % (_esc_attr(m.group(2)), _esc_attr(m.group(1))), text)
    # 链接 [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  lambda m: '<a href="%s" target="_blank" rel="noopener">%s</a>' % (_esc_attr(m.group(2)), m.group(1)), text)
    # 粗体 **x** / __x__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # 斜体 *x* / _x_
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!_)_(?!_)(.+?)_(?!_)", r"<em>\1</em>", text)
    # 删除线 ~~x~~
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    # 还原行内代码
    def restore_code(m):
        idx = int(m.group(1))
        return "<code>%s</code>" % html.escape(codes[idx])
    text = re.sub(r"\x00CODE(\d+)\x00", restore_code, text)
    return text


def _esc_attr(s):
    return html.escape(s, quote=True)


def markdown_to_html(md):
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    lines = md.split("\n")
    out = []
    i = 0
    n = len(lines)

    def is_blank(l):
        return not l.strip()

    while i < n:
        line = lines[i]

        # 代码围栏
        fence = re.match(r"^\s*```(.*)$", line)
        if fence:
            lang = fence.group(1).strip()
            buf = []
            i += 1
            while i < n and not re.match(r"^\s*```\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束围栏
            cls = (' class="language-%s"' % lang) if lang else ""
            out.append("<pre><code%s>%s</code></pre>" % (cls, html.escape("\n".join(buf))))
            continue

        # 标题
        h = re.match(r"^(#{1,6})\s+(.*)$", line)
        if h:
            level = len(h.group(1))
            out.append("<h%d>%s</h%d>" % (level, _inline(h.group(2).strip()), level))
            i += 1
            continue

        # 分隔线
        if re.match(r"^(\s*[-*_]){3,}\s*$", line) and set(line.strip()) <= set("-*_ "):
            out.append("<hr>")
            i += 1
            continue

        # 引用块
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append("<blockquote>%s</blockquote>" % markdown_to_html("\n".join(buf)))
            continue

        # 表格（当前行含 | 且下一行是分隔行）
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]) and "-" in lines[i + 1]:
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            thead = "<tr>" + "".join("<th>%s</th>" % _inline(c) for c in header) + "</tr>"
            tbody = "".join("<tr>" + "".join("<td>%s</td>" % _inline(c) for c in r) + "</tr>" for r in rows)
            out.append("<table><thead>%s</thead><tbody>%s</tbody></table>" % (thead, tbody))
            continue

        # 列表（有序/无序，支持缩进嵌套）
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            buf = []
            while i < n and (re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]) or (buf and lines[i].startswith(" ") and lines[i].strip())):
                if not lines[i].strip():
                    break
                buf.append(lines[i])
                i += 1
            out.append(_render_list(buf))
            continue

        # 空行
        if is_blank(line):
            i += 1
            continue

        # 段落（聚合连续非空、非块级行）
        buf = [line]
        i += 1
        while i < n and not is_blank(lines[i]) and not re.match(
                r"^\s*(#{1,6}\s|```|>\s*|\s*([-*+]|\d+\.)\s+)", lines[i]):
            buf.append(lines[i])
            i += 1
        para = " ".join(x.strip() for x in buf)
        out.append("<p>%s</p>" % _inline(para))
    return "\n".join(out)


def _render_list(lines):
    """将一组列表行（可能嵌套）渲染为 <ul>/<ol>。"""
    items = []  # (indent, ordered, content)
    for ln in lines:
        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", ln)
        if not m:
            continue
        indent = len(m.group(1).replace("\t", "  "))
        ordered = bool(re.match(r"\d+\.", m.group(2)))
        items.append((indent, ordered, m.group(3).strip()))
    if not items:
        return ""
    out = []
    stack = []  # 每项为 (indent, ordered)

    def open_tag(ordered):
        return "<ol>" if ordered else "<ul>"

    def close_tag(ordered):
        return "</ol>" if ordered else "</ul>"

    idx = 0
    while idx < len(items):
        indent, ordered, content = items[idx]
        if not stack:
            stack.append((indent, ordered))
            out.append(open_tag(ordered))
        else:
            top_indent, top_ordered = stack[-1]
            if indent > top_indent:
                stack.append((indent, ordered))
                out.append(open_tag(ordered))
            elif indent < top_indent:
                while stack and stack[-1][0] > indent:
                    ci, co = stack.pop()
                    out.append(close_tag(co))
                if stack:
                    # 同一父级下继续
                    pass
                else:
                    stack.append((indent, ordered))
                    out.append(open_tag(ordered))
            else:
                # 同级：若有序/无序变化，先关后开
                if ordered != stack[-1][1]:
                    ci, co = stack.pop()
                    out.append(close_tag(co))
                    stack.append((indent, ordered))
                    out.append(open_tag(ordered))
        out.append("<li>%s</li>" % _inline(content))
        idx += 1
    while stack:
        ci, co = stack.pop()
        out.append(close_tag(co))
    return "".join(out)


# ---------------------------------------------------------------------------
# 文章 HTML 模板
# ---------------------------------------------------------------------------
ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 剪藏分享</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<header class="site-header">
  <div class="header-inner">
    <a class="brand" href="../index.html">剪藏分享</a>
    <nav class="header-actions">
      <button id="theme-toggle" class="icon-btn" title="切换主题" aria-label="切换主题">🌓</button>
      <button id="admin-open" class="icon-btn" title="后台管理" aria-label="后台管理">⚙</button>
    </nav>
  </div>
</header>
<main class="article-main">
  <article class="article">
    <div class="article-meta">
      <a class="meta-author" href="../index.html?author={author_enc}">{author}</a>
      <span class="meta-date">{date}</span>
    </div>
    <h1 class="article-title">{title}</h1>
    <div class="article-tags">
      {tags_html}
    </div>
    {source_link}
    <div class="article-body">
{body}
    </div>
  </article>
  <footer class="article-footer">
    <a href="../index.html">← 返回首页</a>
  </footer>
</main>
<script src="../assets/app.js"></script>
</body>
</html>
"""


def build_article_html(article, body_html):
    tags_html = "".join(
        '<a class="tag-chip" href="../index.html?tag=%s">%s</a>' % (urllib_parse.quote(t), _esc_text(t))
        for t in article["tags"]
    )
    source_link = ""
    if article.get("url"):
        source_link = '<p class="article-source"><a href="%s" target="_blank" rel="noopener">查看原文 ↗</a></p>' % _esc_attr(article["url"])
    return ARTICLE_TEMPLATE.format(
        title=_esc_text(article["title"]),
        author=_esc_text(article["author"]),
        author_enc=urllib_parse.quote(article["author"]),
        date=_esc_text(article.get("date", "")),
        tags_html=tags_html,
        source_link=source_link,
        body=body_html,
    )


def _esc_text(s):
    return html.escape(s or "")


# ---------------------------------------------------------------------------
# 主构建流程
# ---------------------------------------------------------------------------
def build(source_dir, out_dir):
    alias_path = os.path.join(out_dir, "tag-aliases.json")
    remove_set, aliases = load_alias_map(alias_path)

    articles = []
    author_counts = {}
    tag_counts = {}
    aid = 0

    # 遍历：根目录文件 -> 作者「其他」；一级子目录 -> 作者
    root_md = [f for f in os.listdir(source_dir) if f.endswith(".md") and os.path.isfile(os.path.join(source_dir, f))]
    sub_dirs = [d for d in os.listdir(source_dir)
                if os.path.isdir(os.path.join(source_dir, d)) and d not in INTERNAL_DIRS]

    def scan_file(path, author):
        nonlocal aid
        try:
            text = open(path, encoding="utf-8").read()
        except Exception:
            return
        meta, body = parse_frontmatter(text)
        title = meta.get("标题") or meta.get("title") or os.path.splitext(os.path.basename(path))[0]
        url = meta.get("链接") or meta.get("url") or ""
        date = meta.get("创建时间") or meta.get("date") or ""
        if date:
            date = date[:10]
        raw_tags = meta.get("tags") or []
        if isinstance(raw_tags, str):
            raw_tags = [raw_tags]
        tags = normalize_tags(raw_tags, remove_set, aliases)
        # 摘要
        excerpt = meta.get("摘要") or meta.get("excerpt") or ""
        if not excerpt:
            for para in re.split(r"\n\s*\n", body):
                p = para.strip()
                if p and not p.startswith("!") and not p.startswith(">") and not p.startswith("#"):
                    excerpt = re.sub(r"\s+", " ", p)[:160]
                    break
        plain = re.sub(r"<[^>]+>", "", body)
        plain = re.sub(r"[#*_>`~\-]+", " ", plain)
        plain = re.sub(r"\s+", " ", plain).strip()

        aid += 1
        art_id = "a%04d" % aid
        article = {
            "id": art_id,
            "title": title,
            "author": author,
            "tags": tags,
            "date": date,
            "url": url,
            "excerpt": excerpt,
            "text": plain[:4000],
            "_src": path,  # 仅本地使用，不写入 data.js
        }
        articles.append(article)
        author_counts[author] = author_counts.get(author, 0) + 1
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1

    # 根目录
    for f in sorted(root_md):
        scan_file(os.path.join(source_dir, f), UNCATEGORIZED)
    # 子目录
    for d in sorted(sub_dirs):
        dp = os.path.join(source_dir, d)
        for f in sorted(os.listdir(dp)):
            if f.endswith(".md") and os.path.isfile(os.path.join(dp, f)):
                scan_file(os.path.join(dp, f), d)

    articles.sort(key=lambda a: a["date"] or "", reverse=True)

    # 输出文章页（重建前清空旧 .html，避免孤儿文件）
    articles_dir = os.path.join(out_dir, "articles")
    if os.path.isdir(articles_dir):
        for fn in os.listdir(articles_dir):
            if fn.endswith(".html"):
                try: os.remove(os.path.join(articles_dir, fn))
                except OSError: pass
    os.makedirs(articles_dir, exist_ok=True)
    id_map = {}
    for art in articles:
        text = open(art["_src"], encoding="utf-8").read()
        _, body = parse_frontmatter(text)
        body_html = markdown_to_html(body)
        html_out = build_article_html(art, body_html)
        with open(os.path.join(articles_dir, art["id"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(html_out)
        id_map[art["id"]] = os.path.relpath(art["_src"], source_dir)

    # 输出 data.js（不含 _src 等本地字段）
    public_articles = [
        {
            "id": a["id"],
            "title": a["title"],
            "author": a["author"],
            "tags": a["tags"],
            "date": a["date"],
            "url": a["url"],
            "excerpt": a["excerpt"],
            "text": a["text"],
        }
        for a in articles
    ]
    authors_list = sorted(
        ({"name": k, "count": v} for k, v in author_counts.items()),
        key=lambda x: (-x["count"], x["name"]),
    )
    tags_list = sorted(
        ({"name": k, "count": v} for k, v in tag_counts.items()),
        key=lambda x: (-x["count"], x["name"]),
    )
    data = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total": len(articles),
        "authors": authors_list,
        "tags": tags_list,
        "articles": public_articles,
    }
    data_js = "window.__SITE_DATA__ = " + json.dumps(data, ensure_ascii=False) + ";\n"
    with open(os.path.join(out_dir, "assets", "data.js"), "w", encoding="utf-8") as fh:
        fh.write(data_js)

    # 私有映射：id -> 相对源路径（仅供本地后台使用，不含本地绝对路径）
    with open(os.path.join(out_dir, "assets", ".id_map.json"), "w", encoding="utf-8") as fh:
        json.dump(id_map, fh, ensure_ascii=False)

    # 复制静态资源（index.html / style.css / app.js / .nojekyll）
    here = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(out_dir, "assets")
    static_map = {
        "index.html": out_dir,
        "style.css": assets_dir,
        "app.js": assets_dir,
        "nojekyll": out_dir,
    }
    for fname, dst_dir in static_map.items():
        src = os.path.join(here, fname)
        dst_name = ".nojekyll" if fname == "nojekyll" else fname
        dst = os.path.join(dst_dir, dst_name)
        if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(dst):
            shutil.copyfile(src, dst)

    print("生成完成：%d 篇文章，%d 个作者，%d 个标签" % (len(articles), len(authors_list), len(tags_list)))
    print("输出目录：%s" % out_dir)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="剪藏分享网站生成器")
    parser.add_argument("--source", default=os.environ.get("CLIPPINGS_SOURCE", DEFAULT_SOURCE),
                        help="剪藏源目录（含 .md）")
    parser.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)),
                        help="站点输出目录（默认脚本所在目录）")
    args = parser.parse_args()
    if not args.source:
        print("未指定源目录。请用 --source /path/to/剪藏文件，或设置环境变量 CLIPPINGS_SOURCE。")
        raise SystemExit(1)
    if not os.path.isdir(args.source):
        print("错误：源目录不存在：%s" % args.source)
        raise SystemExit(1)
    build(args.source, args.out)
