# 剪藏分享 · Clippings Share

按 **作者 × 标签** 双维度组织的 AI 剪藏知识库。静态站点，零第三方依赖，可部署到 GitHub Pages。

- 作者维度：按源目录的子文件夹名归集；根目录文件归入「其他」
- 标签维度：取自文章 frontmatter 的 `tags` 字段，经 `tag-aliases.json` 归一化（剔除元标签、合并格式变体/同义）
- 无 `tags` 的文章归入「未分类」
- 站内渲染完整 Markdown 正文，支持全文搜索、浅/深主题切换
- 作者与标签交叉筛选联动

## 目录结构

```
generate.py          生成器（零依赖，标准库）
serve.py             本地后台服务（文章/标签/作者管理，编辑后自动重新生成）
tag-aliases.json     标签合并映射表（可维护）
index.html           首页
assets/              style.css / app.js / data.js
articles/            每篇文章一个静态 HTML 页
.github/workflows/   GitHub Pages 部署
```

## 本地使用

### 生成站点

```bash
export CLIPPINGS_SOURCE=/path/to/剪藏文件
python3 generate.py            # 默认输出到本脚本所在目录
# 或指定输出：python3 generate.py --source /path/to/剪藏文件 --out /path/to/site
```

### 本地预览 + 后台管理

```bash
export CLIPPINGS_SOURCE=/path/to/剪藏文件
python3 serve.py --port 8000
# 浏览器打开 http://127.0.0.1:8000/
# 右上角 ⚙ 进入后台：文章增删改、标签合并/重命名、作者重命名
```

> 公开 Pages 站点上的 ⚙ 入口为**只读**；编辑功能仅在本地 `serve.py` 下可用。

## 维护标签

编辑 `tag-aliases.json`：

- `remove`：剔除的元标签（如 `clippings`）
- `aliases`：`"原始标签": "规范标签"` 合并映射（仅合并真正同义/格式变体，不合并不同概念）

改完运行 `python3 generate.py` 重新生成。

## 接入每周自动化增量更新

每周剪藏学习自动化任务产出新 `.md` 后，执行：

```bash
export CLIPPINGS_SOURCE=/path/to/剪藏文件
python3 generate.py && git add -A && git commit -m "update" && git push
```

即可把新增文章重新生成并发布。
