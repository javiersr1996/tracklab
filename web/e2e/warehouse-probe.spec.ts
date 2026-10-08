import { execSync } from "node:child_process";
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { type APIRequestContext, type Browser, expect, type Request, test } from "@playwright/test";

// Task 38: DuckDB-WASM, a few Parquet files and the server that hands them out, measured
// before any product code is written. The /probe route runs the queries and writes what
// the engine knows to data-* attributes; this spec adds what the network knows and
// writes both to pipeline/reports/warehouse_probe.json, one entry per platform and
// server, so no figure in the plan is typed by hand.
//
// The route, its Parquet files and the prebuild copy of the engine were deleted when task
// 38 closed; 35295fb is the last commit that has them (web/app/probe/Probe.tsx). From then
// on this spec skips, on the state of the server it runs against (/probe answers 404), not
// on a flag: pointed with BASE_URL at a deployment that still has the route (the Vercel
// preview of 0a1b203, the probe commit that was pushed), it measures again.

// The three ways /probe loads the engine (VARIANTS in app/probe/Probe.tsx at 35295fb).
const VARIANTS = ["self_defaults", "self_ranges", "jsdelivr_ranges"] as const;
type Variant = (typeof VARIANTS)[number];
// Same query over several layouts of one table: the results must not depend on layout.
const SAME_RESULT = [
  ["picks_rg1", "picks_rg64"],
  ["fact_rg1", "fact_rg10k", "fact_rg50k"],
];
const RANGED = "/data/probe/picks_rg64.parquet";
const ENGINE_FILES = [
  "duckdb-eh.wasm",
  "duckdb-browser-eh.worker.js",
  "duckdb-mvp.wasm",
  "duckdb-browser-mvp.worker.js",
];

interface Net {
  url: string;
  m: string | null;
  method: string;
  type: string;
  phase: "load" | "run";
  status: number | null;
  range: string | null;
  contentRange: string | null;
  contentType: string | null;
  contentEncoding: string | null;
  body: number | null;
  headers: number | null;
  failure: string | null;
}

interface Timing {
  context: "page" | "worker";
  url: string;
  m: string | null;
  type: string;
  transfer: number;
  encoded: number;
  decoded: number;
}

interface Row {
  target: string;
  query: string;
  rows: number;
  ms: number;
  resultSha: string;
  firstRow: unknown;
  stats: {
    totalFileReadsCold: number;
    totalFileReadsAhead: number;
    totalFileReadsCached: number;
    totalPageAccesses: number;
    totalPageLoads: number;
    blockSize: number;
    blocks: number[][];
  };
}

const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

function stripUrl(raw: string, origin: string): { url: string; m: string | null } {
  if (raw.startsWith("blob:") || raw.startsWith("data:")) return { url: raw.split(":")[0] + ":", m: null };
  const u = new URL(raw);
  // Same origin: the path only, so no host (local or preview) lands in the report.
  return { url: u.origin === origin ? u.pathname : `${u.origin}${u.pathname}`, m: u.searchParams.get("m") };
}

// The bytes a response carried: a 206 says which in Content-Range, a 200 to a GET is the
// whole file, a HEAD carries none.
function served(n: Net, size: number): [number, number] | null {
  if (n.method !== "GET") return null;
  if (n.status === 200) return [0, size];
  const match = n.contentRange?.match(/^bytes (\d+)-(\d+)\//);
  return n.status === 206 && match ? [Number(match[1]), Number(match[2]) + 1] : null;
}

// Where those bytes fall: before the first row group (the magic), inside each row group's
// column chunks, or after the last one (the footer and its length).
type Span = [number, number, number, string | null, string | null];
function areas(spans: Span[], ranges: [number, number][]) {
  const overlap = (lo: number, hi: number) => sum(ranges.map(([a, b]) => Math.max(0, Math.min(b, hi) - Math.max(a, lo))));
  const first = Math.min(...spans.map(([, start]) => start));
  const last = Math.max(...spans.map(([, , stop]) => stop));
  const byRowGroup = Object.fromEntries(
    spans.map(([id, start, stop]) => [id, overlap(start, stop)] as const).filter(([, bytes]) => bytes > 0),
  );
  return {
    bytes: sum(ranges.map(([a, b]) => b - a)),
    head_bytes: overlap(0, first),
    footer_bytes: overlap(last, Number.MAX_SAFE_INTEGER),
    row_groups_with_bytes_read: Object.keys(byRowGroup).map(Number),
    bytes_by_row_group: byRowGroup,
  };
}

// The filter of each filtered query in app/probe/Probe.tsx (at 35295fb), checked against
// the min and max that the footer stores for that column in each row group.
const FILTERS: Record<string, (min: string, max: string) => boolean> = {
  team: (min, max) => Number(min) <= 1331 && 1331 <= Number(max),
  metric_percentile: (min, max) => min <= "handler_ppp" && "handler_ppp" <= max,
};

async function headersOf(request: APIRequestContext, method: "GET" | "HEAD", range?: string) {
  const res = await request.fetch(RANGED, {
    method,
    headers: { "Accept-Encoding": "br, gzip", ...(range ? { Range: range } : {}) },
  });
  const h = res.headers();
  return {
    request: `${method} ${range ? `Range: ${range}` : "(no Range)"}, Accept-Encoding: br, gzip`,
    status: res.status(),
    "content-type": h["content-type"] ?? null,
    "content-encoding": h["content-encoding"] ?? null,
    "content-range": h["content-range"] ?? null,
    "content-length": h["content-length"] ?? null,
    "accept-ranges": h["accept-ranges"] ?? null,
    "cache-control": h["cache-control"] ?? null,
    etag: h["etag"] ?? null,
    "x-vercel-cache": h["x-vercel-cache"] ?? null,
    bodyBytes: method === "GET" ? (await res.body()).length : null,
  };
}

async function measure(browser: Browser, variant: Variant, use: { baseURL?: string; extraHTTPHeaders?: Record<string, string> }, sizes: Record<string, number>) {
  const context = await browser.newContext({ baseURL: use.baseURL, extraHTTPHeaders: use.extraHTTPHeaders });
  const page = await context.newPage();
  const origin = new URL(use.baseURL!).origin;
  let phase: Net["phase"] = "load";
  const phases = new Map<Request, Net["phase"]>();
  const pending: Promise<Net>[] = [];
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  context.on("request", (r) => phases.set(r, phase));
  const record = (r: Request, failure: string | null) =>
    pending.push(
      (async (): Promise<Net> => {
        const response = failure ? null : await r.response();
        const req = await r.allHeaders();
        const res = response ? await response.allHeaders() : {};
        const size = failure ? null : await r.sizes();
        return {
          ...stripUrl(r.url(), origin),
          method: r.method(),
          type: r.resourceType(),
          phase: phases.get(r) ?? "load",
          status: response?.status() ?? null,
          range: req["range"] ?? null,
          contentRange: res["content-range"] ?? null,
          contentType: res["content-type"] ?? null,
          contentEncoding: res["content-encoding"] ?? null,
          body: size?.responseBodySize ?? null,
          headers: size?.responseHeadersSize ?? null,
          failure,
        };
      })(),
    );
  context.on("requestfinished", (r) => record(r, null));
  context.on("requestfailed", (r) => record(r, r.failure()?.errorText ?? "failed"));

  await page.goto("/probe");
  await page.waitForLoadState("networkidle");
  const figure = page.locator("figure.probe");
  await expect(figure).toHaveAttribute("data-state", "idle");
  phase = "run";
  await page.locator(`button[data-run="${variant}"]`).click();
  await expect(figure).toHaveAttribute("data-state", /^(done|error)$/, { timeout: 240_000 });
  expect(await figure.getAttribute("data-error")).toBeNull();
  await expect(figure).toHaveAttribute("data-state", "done");

  const attrs = (await figure.evaluate((el) => ({ ...(el as HTMLElement).dataset }))) as Record<string, string>;
  const rows: Row[] = (
    await page.locator("tr[data-target]").evaluateAll((trs) => trs.map((tr) => ({ ...(tr as HTMLElement).dataset })))
  ).map((d) => ({
    target: d.target!,
    query: d.query!,
    rows: Number(d.rows),
    ms: Number(d.ms),
    resultSha: d.resultSha!,
    firstRow: JSON.parse(d.firstRow!),
    stats: JSON.parse(d.stats!),
  }));
  const spans = JSON.parse(attrs.spans) as Record<string, Span[]>;

  // Runs in the page and in each worker (stringified by Playwright).
  const readTiming = () =>
    performance.getEntriesByType("resource").map((e) => {
      const r = e as PerformanceResourceTiming;
      return { name: r.name, type: r.initiatorType, transfer: r.transferSize, encoded: r.encodedBodySize, decoded: r.decodedBodySize };
    });
  const timing: Timing[] = [];
  const workers = page.workers();
  const read: [Timing["context"], Awaited<ReturnType<typeof readTiming>>][] = [["page", await page.evaluate(readTiming)]];
  for (const w of workers) read.push(["worker", await w.evaluate(readTiming)]);
  for (const [where, entries] of read) {
    for (const t of entries) {
      timing.push({ context: where, ...stripUrl(t.name, origin), type: t.type, transfer: t.transfer, encoded: t.encoded, decoded: t.decoded });
    }
  }
  const net = await Promise.all(pending);
  await context.close();

  const engineRequests = net.filter((n) => /\.wasm$|\.worker\.js$/.test(n.url));
  const queries = rows.map((row) => {
    const m = `${row.target}.${row.query}`;
    const size = sizes[row.target];
    const seen = net.filter((n) => n.m === m);
    const ranges = seen.map((n) => served(n, size)).filter((r): r is [number, number] => r !== null);
    const blockSize = row.stats.blockSize;
    const engineBlocks = row.stats.blocks.filter(([, cold, ahead]) => cold + ahead > 0).map(([i]) => i);
    const engineRanges = engineBlocks.map((i): [number, number] => [i * blockSize, Math.min((i + 1) * blockSize, size)]);
    const inWorker = timing.filter((t) => t.m === m);
    const rgSpans = spans[row.target];
    const filter = FILTERS[row.query];
    return {
      file: row.target,
      query: row.query,
      file_bytes: size,
      row_groups_in_file: rgSpans.length,
      row_groups_matching_statistics: filter
        ? rgSpans.filter(([, , , min, max]) => min !== null && max !== null && filter(min, max)).map(([id]) => id)
        : null,
      rows: row.rows,
      ms: Math.round(row.ms * 10) / 10,
      first_row: row.firstRow,
      result_sha256: row.resultSha,
      engine: {
        source: "exportFileStatistics (duckdb-wasm file statistics), blocks with a cold or read-ahead read",
        reads_cold: row.stats.totalFileReadsCold,
        reads_ahead: row.stats.totalFileReadsAhead,
        reads_cached: row.stats.totalFileReadsCached,
        block_size: blockSize,
        blocks_read: engineBlocks.length,
        ...areas(rgSpans, engineRanges),
      },
      network: {
        source: "Playwright requestfinished events: request.sizes() and the Content-Range served",
        // Every request of one query has the same URL; a GET that Playwright reports with
        // no Content-Range cannot be placed in the file and its bytes stay out of `bytes`.
        unplaced_body_bytes: sum(seen.filter((n) => n.method === "GET" && served(n, size) === null).map((n) => n.body ?? 0)),
        requests: seen.length,
        methods: seen.map((n) => n.method),
        statuses: seen.map((n) => n.status),
        ranges_requested: seen.map((n) => n.range),
        content_ranges: seen.map((n) => n.contentRange),
        body_bytes: seen.map((n) => n.body),
        response_body_bytes: seen.length ? sum(seen.map((n) => n.body ?? 0)) : null,
        ...areas(rgSpans, ranges),
      },
      worker_resource_timing: {
        source: "PerformanceResourceTiming read inside the DuckDB worker",
        entries: inWorker.length,
        transfer_bytes: sum(inWorker.map((t) => t.transfer)),
        transfer_bytes_each: inWorker.map((t) => t.transfer),
        encoded_body_bytes_each: inWorker.map((t) => t.encoded),
        encoded_body_bytes: sum(inWorker.map((t) => t.encoded)),
      },
    };
  });

  return {
    attrs,
    rows,
    errors,
    result: {
      package_version: attrs.packageVersion,
      duckdb_version: attrs.duckdbVersion,
      bundle: stripUrl(attrs.bundle, origin).url,
      ms_instantiate: Math.round(Number(attrs.msInstantiate)),
      ms_load_parquet_extension: Math.round(Number(attrs.msExtension)),
      file_statistics_api: JSON.parse(attrs.statsShape),
      page_load: {
        requests: net.filter((n) => n.phase === "load").length,
        response_body_bytes: sum(net.filter((n) => n.phase === "load").map((n) => n.body ?? 0)),
      },
      engine_requests: engineRequests.map((n) => ({
        url: n.url,
        status: n.status,
        content_type: n.contentType,
        content_encoding: n.contentEncoding,
        response_body_bytes: n.body,
        response_header_bytes: n.headers,
      })),
      engine_resource_timing: timing
        .filter((t) => /\.wasm$|\.worker\.js$/.test(t.url))
        .map((t) => ({ context: t.context, url: t.url, transfer_bytes: t.transfer, encoded_body_bytes: t.encoded, decoded_body_bytes: t.decoded })),
      scripts_after_click: net
        .filter((n) => n.phase === "run" && n.type === "script" && n.url.startsWith("/_next/"))
        .map((n) => ({ url: n.url, response_body_bytes: n.body, content_encoding: n.contentEncoding })),
      origins_after_click: [...new Set(net.filter((n) => n.phase === "run").map((n) => (n.url.startsWith("/") ? "same origin" : new URL(n.url).origin)))],
      network_sees_worker_requests: net.some((n) => n.m !== null),
      workers: workers.length,
      worker_resource_timing_entries: timing.filter((t) => t.context === "worker").length,
      queries,
      console_errors: errors,
    },
  };
}

test("DuckDB-WASM probe: ranges, engine bytes and bytes per query", async ({ browser, request }, testInfo) => {
  test.setTimeout(420_000);
  const probe = await request.get("/probe");
  test.skip(
    probe.status() === 404,
    "/probe answers 404: the route was deleted when task 38 closed; the figures stay in pipeline/reports/warehouse_probe.json",
  );
  expect(probe.status()).toBe(200);
  expect(await probe.text()).toMatch(/<meta name="robots" content="noindex, nofollow"\s*\/?>/);

  const configDir = path.dirname(testInfo.config.configFile!);
  const pinned = JSON.parse(readFileSync(path.join(configDir, "package.json"), "utf8")).dependencies["@duckdb/duckdb-wasm"];
  const dist = path.join(configDir, "node_modules/@duckdb/duckdb-wasm/dist");
  const sizes: Record<string, number> = {};
  for (const [id, url] of [
    ["picks_rg1", "/data/probe/picks_rg1.parquet"],
    ["picks_rg64", RANGED],
    ["fact_rg1", "/data/probe/fact_rg1.parquet"],
    ["fact_rg10k", "/data/probe/fact_rg10k.parquet"],
    ["fact_rg50k", "/data/warehouse/fact.00ed21c4.parquet"],
  ]) {
    const head = await request.head(url);
    expect(head.status(), url).toBe(200);
    sizes[id] = Number(head.headers()["content-length"]);
  }

  // (a) What the server answers to a ranged GET for a .parquet.
  const ranged = [
    await headersOf(request, "GET", "bytes=-8"),
    await headersOf(request, "GET", "bytes=0-99"),
    await headersOf(request, "HEAD"),
  ];
  expect(ranged[0].status, "a suffix range on a .parquet must give 206 (decision 1)").toBe(206);
  expect(ranged[0].bodyBytes).toBe(8);

  const use = testInfo.project.use as { baseURL?: string; extraHTTPHeaders?: Record<string, string> };
  const byVariant: Record<string, unknown> = {};
  for (const variant of VARIANTS) {
    const { rows, errors, result } = await measure(browser, variant, use, sizes);
    expect(result.package_version).toBe(pinned);
    expect(errors).toEqual([]);
    expect(rows.length).toBe(9);
    for (const row of rows) expect(row.rows, `${row.target}.${row.query}`).toBeGreaterThan(0);
    for (const group of SAME_RESULT) {
      for (const query of new Set(rows.filter((r) => r.target === group[0]).map((r) => r.query))) {
        const shas = group.map((t) => rows.find((r) => r.target === t && r.query === query)!.resultSha);
        expect(new Set(shas).size, `${query} over ${group.join(", ")}`).toBe(1);
      }
    }
    if (variant.endsWith("_ranges")) {
      // The point of the Parquet layout: every query reads by range, none reads the file whole.
      for (const q of result.queries) {
        const gets = q.network.statuses.filter((_, i) => q.network.methods[i] === "GET");
        expect(gets, `${q.file}.${q.query}`).toContain(206);
        expect(gets, `${q.file}.${q.query}`).not.toContain(200);
      }
    }
    if (variant === "self_ranges") {
      // Engine and extension from this deployment: nothing fetched from anywhere else.
      expect(result.origins_after_click).toEqual(["same origin"]);
    }
    byVariant[variant] = result;
  }

  const sha = execSync("git rev-parse HEAD", { cwd: configDir }).toString().trim();
  const dirty = execSync("git status --porcelain", { cwd: configDir }).toString().trim() !== "";
  const server = process.env.BASE_URL ? "deployment" : "local next start";
  const key = `${process.platform}-${process.env.BASE_URL ? "deployment" : "local"}`;
  const run = {
    date: new Date().toISOString(),
    sha,
    tree_dirty: dirty,
    server,
    ci: !!process.env.CI,
    browser: { name: browser.browserType().name(), version: browser.version() },
    os: { platform: process.platform, release: os.release(), arch: process.arch, cpus: os.cpus().length, memory_bytes: os.totalmem() },
    node: process.version,
    // (a)
    parquet_ranged_get: { file: RANGED, file_bytes: sizes.picks_rg64, responses: ranged },
    // (b) to (e), once per way of loading the engine
    variants: byVariant,
  };

  const report = path.resolve(configDir, "../pipeline/reports/warehouse_probe.json");
  const previous = existsSync(report) ? JSON.parse(readFileSync(report, "utf8")) : { runs: {} };
  const runs = { ...previous.runs, [key]: run };
  const out = {
    task: 38,
    written_by: "web/e2e/warehouse-probe.spec.ts",
    engine: {
      package: "@duckdb/duckdb-wasm",
      pinned,
      files_in_package: Object.fromEntries(ENGINE_FILES.map((f) => [f, statSync(path.join(dist, f)).size])),
      // What the self-hosted variants put on the deployment (web/public/duckdb, written by
      // the probe's prebuild step), read from the local build.
      files_deployed: !existsSync(path.join(configDir, "public/duckdb")) ? null : Object.fromEntries(
        readdirSync(path.join(configDir, "public/duckdb"), { recursive: true, encoding: "utf8" })
          .map((f) => f.replaceAll("\\", "/"))
          .filter((f) => statSync(path.join(configDir, "public/duckdb", f)).isFile())
          .sort()
          .map((f) => [f, statSync(path.join(configDir, "public/duckdb", f)).size]),
      ),
    },
    pending: Object.keys(runs).some((k) => k.endsWith("-deployment"))
      ? []
      : [
          "No run against a Vercel deployment: VERCEL_AUTOMATION_BYPASS_SECRET is not set. " +
            "Run this spec with BASE_URL set to the preview of a commit that still has /probe, " +
            'and curl -sS -D - -o /dev/null -H "Range: bytes=-8" -H "x-vercel-protection-bypass: $VERCEL_AUTOMATION_BYPASS_SECRET" <preview>/data/warehouse/fact.00ed21c4.parquet',
        ],
    runs,
  };
  const text = JSON.stringify(out, null, 2) + "\n";
  mkdirSync(path.dirname(report), { recursive: true });
  writeFileSync(report, text);
  // The CI artifact uploads test-results/: the Linux run leaves its report there too.
  writeFileSync(testInfo.outputPath("warehouse_probe.json"), text);
  console.log(`warehouse probe: ${key} written to pipeline/reports/warehouse_probe.json`);
});
