import { readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { expect, type Page, test, type Worker } from "@playwright/test";

// Task 42: the DuckDB-WASM engine on /warehouse, driven by the state on `figure.warehouse`
// (`data-engine`, `data-query`, `data-run`) and checked against the network by paths the page
// does not use:
// - nothing of the engine (no `.wasm`, nothing under /duckdb/, no worker) before Run;
// - after Run, every request on this origin, and every request for a Parquet file a ranged
//   GET answered with 206 (or the HEAD that opens the file), never the whole file;
// - the page's bytes per query (counted in the worker from each XMLHttpRequest's body) equal
//   the Range headers Playwright saw, and the browser's Resource Timing inside the worker
//   equals that minus the part Chrome served from its HTTP cache (see `networkBytes`);
// - the page's engine bytes equal the worker's Resource Timing for the engine files;
// - rejected statements never load the engine, and the engine itself refuses a URL the text
//   check cannot see;
// - leaving the page by client-side navigation terminates the worker.
// What it measured goes to the test's output as warehouse_engine.json (uploaded by CI).

const DATA = "/data/warehouse/";
const isEngine = (url: string) => !url.startsWith("blob:") && (url.endsWith(".wasm") || new URL(url).pathname.startsWith("/duckdb/"));

interface Seen {
  url: string;
  method: string;
  range: string | null;
  status: Promise<number | null>;
  query: number;
}

// Requests are watched on the context, which also sees the ones the page's worker makes.
function watch(page: Page) {
  const state = { query: 0 };
  const seen: Seen[] = [];
  const errors: string[] = [];
  page.context().on("request", (r) =>
    seen.push({
      url: r.url(),
      method: r.method(),
      range: r.headers()["range"] ?? null,
      status: r.response().then((res) => res?.status() ?? null, () => null),
      query: state.query,
    }),
  );
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  return { state, seen, errors };
}

async function runQuery(page: Page, sql: string | null) {
  const figure = page.locator("figure.warehouse");
  const before = Number(await figure.getAttribute("data-run"));
  if (sql !== null) await page.getByLabel("SQL").fill(sql);
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure).toHaveAttribute("data-run", String(before + 1));
  await expect(figure).toHaveAttribute("data-query", /^(done|error)$/, { timeout: 120_000 });
  const attrs = await figure.evaluate((el) => ({ ...(el as HTMLElement).dataset }));
  const files = await page
    .locator("li[data-file]")
    .evaluateAll((lis) => lis.map((li) => ({ ...(li as HTMLElement).dataset })));
  return { attrs, files };
}

// Read in the worker (stringified by Playwright), then emptied, so each read is one query's.
const takeTiming = (worker: Worker) =>
  worker.evaluate(() => {
    const entries = performance.getEntriesByType("resource").map((e) => ({
      url: e.name,
      bytes: (e as PerformanceResourceTiming).encodedBodySize,
    }));
    performance.clearResourceTimings();
    return entries;
  });

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

const foreign = (seen: Seen[], origin: string) =>
  seen.filter((s) => !s.url.startsWith("blob:") && new URL(s.url).origin !== origin).map((s) => s.url);

function rangeOf(header: string | null): [number, number] | null {
  const m = header?.match(/^bytes=(\d+)-(\d+)$/);
  return m ? [Number(m[1]), Number(m[2])] : null;
}

// Chrome keeps the 206 responses it receives in its HTTP cache; when a later range of the same
// URL overlaps bytes it already holds, it serves those from the cache and fetches only the rest
// over the network, and Resource Timing counts only what came over the network. (Measured while
// writing this test: the read of bytes 0-16383 after the 1-byte GET that opens the file shows
// 16,383 bytes, and 16,384 once a passthrough route turns the cache off.) Replays every GET of the
// session in order and returns, per query, the bytes requested and the part already cached.
function networkBytes(seen: Seen[], query: number) {
  const held = new Map<string, Set<number>>();
  let requested = 0;
  let cached = 0;
  for (const s of seen) {
    const range = rangeOf(s.range);
    if (s.method !== "GET" || !s.url.includes(DATA) || !range) continue;
    const bytes = held.get(s.url) ?? new Set<number>();
    held.set(s.url, bytes);
    for (let b = range[0]; b <= range[1]; b++) {
      if (s.query === query) {
        requested += 1;
        if (bytes.has(b)) cached += 1;
      }
      bytes.add(b);
    }
  }
  return { requested, cached };
}

test("loads no engine until Run, then reads Parquet by range from this origin only", async ({ page, browser }, testInfo) => {
  test.setTimeout(240_000);
  const { state, seen, errors } = watch(page);

  await page.goto("/warehouse");
  await page.waitForLoadState("networkidle");
  // The network first: the state could say "idle" while the engine downloads.
  expect(seen.filter((s) => isEngine(s.url)).map((s) => s.url), "engine requested on load").toEqual([]);
  expect(page.workers()).toHaveLength(0);
  const figure = page.locator("figure.warehouse");
  await expect(figure).toHaveAttribute("data-engine", "idle");
  await expect(figure).toHaveAttribute("data-query", "idle");

  const origin = new URL(page.url()).origin;
  // The page's default (the percentile over the long fact), another table, the default again
  // once its blocks are in the engine, and every column of the widest table (the engine asks
  // twice for part of it: more bytes requested than the file has).
  const defaultSql = await page.getByLabel("SQL").inputValue();
  const queries = [
    defaultSql,
    "SELECT player_name, team_name, games_played FROM bb_shots WHERE NOT is_season_total ORDER BY player_id LIMIT 5",
    defaultSql,
    "SELECT * FROM bb_picks LIMIT 25",
  ];
  const measured = [];
  let engine: { page: number; timing: { url: string; bytes: number }[] } | null = null;
  for (const [i, sql] of queries.entries()) {
    state.query = i + 1;
    const { attrs, files } = await runQuery(page, sql);
    expect(attrs.error, attrs.error).toBeUndefined();
    expect(attrs).toMatchObject({ engine: "ready", query: "done" });
    expect(Number(attrs.rows)).toBeGreaterThan(0);

    // From this origin only (the worker is a blob: of this page), and Parquet only by range:
    // the HEAD that opens a file and ranged GETs answered with 206, never the whole file.
    const these = seen.filter((s) => s.query === i + 1);
    expect(foreign(these, origin), "requests to another origin").toEqual([]);
    for (const s of these.filter((s) => s.url.includes(DATA))) {
      expect([s.method, s.range], `not a range read: ${s.url}`).toEqual(
        s.method === "HEAD" ? ["HEAD", "bytes=0-"] : ["GET", expect.stringMatching(/^bytes=\d+-\d+$/)],
      );
      expect(await s.status, `${s.method} ${s.range}`).toBe(206);
    }

    const worker = page.workers()[0];
    const timing = await takeTiming(worker);
    if (engine === null) {
      const engineTiming = timing.filter((t) => isEngine(t.url));
      engine = { page: Number(attrs.bytesEngine), timing: engineTiming };
      expect(engineTiming.map((t) => new URL(t.url).pathname).sort()).toEqual([
        `/duckdb/${attrs.packageVersion}/duckdb-browser-eh.worker.js`,
        `/duckdb/${attrs.packageVersion}/duckdb-eh.wasm`,
        `/duckdb/ext/${attrs.duckdbVersion}/wasm_eh/parquet.duckdb_extension.wasm`,
      ]);
      expect(engine.page).toBe(sum(engineTiming.map((t) => t.bytes)));
      // Encoded bytes, so no more than the files the build copied (compression may make them less).
      const dir = path.join(path.dirname(testInfo.config.configFile!), "public");
      expect(engine.page).toBeLessThanOrEqual(sum(engineTiming.map((t) => statSync(path.join(dir, new URL(t.url).pathname)).size)));
    }

    const dataTiming = timing.filter((t) => t.url.includes(DATA));
    const ranged = networkBytes(seen, i + 1);
    const pageBytes = Number(attrs.bytesQuery);
    // The page's count is what the engine asked for, byte for byte.
    expect(pageBytes, "page bytes vs Range headers").toBe(ranged.requested);
    expect(Number(attrs.requests), "page requests vs worker Resource Timing").toBe(dataTiming.length);
    // The network's count is that minus what Chrome already held.
    expect(sum(dataTiming.map((t) => t.bytes)), "worker Resource Timing vs page bytes minus cached").toBe(pageBytes - ranged.cached);
    // Per file: the page's figures against the worker's entries for that file.
    // And each byte of a file counted once: no more than the file, no less than the network sent.
    for (const f of files) {
      const entries = dataTiming.filter((t) => t.url.endsWith(`${DATA}${f.file}`));
      expect(Number(f.requests), f.file).toBe(entries.length);
      expect(Number(f.bytesDistinct), f.file).toBeLessThanOrEqual(Number(f.fileBytes));
      expect(Number(f.bytesDistinct), f.file).toBeGreaterThanOrEqual(sum(entries.map((t) => t.bytes)));
    }
    expect(sum(files.map((f) => Number(f.bytes)))).toBe(pageBytes);
    measured.push({
      sql,
      rows: Number(attrs.rows),
      ms: Number(attrs.ms),
      page_bytes: pageBytes,
      page_requests: Number(attrs.requests),
      network_bytes: sum(dataTiming.map((t) => t.bytes)),
      cached_bytes: ranged.cached,
      page_distinct_bytes: Number(attrs.bytesDistinct),
      files: files.map((f) => ({
        file: f.file,
        bytes: Number(f.bytes),
        distinct_bytes: Number(f.bytesDistinct),
        requests: Number(f.requests),
        file_bytes: Number(f.fileBytes),
      })),
    });
  }

  expect(errors).toEqual([]);

  const report = {
    task: 42,
    written_by: "web/e2e/warehouse.spec.ts",
    date: new Date().toISOString(),
    browser: { name: browser.browserType().name(), version: browser.version() },
    platform: process.platform,
    ci: !!process.env.CI,
    server: process.env.BASE_URL ? "deployment" : "local next start",
    engine: { page_bytes: engine!.page, files: engine!.timing.map((t) => ({ path: new URL(t.url).pathname, encoded_bytes: t.bytes })) },
    queries: measured,
    engine_files_on_disk: Object.fromEntries(
      readdirSync(path.join(path.dirname(testInfo.config.configFile!), "public/duckdb"), { recursive: true, encoding: "utf8" })
        .map((f) => f.replaceAll("\\", "/"))
        .filter((f) => statSync(path.join(path.dirname(testInfo.config.configFile!), "public/duckdb", f)).isFile())
        .sort()
        .map((f) => [f, statSync(path.join(path.dirname(testInfo.config.configFile!), "public/duckdb", f)).size]),
    ),
  };
  writeFileSync(testInfo.outputPath("warehouse_engine.json"), JSON.stringify(report, null, 2) + "\n");
  console.log(`warehouse engine: ${JSON.stringify(report)}`);
});

test("rejects anything but a read before loading the engine, and the engine refuses other origins", async ({ page }) => {
  test.setTimeout(180_000);
  const { seen, errors } = watch(page);
  // Never reaches example.com; the request is still seen (and fails the test) if it is made.
  await page.route("https://example.com/**", (r) => r.abort());
  await page.goto("/warehouse");
  const figure = page.locator("figure.warehouse");

  for (const [sql, why] of [
    ["INSTALL httpfs", /Only SELECT/],
    ["ATTACH 'https://example.com/other.duckdb'", /Only SELECT/],
    ["SELECT * FROM read_csv('https://example.com/x.csv')", /No URLs/],
    ["SELECT 1; LOAD httpfs", /One statement/],
  ] as const) {
    const { attrs } = await runQuery(page, sql);
    expect(attrs, sql).toMatchObject({ engine: "idle", query: "error" });
    expect(attrs.error, sql).toMatch(why);
  }
  expect(seen.filter((s) => isEngine(s.url)).map((s) => s.url), "a rejected statement loaded the engine").toEqual([]);
  expect(page.workers()).toHaveLength(0);

  // A URL the text check cannot see, built inside the query: the engine's own lock refuses it.
  const { attrs } = await runQuery(page, "SELECT * FROM read_csv(concat('https', chr(58), '//example.com/x.csv'))");
  expect(attrs).toMatchObject({ engine: "ready", query: "error" });
  expect(attrs.error).toMatch(/disabled by configuration/);
  await expect(figure).toHaveAttribute("data-engine", "ready");

  expect(foreign(seen, new URL(page.url()).origin), "requests to another origin").toEqual([]);
  expect(errors).toEqual([]);
});

test("terminates the engine's worker when the page unmounts", async ({ page }) => {
  test.setTimeout(180_000);
  const { errors } = watch(page);
  await page.goto("/warehouse");
  const { attrs } = await runQuery(page, null);
  expect(attrs).toMatchObject({ engine: "ready", query: "done" });
  expect(page.workers()).toHaveLength(1);
  const closed = new Promise<void>((resolve) => page.workers()[0].once("close", () => resolve()));

  // A client-side navigation keeps this document (and its JS) alive: only the component's own
  // cleanup can end the worker, not a page load.
  await page.evaluate(() => ((window as unknown as { __sameDocument: boolean }).__sameDocument = true));
  await page.getByRole("link", { name: "Track Lab" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("h1")).toHaveText("Watch a possession, then ask it a question");
  expect(await page.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument)).toBe(true);

  await expect.poll(() => page.workers().length, { timeout: 10_000 }).toBe(0);
  await closed;
  expect(errors).toEqual([]);
});
