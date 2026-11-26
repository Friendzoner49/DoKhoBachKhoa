// Batch Bing Images search (real headless browser -- a plain curl/fetch
// gets an almost-empty shell page, since Bing needs JS to render real
// results). For each product: search the full product name; if nothing
// in the results actually looks like it's about that product, retry
// with a shortened query; pick the best match among TRUSTED_DOMAINS
// first, else the best-scoring match overall. Every raw candidate is
// still saved (not just the pick), so a bad auto-pick can be fixed by
// hand without re-searching from scratch.
const fs = require("fs");
const puppeteer = require("puppeteer-core");

const IN_PATH = process.argv[2];
const OUT_PATH = process.argv[3];
const START = parseInt(process.argv[4] || "0", 10);
const END = parseInt(process.argv[5] || "100000", 10);

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

// Vietnamese grocery retailers/CDNs known for clean, correctly-labelled
// product photography -- preferred when more than one candidate passes
// the relevance filter.
const TRUSTED_DOMAINS = [
  "cdn.tgdd.vn", "bachhoaxanh.com",
  "product.hstatic.net", "bizweb.dktcdn.net",
  "sayweee.com", "img01.weeecdn.com", "img06.weeecdn.com",
  "winmart.vn", "coopmart.com.vn", "aeon.com.vn", "kingfoodmart.com",
  "meta.vn", "farmersmarket.vn",
];

function stripAccents(s) {
  return s.replace(/Đ/g, "D").replace(/đ/g, "d").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function tokens(s) {
  return stripAccents(s).toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length >= 2);
}

function cleanQuery(name) {
  return name
    .replace(/\([^)]*\)/g, " ") // drop parenthetical variant lists
    .replace(/\bTặng\b.*$/i, " ") // drop trailing promo text
    .replace(/\s+/g, " ")
    .trim();
}

function shortQuery(name) {
  return cleanQuery(name).split(" ").slice(0, 4).join(" ");
}

function scoreCandidate(queryTokens, candidate) {
  const titleTokens = new Set(tokens(candidate.t || ""));
  let overlap = 0;
  for (const w of queryTokens) if (titleTokens.has(w)) overlap++;
  return overlap;
}

function isTrusted(murl) {
  try {
    const host = new URL(murl).hostname;
    return TRUSTED_DOMAINS.some((d) => host === d || host.endsWith("." + d));
  } catch (e) {
    return false;
  }
}

function pickBest(query, candidates) {
  const qTokens = tokens(query);
  const minOverlap = Math.max(1, Math.ceil(qTokens.length * 0.4));
  const scored = candidates
    .map((c) => ({ ...c, score: scoreCandidate(qTokens, c) }))
    .filter((c) => c.score >= minOverlap);
  if (scored.length === 0) return null;
  scored.sort((a, b) => {
    const ta = isTrusted(a.murl) ? 1 : 0;
    const tb = isTrusted(b.murl) ? 1 : 0;
    if (ta !== tb) return tb - ta;
    return b.score - a.score;
  });
  return scored[0];
}

const EXE_PATH = "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

async function bingImageSearch(query) {
  // A fresh BROWSER PROCESS per query, not just a fresh page/tab: reusing
  // one browser across sequential searches got flagged after roughly a
  // dozen queries (Bing started returning a same-every-time "trending
  // images" carousel -- totally unrelated to the query -- instead of real
  // results, still as a normal 200 response). A brand new process each
  // time reliably avoided it in testing, even with no delay between runs.
  const browser = await puppeteer.launch({
    executablePath: EXE_PATH,
    headless: "new",
    args: ["--disable-gpu"],
  });
  try {
    const page = await browser.newPage();
    await page.setUserAgent(UA);
    const q = encodeURIComponent(query);
    await page.goto(`https://www.bing.com/images/search?q=${q}&form=HDRSC2`, {
      waitUntil: "networkidle2",
      timeout: 25000,
    });
    try {
      await page.waitForSelector("a.iusc", { timeout: 8000 });
    } catch (e) {
      return [];
    }
    await new Promise((r) => setTimeout(r, 400));
    return await page.evaluate(() => {
      const out = [];
      document.querySelectorAll("a.iusc").forEach((a) => {
        const m = a.getAttribute("m");
        if (!m) return;
        try {
          const data = JSON.parse(m);
          if (data.murl) out.push({ murl: data.murl, purl: data.purl, t: data.t });
        } catch (e) {}
      });
      return out.slice(0, 15);
    });
  } finally {
    await browser.close();
  }
}

async function searchProduct(name) {
  const q1 = cleanQuery(name);
  const c1 = await bingImageSearch(q1);
  let best = pickBest(q1, c1);
  let queryUsed = q1;
  let allCandidates = c1;

  if (!best) {
    const q2 = shortQuery(name);
    if (q2 !== q1) {
      const c2 = await bingImageSearch(q2);
      const best2 = pickBest(q2, c2);
      if (best2) {
        best = best2;
        queryUsed = q2;
        allCandidates = c2;
      } else if (c2.length) {
        allCandidates = c1.concat(c2);
      }
    }
  }

  return { query_used: queryUsed, chosen: best || null, candidates: allCandidates };
}

(async () => {
  const products = JSON.parse(fs.readFileSync(IN_PATH, "utf-8"));
  const slice = products.slice(START, END);

  let out = {};
  if (fs.existsSync(OUT_PATH)) {
    out = JSON.parse(fs.readFileSync(OUT_PATH, "utf-8"));
  }

  for (const p of slice) {
    try {
      const result = await searchProduct(p.name);
      out[p.code] = { name: p.name, ...result };
      console.log(`${p.code}: ${result.chosen ? "OK (" + result.chosen.score + ") " + result.chosen.murl : "NO MATCH"}`);
    } catch (e) {
      out[p.code] = { name: p.name, error: String(e) };
      console.log(`${p.code}: ERROR ${e}`);
    }
    fs.writeFileSync(OUT_PATH, JSON.stringify(out, null, 2), "utf-8");
    await new Promise((r) => setTimeout(r, 300));
  }

  console.log("DONE", slice.length, "products");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
