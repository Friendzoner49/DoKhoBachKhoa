// Reads the already-published public price list -- the bot never
// touches the shop's real database (see CLAUDE.md section 6: bot <->
// app data contract).
export async function fetchCatalog(env) {
  const res = await fetch(env.CATALOG_URL, {
    cf: { cacheTtl: 300, cacheEverything: true },
  });
  if (!res.ok) {
    throw new Error(`Catalog fetch failed: HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.items || [];
}

export function findByCode(items, code) {
  return items.find((i) => i.code === code);
}
