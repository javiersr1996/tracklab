// Lists the pages of the last `next build` whose HTML has no <meta name="description"> or no
// og:image (P19, task 150). Exit 1 if any: `npm run build && node scripts/check-meta.mjs`.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";

const ROOT = join(process.cwd(), ".next", "server", "app");

function* htmlFiles(dir) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) yield* htmlFiles(p);
    else if (e.name.endsWith(".html")) yield p;
  }
}

const missing = [];
let count = 0;
for (const file of htmlFiles(ROOT)) {
  const route = "/" + relative(ROOT, file).split(sep).join("/").replace(/(^|\/)index\.html$|\.html$/, "");
  if (route.startsWith("/_")) continue; // _not-found, _global-error
  count++;
  const html = readFileSync(file, "utf8");
  const lacks = [];
  if (!/<meta name="description" content="[^"]+"/.test(html)) lacks.push("description");
  if (!/<meta property="og:image" content="[^"]+"/.test(html)) lacks.push("og:image");
  if (lacks.length) missing.push(`${route}: ${lacks.join(", ")}`);
}
console.log(`${count} pages, ${missing.length} without description or og:image`);
for (const m of missing) console.log("  " + m);
process.exit(missing.length ? 1 : 0);
