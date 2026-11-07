# Image search tool (dev-only, not part of the shipped app)

One-time/occasional tool used to find a product photo per catalog item
for the public website. Not imported by `shop` at all -- a separate
Node.js script, run by hand when (re)sourcing images.

## Why a real browser, not a plain HTTP request

Bing Images needs JavaScript to render real results; a plain `curl`/`fetch`
gets back an almost-empty page. This script drives a real, local copy of
Microsoft Edge in headless mode via `puppeteer-core` (no bundled Chromium
download -- it points at Edge, which Windows already has).

**Important:** a fresh **browser process** per search query, not just a
fresh tab. Reusing one browser across several sequential searches got
flagged after roughly a dozen queries -- Bing started returning the same
unrelated "trending images" carousel instead of real results (still a
normal-looking HTTP 200), which only a relevance check against the query
words caught.

## Setup

```
cd tools/image_search
npm install
```

Edge must be installed at the default Windows path
(`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`); edit
`EXE_PATH` near the top of `bing_batch_search.js` if yours lives
elsewhere.

## Usage

Input: a JSON array of `{code, name, unit}` (export with e.g.
`shop.core.products.list_products`).

```
node bing_batch_search.js <input.json> <output.json> [startIndex] [endIndex]
```

For each product it searches Bing Images, keeps every candidate whose
title shares enough words with the product name (rejects the
unrelated-carousel problem above), and writes `{name, query_used, chosen,
candidates}` per code to `<output.json>` -- incrementally, so an
interrupted run can resume by re-pointing at the same output file (it
merges rather than overwrites).

`search_results_full.json` in this folder is the saved result of the
18-19/10/2026 run across the whole catalog -- keep it as a reference for
"swap this one image" requests (every candidate's URL and title is still
there) instead of re-searching from scratch.

## Applying results

This script only finds and ranks candidate image URLs -- it doesn't
download or touch the database. Feed a `chosen.murl` into
`shop.tools.fetch_images.save_product_image()` (download, validate size,
save under the site repo's `images/`, record the source in
`images/manifest.json`, and set the product's `image_filename`).
