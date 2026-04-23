# pio blog — Style Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Приблизить визуал постов и главной к zine-стилю sereja.tech — уже колонка, спокойные тона, теги-пиллы сверху поста, callout-блоки, отдельная страница архива — без правок темы Beautiful Jekyll, навбара и сайдбара.

**Architecture:** Всё в `assets/css/overrides.css` (включается через `site-css` в `_config.yml`). Два layout-файла (`post.html`, `home.html`) точечно модифицируются. Создаётся одна новая страница `archive.md`. Тема не форкается.

**Tech Stack:** Jekyll 3.x (GitHub Pages), Beautiful Jekyll theme, Bootstrap 5 (под капотом темы), Liquid, kramdown markdown, CSS `:has()` для скоупинга.

**Spec:** [docs/superpowers/specs/2026-04-24-blog-style-refresh-design.md](../specs/2026-04-24-blog-style-refresh-design.md)

**Workflow:** Работаем на `master`. Коммитим после каждой задачи. Пушим в конце (Task 9). GitHub Pages ребилдит автоматически.

---

## Task 1: Scaffolding — overrides.css и site-css hook

**Files:**
- Create: `assets/css/overrides.css`
- Modify: `_config.yml`

- [ ] **Step 1: Create the overrides stylesheet**

Write to `assets/css/overrides.css`:

```css
/* =============================================================
   overrides.css — визуальный refresh pio blog
   Spec: docs/superpowers/specs/2026-04-24-blog-style-refresh-design.md
   Подключается через site-css в _config.yml
   ============================================================= */
```

- [ ] **Step 2: Wire the stylesheet into _config.yml**

Open `_config.yml`, find the commented block (around line 95):

```yaml
# For any extra visual customization, you can include additional CSS files in every page on your site. List any custom CSS files here
#site-css:
#  - "/assets/css/custom-styles.css"
#  - "/assets/js/custom-script.js"
```

Replace with:

```yaml
# For any extra visual customization, you can include additional CSS files in every page on your site. List any custom CSS files here
site-css:
  - "/assets/css/overrides.css"
```

- [ ] **Step 3: Sanity-check the hook**

Run: `grep -n "site-css" _config.yml`
Expected: shows the uncommented `site-css:` line.

- [ ] **Step 4: Commit**

```bash
git add assets/css/overrides.css _config.yml
git commit -m "add overrides.css hook for style refresh"
```

---

## Task 2: Post — narrow column + typography scale (V3)

**Files:**
- Modify: `assets/css/overrides.css`

- [ ] **Step 1: Append post-layout CSS**

Append to `assets/css/overrides.css`:

```css
/* =======================================
   POST — narrow column (620px) + type scale
   Использует :has() для скоупа «только на странице поста»
   ======================================= */
.container-md .row > div:has(> article.blog-post) {
  max-width: 620px;
  flex: 0 0 100%;
  margin-left: auto !important;
  margin-right: auto !important;
}

article.blog-post {
  font-size: 1rem;
  line-height: 1.7;
}
article.blog-post h1 { font-size: 1.75rem; }
article.blog-post h2 { font-size: 1.375rem; margin-top: 2rem; }
article.blog-post h3 { font-size: 1.125rem; margin-top: 1.5rem; }
```

- [ ] **Step 2: Verify CSS is syntactically valid**

Run: `cat assets/css/overrides.css | head -30`
Expected: shows the new rules, no unmatched braces.

- [ ] **Step 3: Commit**

```bash
git add assets/css/overrides.css
git commit -m "narrow post column to 620px and scale down headings"
```

---

## Task 3: Move tags to top of post

**Files:**
- Modify: `_layouts/post.html`

- [ ] **Step 1: Remove the bottom tags block**

Open `_layouts/post.html`. Find the block that renders tags under the article (around line 46-54):

```liquid
      {% if page.tags.size > 0 %}
        <div class="blog-tags">
          <span>Tags:</span>
          {% for tag in page.tags %}
            <a href="{{ '/tags' | relative_url }}#{{- tag -}}">{{- tag -}}</a>
          {% endfor %}
        </div>
      {% endif %}
```

Delete the entire block (9 lines).

- [ ] **Step 2: Insert the new top tags block**

In the same file, find the line `{% include header.html type="post" %}` (near the top, around line 5). Insert the new tags block immediately after it, before the `<div class="{% if page.full-width %}...`. Result should look like:

```liquid
{% include header.html type="post" %}

<div class="{% if page.full-width %} container-fluid {% else %} container-md {% endif %}">
  <div class="row">
    <div class="{% if page.full-width %} col {% else %} col-xl-8 offset-xl-2 col-lg-10 offset-lg-1 {% endif %}">

      {% if page.tags.size > 0 %}
        <div class="blog-tags blog-tags-top">
          {% for tag in page.tags %}
            <a href="{{ '/tags' | relative_url }}#{{- tag -}}">{{- tag -}}</a>
          {% endfor %}
        </div>
      {% endif %}
```

Key differences from original:
- Placed BEFORE `{% if page.gh-repo %}` block (first child of the inner col)
- Class changed to `blog-tags blog-tags-top`
- The `<span>Tags:</span>` label is REMOVED (pills don't need a prefix label)

- [ ] **Step 3: Verify the layout renders without Liquid errors**

Run: `grep -c "blog-tags-top" _layouts/post.html`
Expected: `1` (one occurrence — the new block)

Run: `grep -c "blog-tags" _layouts/post.html`
Expected: `1` (only the new `blog-tags blog-tags-top` — the old block is gone)

- [ ] **Step 4: Commit**

```bash
git add _layouts/post.html
git commit -m "move post tags from below article to top of post"
```

---

## Task 4: Tag pills + pre border + callouts

**Files:**
- Modify: `assets/css/overrides.css`

- [ ] **Step 1: Append styles for tags, code blocks, callouts**

Append to `assets/css/overrides.css`:

```css
/* =======================================
   POST — теги-пиллы наверху
   ======================================= */
.blog-tags.blog-tags-top {
  margin: 0 0 1.75rem;
  padding: 0;
  border: 0;
  font-family: 'Open Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.blog-tags.blog-tags-top a {
  font-size: 12px;
  padding: 2px 10px;
  margin: 0;
  border: 1px solid #222;
  color: #222;
  border-radius: 999px;
  text-decoration: none;
  background: transparent;
}
.blog-tags.blog-tags-top a:hover {
  background: #222;
  color: #fff;
  text-decoration: none;
}

/* =======================================
   POST — <pre> с рамкой, без серой заливки
   ======================================= */
article.blog-post pre {
  background: transparent;
  border: 1px solid #222;
  border-radius: 2px;
  padding: 14px 16px;
  overflow-x: auto;
}

/* =======================================
   POST — callout-блоки
   Использование в markdown (kramdown):
     <div class="callout insight" markdown="1">
     **Идея** — краткое пояснение идеи.
     </div>
   ======================================= */
.callout {
  border: 1px solid #ddd;
  border-left: 3px solid #888;
  padding: 12px 16px;
  margin: 20px 0;
  background: #fafafa;
}
.callout.insight { border-left-color: #1e8a4a; }
.callout.warning { border-left-color: #c0392b; }
.callout > p:first-child strong:first-child {
  color: #222;
}
.callout > p:last-child { margin-bottom: 0; }
```

- [ ] **Step 2: Verify file is well-formed**

Run: `grep -c "}" assets/css/overrides.css && grep -c "{" assets/css/overrides.css`
Expected: same number of `{` and `}`.

- [ ] **Step 3: Commit**

```bash
git add assets/css/overrides.css
git commit -m "style post tags as pills, pre with border, add callout classes"
```

---

## Task 5: Home — softer cards (H1)

**Files:**
- Modify: `assets/css/overrides.css`

- [ ] **Step 1: Append home-feed CSS**

Append to `assets/css/overrides.css`:

```css
/* =======================================
   HOME — карточки постов помягче (H1)
   Перебиваем beautifuljekyll.css по месту
   ======================================= */
.posts-list {
  max-width: 680px;
  margin-left: auto;
  margin-right: auto;
}

.post-preview {
  padding: 1rem 0 1.5rem !important;
  border-bottom: 1px solid #f2f2f2 !important;
}
.post-preview:last-of-type {
  border-bottom: 0 !important;
}

.post-preview .post-title {
  font-size: 1.375rem !important;
  margin-top: 0 !important;
}
.post-preview .post-subtitle {
  font-weight: 400 !important;
  font-size: 1rem !important;
  color: #777 !important;
  margin-bottom: 0.5rem !important;
}
.post-preview .post-meta {
  color: #999 !important;
  font-size: 0.8125rem !important;
}
.post-preview .post-image {
  height: 7rem !important;
  max-width: 7rem !important;
  filter: none !important;
  margin-left: 14px;
}
.post-preview .post-image img {
  max-height: 7rem;
}
.post-preview .post-read-more { display: none !important; }
.post-preview .blog-tags { display: none !important; }
```

- [ ] **Step 2: Verify**

Run: `grep -c "post-preview" assets/css/overrides.css`
Expected: `8` or more (each rule counted)

- [ ] **Step 3: Commit**

```bash
git add assets/css/overrides.css
git commit -m "soften home feed cards (smaller image, thinner borders, hide read-more)"
```

---

## Task 6: «Все посты →» link under home feed

**Files:**
- Modify: `_layouts/home.html`
- Modify: `assets/css/overrides.css`

- [ ] **Step 1: Add the link block to home layout**

Open `_layouts/home.html`. After the closing `</div>` of `<div class="posts-list">` (right before the `{% if paginator.total_pages > 1 %}` block), add:

```liquid
<p class="all-posts-link">
  <a href="{{ '/archive/' | relative_url }}">Все посты &rarr;</a>
</p>
```

- [ ] **Step 2: Append link styles**

Append to `assets/css/overrides.css`:

```css
/* =======================================
   HOME — ссылка «Все посты →»
   ======================================= */
.all-posts-link {
  max-width: 680px;
  margin: 1.5rem auto 0;
  padding-top: 1rem;
  border-top: 1px solid #eee;
  font-family: 'Open Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 0.9375rem;
}
```

- [ ] **Step 3: Verify**

Run: `grep -c "all-posts-link" _layouts/home.html`
Expected: `1`

Run: `grep -c "all-posts-link" assets/css/overrides.css`
Expected: `1` (the class rule)

- [ ] **Step 4: Commit**

```bash
git add _layouts/home.html assets/css/overrides.css
git commit -m "add 'Все посты →' link under home feed"
```

---

## Task 7: Create /archive page

**Files:**
- Create: `archive.md`
- Modify: `assets/css/overrides.css`

- [ ] **Step 1: Create archive.md**

Write to `archive.md` (at repo root):

```markdown
---
layout: page
title: Все посты
permalink: /archive/
---

<div class="archive-page">
{% assign date_format = site.date_format | default: "%B %-d, %Y" %}
{% assign posts_by_year = site.posts | group_by_exp: "post", "post.date | date: '%Y'" %}
{% for year in posts_by_year %}
  <h2 class="archive-year">{{ year.name }}</h2>
  <ul class="archive-list">
    {% for post in year.items %}
    <li>
      <span class="d">{{ post.date | date: date_format }}</span>
      <a href="{{ post.url | relative_url }}">{{ post.title }}</a>
    </li>
    {% endfor %}
  </ul>
{% endfor %}
</div>
```

- [ ] **Step 2: Append archive-page styles to overrides.css**

Append to `assets/css/overrides.css`:

```css
/* =======================================
   ARCHIVE — страница /archive/
   ======================================= */
.archive-page {
  max-width: 600px;
  margin: 0 auto;
  font-family: 'Open Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
.archive-year {
  font-family: 'Open Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 1.125rem;
  margin: 2rem 0 0.75rem;
  color: #222;
}
.archive-page .archive-year:first-of-type { margin-top: 0; }
.archive-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.archive-list li {
  padding: 4px 0;
  display: flex;
  gap: 12px;
  align-items: baseline;
}
.archive-list .d {
  color: #999;
  font-size: 0.8125rem;
  min-width: 110px;
  flex-shrink: 0;
}
.archive-list a {
  font-size: 0.9375rem;
  line-height: 1.3;
}
```

- [ ] **Step 3: Verify archive.md frontmatter**

Run: `head -5 archive.md`
Expected: shows `layout: page`, `title: Все посты`, `permalink: /archive/`.

- [ ] **Step 4: Commit**

```bash
git add archive.md assets/css/overrides.css
git commit -m "add /archive page with posts grouped by year"
```

---

## Task 8: Local syntax sanity check

**Files:** none (pure verification)

- [ ] **Step 1: CSS brace balance**

Run: `awk 'BEGIN{o=0;c=0} /{/{o+=gsub(/{/,"{")} /}/{c+=gsub(/}/,"}")} END{print "opens="o, "closes="c}' assets/css/overrides.css`
Expected: `opens=N closes=N` with the same number.

- [ ] **Step 2: No stray Liquid tags in layouts**

Run: `grep -nE "\{\{|\{%" _layouts/post.html _layouts/home.html archive.md | wc -l`
Expected: >0 (Liquid tags present) and no error messages.

Run: `grep -nE "\{%[^%]*$|[^%]%\}" _layouts/post.html _layouts/home.html archive.md`
Expected: no output (no unclosed Liquid blocks).

- [ ] **Step 3: Overrides file size sanity**

Run: `wc -l assets/css/overrides.css`
Expected: roughly 140-180 lines.

- [ ] **Step 4: Expected commits are in place**

Run: `git log --oneline -7`
Expected: 6 commits from Tasks 1-7 on top of the prior HEAD, in the order they were made.

---

## Task 9: Push and verify live site

**Files:** none (deploy + verify)

- [ ] **Step 1: Push master to GitHub Pages**

```bash
git push origin master
```

- [ ] **Step 2: Wait 60 seconds for Pages rebuild**

Run: `sleep 60 && echo "ready to check"`

- [ ] **Step 3: Curl the archive page**

```bash
curl -sL -o /tmp/archive_check.html https://vedulix.github.io/blog/archive/ && \
  grep -c "archive-year" /tmp/archive_check.html
```
Expected: 2+ (one per year of posts). If 0 — Pages hasn't rebuilt yet; sleep 60s more and retry.

- [ ] **Step 4: Curl the home page**

```bash
curl -sL -o /tmp/home_check.html https://vedulix.github.io/blog/ && \
  grep -c "all-posts-link" /tmp/home_check.html
```
Expected: 1.

- [ ] **Step 5: Curl a post page and check for top tags**

```bash
curl -sL -o /tmp/post_check.html https://vedulix.github.io/blog/consuming-self-development-content-2022-07-17/ && \
  grep -c "blog-tags-top" /tmp/post_check.html
```
Expected: 1.

- [ ] **Step 6: Curl the overrides.css**

```bash
curl -sI https://vedulix.github.io/blog/assets/css/overrides.css | head -1
```
Expected: `HTTP/2 200`.

- [ ] **Step 7: Visual sanity via browser**

Open in browser: `https://vedulix.github.io/blog/`, `https://vedulix.github.io/blog/archive/`, any post.
Check against the spec's «Проверка» section: colonka narrow, теги-пиллы сверху, «Все посты →» внизу главной, архив по годам.

- [ ] **Step 8: Final summary commit (if any post-push fixes)**

If live site shows issues, fix and recommit:
```bash
git add -A
git commit -m "fix post-push regressions"
git push origin master
```

If everything's good — no additional commit needed.

---

## Notes for the implementing agent

- **Do NOT** fork or override any file in the Beautiful Jekyll theme except the two listed layouts (`post.html`, `home.html`) in the user's repo.
- **Do NOT** touch `_includes/header.html`, `_includes/footer.html`, `_layouts/base.html`, `_layouts/default.html`, `_layouts/page.html`, `_config.yml` beyond the `site-css` line.
- **Callouts** are infrastructure only — we add CSS, but don't retrofit existing posts. User decides when to use.
- **CSS `:has()`** targets the post column. Browsers without `:has()` (old Safari <15.4) fall back to wider default column — acceptable degrade.
- **Russian dates**: archive uses `site.date_format` which defaults to English (`%B %-d, %Y`). Matches existing site convention.
- **If a task fails**: stop, report, do NOT push partial work to live. User will triage.
