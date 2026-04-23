import { Client } from '@notionhq/client';
import { NotionToMarkdown } from 'notion-to-md';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import https from 'node:https';
import dns from 'node:dns/promises';
import net from 'node:net';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const config = JSON.parse(await fs.readFile(path.join(__dirname, 'notion-pages.json'), 'utf8'));

const DRY_RUN = !!process.env.DRY_RUN;
const NOTION_TOKEN = process.env.NOTION_TOKEN;

if (!DRY_RUN && !NOTION_TOKEN) {
  console.error('ERROR: NOTION_TOKEN env var required (or set DRY_RUN=1)');
  process.exit(1);
}

// Pin API version; SDK has built-in retry with exponential backoff for 429/5xx
const notion = DRY_RUN ? null : new Client({
  auth: NOTION_TOKEN,
  notionVersion: '2026-03-11',
});

// Download constraints
const MAX_REDIRECTS = 5;
const MAX_IMAGE_BYTES = 25 * 1024 * 1024; // 25MB
const DOWNLOAD_TIMEOUT_MS = 30_000;
const IMAGE_HOST_ALLOWLIST = [
  /\.amazonaws\.com$/i,
  /\.notion\.so$/i,
  /\.notion-static\.com$/i,
];

// ============================================================
// Utilities
// ============================================================

function slugify(text) {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-+/g, '-')
    .slice(0, 60);
}

function shortHash(str, len = 8) {
  return crypto.createHash('sha256').update(str).digest('hex').slice(0, len);
}

function sanitizeYamlString(s) {
  return (s || '').replace(/[\r\n]+/g, ' ').replace(/"/g, '\\"').trim();
}

function getExtension(url) {
  const cleanUrl = url.split('?')[0];
  const m = cleanUrl.match(/\.([a-zA-Z0-9]{3,4})$/);
  return m ? m[1].toLowerCase() : 'png';
}

function redactUrl(url) {
  try {
    const u = new URL(url);
    return `${u.origin}${u.pathname}`;
  } catch { return '[invalid-url]'; }
}

async function writeFileEnsuringDir(absPath, content) {
  await fs.mkdir(path.dirname(absPath), { recursive: true });
  await fs.writeFile(absPath, content);
}

// SSRF guard: HTTPS only + hostname allowlist + private IP block
async function assertSafeUrl(url) {
  const u = new URL(url);
  if (u.protocol !== 'https:') throw new Error(`Non-HTTPS blocked: ${u.protocol}`);
  const hostOk = IMAGE_HOST_ALLOWLIST.some((rx) => rx.test(u.hostname));
  if (!hostOk) throw new Error(`Host not in allowlist: ${u.hostname}`);
  try {
    const addrs = await dns.lookup(u.hostname, { all: true });
    for (const a of addrs) {
      if (!net.isIP(a.address)) continue;
      if (a.address.startsWith('10.') || a.address.startsWith('192.168.') ||
          a.address.startsWith('127.') || a.address.startsWith('169.254.') ||
          a.address.startsWith('::1') || a.address === '0.0.0.0' ||
          /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(a.address)) {
        throw new Error(`Private IP blocked: ${a.address}`);
      }
    }
  } catch (err) {
    if (err.message.startsWith('Private IP') || err.message.startsWith('Non-HTTPS') || err.message.startsWith('Host not')) throw err;
    // DNS failure → let https.get handle
  }
}

async function downloadFile(url, targetPath, redirectsLeft = MAX_REDIRECTS) {
  // Idempotency: skip if already exists and non-empty
  try {
    const st = await fs.stat(targetPath);
    if (st.size > 0) return;
  } catch {}

  await assertSafeUrl(url);
  await fs.mkdir(path.dirname(targetPath), { recursive: true });

  const tmpPath = `${targetPath}.tmp-${process.pid}`;
  return new Promise((resolve, reject) => {
    const req = https.get(url, { timeout: DOWNLOAD_TIMEOUT_MS }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        if (redirectsLeft <= 0) return reject(new Error('Too many redirects'));
        return downloadFile(res.headers.location, targetPath, redirectsLeft - 1).then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode} for ${redactUrl(url)}`));
      }
      const chunks = [];
      let bytes = 0;
      res.on('data', (c) => {
        bytes += c.length;
        if (bytes > MAX_IMAGE_BYTES) {
          res.destroy();
          return reject(new Error(`Image exceeds ${MAX_IMAGE_BYTES} bytes: ${redactUrl(url)}`));
        }
        chunks.push(c);
      });
      res.on('end', async () => {
        try {
          await fs.writeFile(tmpPath, Buffer.concat(chunks));
          await fs.rename(tmpPath, targetPath); // atomic
          resolve();
        } catch (err) { reject(err); }
      });
      res.on('error', reject);
    });
    req.on('timeout', () => { req.destroy(new Error('Download timeout')); });
    req.on('error', reject);
  });
}

// Fetch ALL children (handles pagination for blocks with >100 children)
async function fetchAllChildren(blockId) {
  const all = [];
  let cursor;
  do {
    const res = await notion.blocks.children.list({
      block_id: blockId,
      page_size: 100,
      start_cursor: cursor,
    });
    all.push(...res.results);
    cursor = res.has_more ? res.next_cursor : undefined;
  } while (cursor);
  return all;
}

// ============================================================
// Per-page: fresh n2m instance per page (transformers reference page context)
// ============================================================

function buildFrontMatter(fields) {
  const lines = ['---'];
  for (const [k, v] of Object.entries(fields)) {
    if (v === undefined || v === null) continue;
    const val = typeof v === 'string' ? `"${sanitizeYamlString(v)}"` : v;
    lines.push(`${k}: ${val}`);
  }
  lines.push('---', '');
  return lines.join('\n');
}

function createN2M(pageSlug, imageTasks, subPageIdByTitle) {
  const n2m = new NotionToMarkdown({
    notionClient: notion,
    config: { parseChildPages: true, separateChildPage: true },
  });

  // Callout → kramdown-compatible div
  n2m.setCustomTransformer('callout', async (block) => {
    const callout = block.callout;
    const color = callout.color || 'gray_bg';
    let icon = '';
    if (callout.icon?.type === 'emoji') icon = callout.icon.emoji;
    else if (callout.icon?.type === 'custom_emoji') icon = '📄';
    const text = callout.rich_text.map((t) => {
      let s = t.plain_text;
      if (t.annotations.bold) s = `**${s}**`;
      if (t.annotations.italic) s = `*${s}*`;
      if (t.href) s = `[${s}](${t.href})`;
      return s;
    }).join('');
    return `<div class="callout ${color}" markdown="1">\n${icon} ${text}\n</div>\n\n`;
  });

  // Heading_3 with is_toggleable → <details><summary><h3>
  n2m.setCustomTransformer('heading_3', async (block) => {
    const h3 = block.heading_3;
    const text = h3.rich_text.map((t) => t.plain_text).join('');
    if (h3.is_toggleable && block.has_children) {
      const children = await fetchAllChildren(block.id);
      const mdBlocks = await n2m.blocksToMarkdown(children);
      const innerMd = n2m.toMarkdownString(mdBlocks).parent || '';
      return `<details>\n<summary><h3>${text}</h3></summary>\n\n${innerMd}\n</details>\n\n`;
    }
    return `### ${text}\n\n`;
  });

  // Image → deterministic filename (block.id only — NOT signed URL)
  n2m.setCustomTransformer('image', async (block) => {
    const img = block.image;
    const url = img.type === 'file' ? img.file.url : img.external.url;
    const caption = img.caption?.map((t) => t.plain_text).join('') || '';
    const ext = getExtension(url);
    const filename = `${shortHash(block.id)}.${ext}`;
    const relPath = `/${config.options.imageDir}/${pageSlug}/${filename}`;
    const absPath = path.join(REPO_ROOT, config.options.imageDir, pageSlug, filename);
    imageTasks.push({ url, absPath });
    return `![${caption}](${relPath})\n\n`;
  });

  // child_page → capture title→id mapping for stable slug routing
  n2m.setCustomTransformer('child_page', async (block) => {
    const title = block.child_page?.title || '';
    if (title) subPageIdByTitle.set(title, block.id);
    return false; // fall back to library default (renders as heading2 for separate-pages mode)
  });

  return n2m;
}

// ============================================================
// Main sync per page
// ============================================================

async function syncPage(pageId, pageConfig) {
  const { target, slug, title, permalink } = pageConfig;

  if (DRY_RUN) {
    console.log(`[DRY_RUN] Would sync ${title} → ${target}`);
    const fm = buildFrontMatter({
      layout: 'page',
      title,
      permalink,
      notion_id: pageId,
      notion_last_edited: '2026-04-24T00:00:00.000Z',
    });
    const body = `<!-- DRY_RUN fixture -->\n\n## Тестовая страница\n\n<div class="callout gray_bg" markdown="1">\n📝 Это заглушка для DRY_RUN режима.\n</div>\n\n<details>\n<summary>Test toggle</summary>\nContent inside toggle.\n</details>\n`;
    await writeFileEnsuringDir(path.join(REPO_ROOT, target), fm + body);
    return { imageCount: 0, subPageCount: 0 };
  }

  const imageTasks = [];
  const subPageIdByTitle = new Map();
  const n2m = createN2M(slug, imageTasks, subPageIdByTitle);

  const pageMeta = await notion.pages.retrieve({ page_id: pageId });
  const mdblocks = await n2m.pageToMarkdown(pageId);
  const mdObject = n2m.toMarkdownString(mdblocks);

  // Main page content — rewrite sub-page headings to links with stable id-based slugs
  let parentContent = mdObject.parent || '';
  const subPages = [];
  for (const [title, md] of Object.entries(mdObject)) {
    if (title === 'parent') continue;
    if (!title) continue; // guard against empty title
    const subId = subPageIdByTitle.get(title);
    // Stable slug: id-based suffix prevents broken links on title rename + avoids slug collisions
    const subSlug = subId
      ? `${slugify(title) || 'page'}-${shortHash(subId, 6)}`
      : `${slugify(title) || 'page'}-${shortHash(title, 6)}`;
    subPages.push({ title, slug: subSlug, content: md });

    // Replace only the first occurrence of `## {title}` (literal). Escape regex specials.
    const escaped = title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    parentContent = parentContent.replace(
      new RegExp(`^## ${escaped}$`, 'm'),
      `- [${title}](/cases/${subSlug}/)`,
    );
  }

  const frontMatter = buildFrontMatter({
    layout: 'page',
    title,
    permalink,
    notion_id: pageId,
    notion_last_edited: pageMeta.last_edited_time,
  });

  await writeFileEnsuringDir(path.join(REPO_ROOT, target), frontMatter + parentContent);

  // Write sub-pages with stable slug + id-based filename
  for (const sp of subPages) {
    const subFm = buildFrontMatter({
      layout: 'page',
      title: sp.title,
      permalink: `/cases/${sp.slug}/`,
      parent_notion_id: pageId,
    });
    const subAbs = path.join(REPO_ROOT, config.options.subPagesDir, `${sp.slug}.md`);
    await writeFileEnsuringDir(subAbs, subFm + sp.content);
  }

  // Download images — concurrency bound at 4 to avoid S3 throttle
  const imgResults = await runBounded(imageTasks, 4, (t) => downloadFile(t.url, t.absPath));
  const imageErrors = imgResults.filter((r) => r.status === 'rejected');
  if (imageErrors.length > 0) {
    console.warn(`⚠️  ${imageErrors.length} image(s) failed for ${slug}`);
    imageErrors.forEach((r) => console.warn('  -', r.reason.message));
  }

  return {
    imageCount: imageTasks.length - imageErrors.length,
    subPageCount: subPages.length,
  };
}

// Bounded concurrency helper
async function runBounded(items, limit, worker) {
  const results = new Array(items.length);
  let idx = 0;
  async function run() {
    while (idx < items.length) {
      const i = idx++;
      try {
        const value = await worker(items[i]);
        results[i] = { status: 'fulfilled', value };
      } catch (err) {
        results[i] = { status: 'rejected', reason: err };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, run));
  return results;
}

// ============================================================
// Main
// ============================================================

async function main() {
  console.log(`🚀 Notion sync start ${DRY_RUN ? '[DRY_RUN]' : '[LIVE]'}`);
  let totalImages = 0;
  let totalSubPages = 0;
  let failed = 0;
  const pageCount = Object.keys(config.pages).length;

  for (const [pageId, pageConfig] of Object.entries(config.pages)) {
    try {
      console.log(`→ ${pageConfig.title}`);
      const { imageCount, subPageCount } = await syncPage(pageId, pageConfig);
      totalImages += imageCount;
      totalSubPages += subPageCount;
      console.log(`  ✓ ${pageConfig.target} (${imageCount} imgs, ${subPageCount} sub-pages)`);
    } catch (err) {
      console.error(`  ✗ FAILED ${pageConfig.title}: ${err.message}`);
      failed++;
    }
  }

  console.log(`\n📊 ${pageCount - failed}/${pageCount} pages OK, ${totalImages} images, ${totalSubPages} sub-pages`);
  if (failed > 0) process.exit(1);
}

main().catch((err) => {
  console.error('💥 Fatal:', err.message);
  process.exit(1);
});
