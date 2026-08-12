/* 剪藏分享 · 前端逻辑（原生 JS，无依赖） */
(function () {
  "use strict";

  var DATA = window.__SITE_DATA__ || { articles: [], authors: [], tags: [], total: 0 };

  /* ---------- 主题 ---------- */
  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("theme", t); } catch (e) {}
  }
  var saved = "light";
  try { saved = localStorage.getItem("theme") || "light"; } catch (e) {}
  applyTheme(saved);

  document.addEventListener("click", function (e) {
    if (e.target && e.target.closest("#theme-toggle")) {
      var cur = document.documentElement.getAttribute("data-theme");
      applyTheme(cur === "dark" ? "light" : "dark");
    }
  });

  /* ---------- 状态 ---------- */
  var state = { authors: new Set(), tags: new Set(), q: "", sort: "date" };
  var TAG_LIMIT_DEFAULT = 40;
  var tagExpanded = false;

  function ARTICLE_URL(id) { return "articles/" + id + ".html"; }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ---------- 过滤逻辑 ---------- */
  function filtered() {
    var q = state.q.trim().toLowerCase();
    return DATA.articles.filter(function (a) {
      if (state.authors.size && !state.authors.has(a.author)) return false;
      if (state.tags.size) {
        var ok = true;
        state.tags.forEach(function (t) { if (a.tags.indexOf(t) === -1) ok = false; });
        if (!ok) return false;
      }
      if (q) {
        var hay = (a.title + " " + (a.text || "") + " " + a.author + " " + a.tags.join(" ")).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  function countsUnder(other) {
    var map = {};
    DATA.articles.forEach(function (a) {
      if (state.tags.size && other === "author") {
        var ok = true; state.tags.forEach(function (t) { if (a.tags.indexOf(t) === -1) ok = false; });
        if (!ok) return;
      }
      if (state.authors.size && other === "tag") { if (!state.authors.has(a.author)) return; }
      if (other === "author") map[a.author] = (map[a.author] || 0) + 1;
      else a.tags.forEach(function (t) { map[t] = (map[t] || 0) + 1; });
    });
    return map;
  }

  /* ---------- 渲染：作者列表（侧边栏行式）---------- */
  function renderAuthors() {
    var ac = countsUnder("author");
    var el = document.getElementById("author-list");
    el.innerHTML = "";
    DATA.authors.forEach(function (au) {
      var cnt = ac[au.name] || 0;
      var item = document.createElement("div");
      item.className = "author-item" + (state.authors.has(au.name) ? " active" : "");
      if (cnt === 0 && state.tags.size) item.style.opacity = ".3";
      item.innerHTML =
        '<span class="ai-name">' + esc(au.name) + '</span>' +
        '<span class="ai-cnt">' + cnt + '</span>';
      item.onclick = function () {
        if (state.authors.has(au.name)) state.authors.delete(au.name);
        else state.authors.add(au.name);
        render();
      };
      el.appendChild(item);
    });
    document.getElementById("author-count").textContent = DATA.authors.length;
    document.getElementById("clear-authors").hidden = state.authors.size === 0;
  }

  /* ---------- 渲染：标签列表（搜索+折叠）---------- */
  function renderTags() {
    var tc = countsUnder("tag");
    var filterEl = document.getElementById("tag-filter");
    var fq = (filterEl ? filterEl.value : "").trim().toLowerCase();

    var filteredTags = DATA.tags.filter(function (t) {
      return !fq || t.name.toLowerCase().indexOf(fq) !== -1;
    });

    var limit = tagExpanded || fq ? filteredTags.length : TAG_LIMIT_DEFAULT;
    var displayTags = filteredTags.slice(0, limit);
    var hasMore = filteredTags.length > limit;

    var el = document.getElementById("tag-list");
    el.innerHTML = "";
    displayTags.forEach(function (tg) {
      var cnt = tc[tg.name] || 0;
      var chip = document.createElement("span");
      chip.className = "tag-chip" + (state.tags.has(tg.name) ? " active" : "") +
        (cnt === 0 && state.authors.size ? " dim" : "");
      chip.innerHTML = esc(tg.name) + '<span class="tc-cnt">' + cnt + '</span>';
      chip.onclick = function () {
        if (state.tags.has(tg.name)) state.tags.delete(tg.name);
        else state.tags.add(tg.name);
        render();
      };
      el.appendChild(chip);
    });

    var expBtn = document.getElementById("tag-expand");
    if (hasMore || (!tagExpanded && DATA.tags.length > TAG_LIMIT_DEFAULT)) {
      expBtn.hidden = false;
      expBtn.innerHTML = (tagExpanded ? "收起" : "展开全部") +
        ' (' + DATA.tags.length + ') <span>' + (tagExpanded ? "▴" : "▾") + "</span>";
    } else {
      expBtn.hidden = true;
    }

    document.getElementById("tag-count").textContent = DATA.tags.length;
    document.getElementById("clear-tags").hidden = state.tags.size === 0;
  }

  /* ---------- 渲染：卡片网格 ---------- */
  function renderGrid() {
    var list = filtered();
    if (state.sort === "title")
      list = list.slice().sort(function (a, b) { return a.title.localeCompare(b.title, "zh"); });
    else
      list = list.slice().sort(function (a, b) { return (b.date || "").localeCompare(a.date || ""); });

    var grid = document.getElementById("grid");
    grid.innerHTML = "";
    document.getElementById("empty").hidden = list.length !== 0;

    list.forEach(function (a) {
      var card = document.createElement("div");
      card.className = "card";

      var cover = a.cover
        ? '<div class="card-cover"><img src="' + esc(a.cover) + '" alt="" loading="lazy" onerror="this.parentElement.style.display=\'none\'"></div>'
        : "";

      var tagsHtml = a.tags.slice(0, 4).map(function (t) {
        return '<span class="ct">' + esc(t) + "</span>";
      }).join("");

      card.innerHTML =
        cover +
        '<div class="card-body">' +
          '<h3>' + esc(a.title) + "</h3>" +
          '<div class="card-meta"><span class="c-author">' + esc(a.author) + "</span>" +
          (a.date ? "<span>· " + esc(a.date) + "</span>" : "") + "</div>" +
          (a.excerpt ? "<p class=\"card-excerpt\">" + esc(a.excerpt) + "</p>" : "") +
          (tagsHtml ? "<div class=\"card-tags\">" + tagsHtml + "</div>" : "") +
        "</div>";

      card.onclick = function () { window.location.href = ARTICLE_URL(a.id); };
      grid.appendChild(card);
    });

    document.getElementById("result-count").textContent =
      "共 " + list.length + " 篇 / 全部 " + DATA.total + " 篇";
  }

  /* ---------- 统一渲染 + URL 深链 ---------- */
  function render() {
    renderAuthors();
    renderTags();
    renderGrid();
    var params = new URLSearchParams();
    if (state.authors.size) params.set("author", Array.from(state.authors).join(","));
    if (state.tags.size) params.set("tag", Array.from(state.tags).join(","));
    if (state.q) params.set("q", state.q);
    history.replaceState(null, "", params.toString() ? ("?" + params.toString()) : location.pathname);
  }

  function resetFilters() {
    state.authors.clear(); state.tags.clear();
    state.q = "";
    var si = document.getElementById("search"); if (si) si.value = "";
    var tf = document.getElementById("tag-filter"); if (tf) tf.value = "";
    render();
  }
  window.App = window.App || {}; window.App.resetFilters = resetFilters;

  /* ---------- 初始化 ---------- */
  function initIndex() {
    document.getElementById("footer-meta").textContent =
      "剪藏分享 · " + DATA.total + " 篇 · " + DATA.authors.length + " 位作者 · " + DATA.tags.length + " 个标签";

    var params = new URLSearchParams(location.search);
    if (params.get("author")) params.get("author").split(",").forEach(function (x) { state.authors.add(x); });
    if (params.get("tag")) params.get("tag").split(",").forEach(function (x) { state.tags.add(x); });
    if (params.get("q")) { state.q = params.get("q"); document.getElementById("search").value = state.q; }

    var searchInput = document.getElementById("search");
    searchInput.addEventListener("input", function () { state.q = searchInput.value; render(); });

    document.getElementById("clear-authors").onclick = function () { state.authors.clear(); render(); };
    document.getElementById("clear-tags").onclick = function () { state.tags.clear(); render(); };

    var tagFilter = document.getElementById("tag-filter");
    tagFilter.addEventListener("input", function () { renderTags(); });

    document.getElementById("tag-expand").onclick = function () { tagExpanded = !tagExpanded; renderTags(); };

    Array.prototype.forEach.call(document.querySelectorAll(".sort-opt"), function (label) {
      label.addEventListener("click", function () {
        document.querySelectorAll(".sort-opt").forEach(function (l) { l.classList.remove("active"); });
        label.classList.add("active");
        var inp = label.querySelector("input");
        if (inp) { inp.checked = true; state.sort = inp.value; renderGrid(); }
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "/" && !["INPUT","TEXTAREA"].includes((e.target||{}).tagName)) {
        e.preventDefault(); searchInput.focus(); searchInput.select();
      }
    });

    // 移动端侧边栏
    var sidebar = document.getElementById("sidebar");
    var overlay = document.getElementById("sidebar-overlay");
    var toggle = document.getElementById("sidebar-toggle");
    if (toggle) toggle.onclick = function () { sidebar.classList.add("open"); overlay.hidden = false; };
    if (overlay) overlay.onclick = function () { sidebar.classList.remove("open"); overlay.hidden = true; };

    render();
  }

  /* ================= 后台管理 ================= */
  var adminMode = "readonly";

  function initAdmin() {
    var openBtn = document.getElementById("admin-open");
    var modal = document.getElementById("admin-modal");
    var closeBtn = document.getElementById("admin-close");
    if (!openBtn || !modal || !closeBtn) return;

    function closeModal() { modal.hidden = true; }

    openBtn.onclick = function () { modal.hidden = false; loadAdmin(); };
    closeBtn.onclick = function (e) { e.stopPropagation(); closeModal(); };
    modal.addEventListener("click", function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !modal.hidden) closeModal();
    });
    if (location.protocol === "file:") { adminMode = "readonly"; return; }
    fetch("/__admin_status__", { method: "HEAD" })
      .then(function (r) { adminMode = r.ok ? "edit" : "readonly"; })
      .catch(function () { adminMode = "readonly"; });
  }

  function api(path, opts) {
    opts = opts || {};
    return fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, opts));
  }

  function loadAdmin() {
    var body = document.getElementById("admin-body");
    var notice = adminMode === "readonly"
      ? '<div class="notice">当前为只读模式。请在本地运行 <code>python3 serve.py</code> 后通过本地地址访问，即可编辑内容。</div>'
      : "";
    body.innerHTML = notice +
      '<div class="admin-tabs">' +
      '<span class="admin-tab active" data-tab="articles">文章</span>' +
      '<span class="admin-tab" data-tab="tags">标签</span>' +
      '<span class="admin-tab" data-tab="authors">作者</span>' +
      "</div><div id=\"admin-tab-body\"></div>";
    Array.prototype.forEach.call(body.querySelectorAll(".admin-tab"), function (t) {
      t.onclick = function () {
        body.querySelectorAll(".admin-tab").forEach(function (x) { x.classList.remove("active"); });
        t.classList.add("active");
        showAdminTab(t.getAttribute("data-tab"));
      };
    });
    showAdminTab("articles");
  }

  function showAdminTab(tab) {
    var box = document.getElementById("admin-tab-body");
    if (tab === "articles") renderAdminArticles(box);
    else if (tab === "tags") renderAdminTags(box);
    else if (tab === "authors") renderAdminAuthors(box);
  }

  function renderAdminArticles(box) {
    var ro = adminMode === "readonly";
    box.innerHTML =
      '<div class="admin-section">' +
      (ro ? "" :
        '<h3>新增文章</h3>' +
        '<div class="form-row"><input id="na-author" placeholder="作者（文件夹名）"><input id="na-title" placeholder="标题"></div>' +
        '<div class="form-row"><input id="na-tags" placeholder="标签，逗号分隔"></div>' +
        '<div class="form-row"><textarea id="na-body" placeholder="Markdown 正文"></textarea></div>' +
        '<div class="form-row"><button class="btn" id="na-save">创建</button></div>') +
      '<h3>文章列表（点击编辑）</h3>' +
      '<div class="form-row"><input id="aa-q" placeholder="搜索标题…"></div>' +
      '<div class="admin-list" id="aa-list"></div></div>';

    function refresh() {
      var q = (document.getElementById("aa-q").value || "").toLowerCase();
      api("/api/articles?q=" + encodeURIComponent(q)).then(function (r) { return r.json(); }).then(function (list) {
        var el = document.getElementById("aa-list"); el.innerHTML = "";
        list.slice(0, 200).forEach(function (a) {
          var row = document.createElement("div"); row.className = "admin-row";
          row.innerHTML = '<span class="grow">' + esc(a.title) + '</span><span class="row-cnt">' + esc(a.author) + '</span>';
          var act = document.createElement("div"); act.className = "row-act";
          var eb = document.createElement("button"); eb.className = "mini-btn"; eb.textContent = "编辑";
          eb.onclick = function () { openArticleEditor(a.id, box); }; act.appendChild(eb);
          if (!ro) {
            var db = document.createElement("button"); db.className = "mini-btn danger"; db.textContent = "删除";
            db.onclick = function () { if (confirm("确认删除《" + a.title + "》？")) api("/api/article/" + a.id, { method: "DELETE" }).then(function () { refresh(); setTimeout(reloadData, 600); }); };
            act.appendChild(db);
          }
          row.appendChild(act); el.appendChild(row);
        });
      }).catch(function () { box.innerHTML = '<p class="notice">无法连接本地管理服务。</p>'; });
    }
    if (!ro) document.getElementById("na-save").onclick = function () {
      var p = { author: document.getElementById("na-author").value.trim(), title: document.getElementById("na-title").value.trim(),
        tags: document.getElementById("na-tags").value.split(",").map(function(s){return s.trim();}).filter(Boolean), body: document.getElementById("na-body").value };
      if (!p.author || !p.title) { alert("作者与标题必填"); return; }
      api("/api/article/new", { method: "POST", body: JSON.stringify(p) }).then(function(){alert("已创建");refresh();setTimeout(reloadData,600);});
    };
    var qEl = document.getElementById("aa-q"); if (qEl) qEl.addEventListener("input", refresh);
    refresh();
  }

  function openArticleEditor(id, box) {
    api("/api/article/" + id).then(function(r){return r.json();}).then(function(a){
      box.innerHTML='<div class="admin-section"><h3>编辑：'+esc(a.title)+'</h3>'+
        '<div class="form-row"><input id="ed-title" value="'+esc(a.title)+'"></div>'+
        '<div class="form-row"><input id="ed-tags" value="'+esc(a.tags.join(", "))+'" placeholder="标签，逗号分隔"></div>'+
        '<div class="form-row"><textarea id="ed-body">'+esc(a.body)+'</textarea></div>'+
        '<div class="form-row"><button class="btn" id="ed-save">保存</button><button class="btn ghost" id="ed-back">返回</button></div></div>';
      document.getElementById("ed-back").onclick=function(){showAdminTab("articles");};
      document.getElementById("ed-save").onclick=function(){
        var p={title:document.getElementById("ed-title").value.trim(),
          tags:document.getElementById("ed-tags").value.split(",").map(function(s){return s.trim();}).filter(Boolean),
          body:document.getElementById("ed-body").value};
        api("/api/article/"+id,{method:"PUT",body:JSON.stringify(p)}).then(function(){alert("已保存");showAdminTab("articles");setTimeout(reloadData,600);});
      };
    });
  }

  function renderAdminTags(box) {
    var ro=adminMode==="readonly";
    box.innerHTML='<div class="admin-section">'+
      (ro?"":'<h3>合并 / 重命名标签</h3><div class="form-row"><input id="tg-from" placeholder="原标签"><input id="tg-to" placeholder="目标标签"><button class="btn" id="tg-merge">合并</button><button class="btn ghost" id="tg-rename">重命名为</button></div>')+
      '<h3>全部标签</h3><div class="admin-list" id="tg-list"></div></div>';
    function refresh(){
      api("/api/tags").then(function(r){return r.json();}).then(function(d){
        var el=document.getElementById("tg-list");el.innerHTML="";
        d.tags.slice().sort(function(a,b){return b.count-a.count;}).forEach(function(t){
          var row=document.createElement("div");row.className="admin-row";
          row.innerHTML='<span class="grow">'+esc(t.name)+'</span><span class="row-cnt">'+t.count+'</span>';el.appendChild(row);
        });
      }).catch(function(){box.innerHTML='<p class="notice">无法连接本地管理服务。</p>';});
    }
    if(!ro){
      document.getElementById("tg-merge").onclick=function(){
        var f=document.getElementById("tg-from").value.trim(),t=document.getElementById("tg-to").value.trim();
        if(!f||!t){alert("请填写原标签与目标标签");return;}
        api("/api/tag",{method:"POST",body:JSON.stringify({from:f,to:t,action:"merge"})}).then(function(){alert("已合并");refresh();setTimeout(reloadData,600);});
      };
      document.getElementById("tg-rename").onclick=function(){
        var f=document.getElementById("tg-from").value.trim(),t=document.getElementById("tg-to").value.trim();
        if(!f||!t){alert("请填写原标签与新名称");return;}
        api("/api/tag",{method:"POST",body:JSON.stringify({from:f,to:t,action:"rename"})}).then(function(){alert("已重命名");refresh();setTimeout(reloadData,600);});
      };
    }
    refresh();
  }

  function renderAdminAuthors(box){
    var ro=adminMode==="readonly";
    box.innerHTML='<div class="admin-section">'+
      (ro?"":'<h3>重命名 / 合并作者</h3><div class="form-row"><input id="au-from" placeholder="原作者"><input id="au-to" placeholder="目标作者"><button class="btn" id="au-rename">重命名</button></div>')+
      '<h3>全部作者</h3><div class="admin-list" id="au-list"></div></div>';
    function refresh(){
      api("/api/authors").then(function(r){return r.json();}).then(function(list){
        var el=document.getElementById("au-list");el.innerHTML="";
        list.forEach(function(a){
          var row=document.createElement("div");row.className="admin-row";
          row.innerHTML='<span class="grow">'+esc(a.name)+'</span><span class="row-cnt">'+a.count+'</span>';el.appendChild(row);
        });
      }).catch(function(){box.innerHTML='<p class="notice">无法连接本地管理服务。</p>';});
    }
    if(!ro)document.getElementById("au-rename").onclick=function(){
      var f=document.getElementById("au-from").value.trim(),t=document.getElementById("au-to").value.trim();
      if(!f||!t)return;if(!confirm("将「"+f+"」下的文章移动到「"+t+"」？"))return;
      api("/api/author",{method:"POST",body:JSON.stringify({from:f,to:t})}).then(function(){alert("已完成");refresh();setTimeout(reloadData,600);});
    };
    refresh();
  }

  function reloadData(){
    if(location.protocol==="file:")return;
    api("/assets/data.js").then(function(r){return r.text();}).then(function(txt){
      try{var m=txt.match(/window\.__SITE_DATA__\s*=\s*(\{[\s\S]*\})\s*;/);
        if(m){DATA=JSON.parse(m[1]);if(document.getElementById("grid"))render();}
      }catch(e){}
    });
  }

  /* ---------- 启动 ---------- */
  if (document.getElementById("grid")) initIndex();
  initAdmin();
})();
