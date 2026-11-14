import { expect, type Page, type Request, test } from "@playwright/test";

// The layers' counters (P20, task 174). In production, 10 s after load, four of the six layers
// read 0: the flow played one layer after another in a loop that started over from 0, and the
// server sent every counter at 0. Now the server sends the figures of platform.json, and the first
// time the figure comes into view all six layers count up together and land on them within 2 s.
// `figure.platform[data-state]` is the count's phase (still, idle, counting, done); a
// MutationObserver installed by an init script, before the page's own scripts run, logs each
// state, so one that lasts less than a poll still shows up.

declare global {
  interface Window {
    __platformLog?: { states: string[] };
  }
}

// Runs in the page (stringified by Playwright), not in this test's own scope.
function installPlatformLogger(): void {
  const log: { states: string[] } = { states: [] };
  window.__platformLog = log;

  const record = (value: string | null) => {
    if (value !== null && log.states[log.states.length - 1] !== value) log.states.push(value);
  };

  const watch = (figure: Element) => {
    record(figure.getAttribute("data-state"));
    new MutationObserver((mutations) => {
      // One batch can hold several changes: each change's new value is the next change's
      // oldValue (the live value for the last), so a state shorter than a batch is still logged.
      mutations.forEach((_, i) => {
        const later = mutations[i + 1];
        record(later ? later.oldValue : figure.getAttribute("data-state"));
      });
    }).observe(figure, { attributes: true, attributeOldValue: true, attributeFilter: ["data-state"] });
  };

  const existing = document.querySelector("figure.platform");
  if (existing) {
    watch(existing);
    return;
  }
  const bootstrap = new MutationObserver(() => {
    const figure = document.querySelector("figure.platform");
    if (figure) {
      bootstrap.disconnect();
      watch(figure);
    }
  });
  // `document`, not `document.documentElement`: an init script runs before the
  // page has a document element at all, so observing that would throw.
  bootstrap.observe(document, { childList: true, subtree: true });
}

interface PlatformLayerRecord {
  layer: string;
  files: number;
  rows: number | null;
  bytes: number;
  seconds: number;
}

interface PlatformJson {
  title: string;
  subtitle: string;
  layers: PlatformLayerRecord[];
  raw_sources: { source_id: string; files: number; bytes: number }[];
}

// What a counter must read: the layer's field as the page prints it.
function expected(platform: PlatformJson, key: string): { text: string; value: number } {
  const [layerName, field] = key.split(".");
  const layer = platform.layers.find((l) => l.layer === layerName);
  if (!layer) throw new Error(`platform.json has no layer "${layerName}" for data-counter="${key}"`);
  const value = (layer as unknown as Record<string, number>)[field];
  return { text: field === "seconds" ? value.toFixed(1) : value.toLocaleString("en-US"), value };
}

const counters = (page: Page) =>
  page.locator("[data-counter]").evaluateAll((cells) =>
    cells.map((cell) => ({ key: cell.getAttribute("data-counter")!, text: (cell.textContent ?? "").trim() })),
  );

async function platformJson(page: Page): Promise<PlatformJson> {
  return (await (await page.request.get("/data/platform.json")).json()) as PlatformJson;
}

// Every counter reads its figure, and none reads 0 where the figure is not 0.
function expectFinal(platform: PlatformJson, read: { key: string; text: string }[], when: string) {
  expect(read.length, when).toBeGreaterThan(20);
  for (const { key, text } of read) {
    const want = expected(platform, key);
    if (want.value !== 0) expect(Number(text.replace(/,/g, "")), `${when}: ${key} reads 0`).not.toBe(0);
    expect(text, `${when}: ${key}`).toBe(want.text);
  }
}

test("the server sends every counter at platform.json's figure", async ({ page }) => {
  const platform = await platformJson(page);
  const html = await (await page.request.get("/engineering")).text();
  const read = [...html.matchAll(/data-counter="([^"]+)"[^>]*>([^<]*)</g)].map((m) => ({ key: m[1], text: m[2].trim() }));
  expectFinal(platform, read, "server HTML");
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });
  test("the counters read platform.json", async ({ page }) => {
    const platform = await platformJson(page);
    await page.goto("/engineering");
    expectFinal(platform, await counters(page), "no JS");
  });
});

test("2 s after load no counter reads 0, in view or not, and all read platform.json", async ({ page }) => {
  const platform = await platformJson(page);
  await page.goto("/engineering");
  await page.waitForTimeout(2_000);
  expectFinal(platform, await counters(page), "2 s after load, not scrolled");
  await page.locator("figure.platform").scrollIntoViewIfNeeded();
  await page.waitForTimeout(2_000);
  expectFinal(platform, await counters(page), "2 s after coming into view");
});

test("in view, the six layers count up together once and land on platform.json within 2 s", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  const requests: Request[] = [];
  page.on("requestfinished", (r) => requests.push(r));

  await page.addInitScript(installPlatformLogger);
  await page.goto("/engineering");
  const figure = page.locator("figure.platform");
  await figure.scrollIntoViewIfNeeded();
  await expect(figure).toHaveAttribute("data-state", "counting");
  // All at once: while it counts, every layer is lit.
  const phases = await page.locator(".platform-layer").evaluateAll((els) => els.map((e) => e.getAttribute("data-phase")));
  expect(phases).toEqual(Array(phases.length).fill("active"));
  await expect(figure).toHaveAttribute("data-state", "done", { timeout: 2_000 });
  const platform = await platformJson(page);
  expectFinal(platform, await counters(page), "done");
  // Once: it does not start over.
  await page.waitForTimeout(1_500);
  expect((await page.evaluate(() => window.__platformLog))?.states).toEqual(["idle", "counting", "done"]);

  // The H1 and the line under it are the title and subtitle the script printed (task 46).
  await expect(page.locator("h1")).toHaveText(platform.title);
  await expect(page.locator("[data-subtitle]")).toHaveText(platform.subtitle);

  await page.waitForLoadState("networkidle");
  let transferred = 0;
  for (const r of requests) {
    const sizes = await r.sizes();
    transferred += sizes.responseBodySize + sizes.responseHeadersSize;
  }
  console.log(`/engineering: ${transferred} bytes transferred`);
  expect(transferred).toBeLessThan(400_000);

  expect(errors).toEqual([]);
});

test.describe("prefers-reduced-motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("never counts: still, with platform.json's figures", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));

    await page.addInitScript(installPlatformLogger);
    await page.goto("/engineering");
    const figure = page.locator("figure.platform");
    await expect(figure).toHaveAttribute("data-state", "still");
    await figure.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    const log = await page.evaluate(() => window.__platformLog);
    expect(log?.states ?? []).not.toContain("counting");
    expect(log?.states.at(-1)).toBe("still");
    expectFinal(await platformJson(page), await counters(page), "reduced motion");

    expect(errors).toEqual([]);
  });
});

test("the logger keeps a state that lasted less than one mutation batch", async ({ page }) => {
  await page.setContent('<figure class="platform" data-state="idle"></figure>');
  await page.evaluate(installPlatformLogger);

  const states = await page.evaluate(async () => {
    const figure = document.querySelector("figure.platform") as Element;
    // Two changes in one task land in the same MutationObserver batch.
    figure.setAttribute("data-state", "counting");
    figure.setAttribute("data-state", "done");
    await new Promise((resolve) => setTimeout(resolve, 0));
    return window.__platformLog?.states;
  });

  expect(states).toEqual(["idle", "counting", "done"]);
});

test("the raw bytes line names the body-pose share, with the figures platform.json holds", async ({
  page,
}) => {
  const platform = (await (await page.request.get("/data/platform.json")).json()) as PlatformJson;
  const pose = platform.raw_sources.find((s) => s.source_id === "opendata-bodypose");
  expect(pose, "platform.json has no opendata-bodypose in raw_sources").toBeTruthy();
  const raw = platform.layers.find((l) => l.layer === "raw");
  const others = raw!.bytes - pose!.bytes;
  const n = (v: number) => v.toLocaleString("en-US");
  await page.goto("/engineering");
  const line = page.locator("[data-pose-share]");
  await expect(line).toHaveText(
    `Of the ${n(raw!.bytes)} raw bytes, ${n(pose!.bytes)} come from the ${pose!.files} ` +
      `body-pose zip${pose!.files === 1 ? "" : "s"} of ` +
      `opendata-bodypose (the body pose on /tracking/pose); the other sources account for ${n(others)}.`,
  );
  await expect(line.getByRole("link", { name: "/tracking/pose" })).toHaveAttribute("href", "/tracking/pose");
});

test("the home page links to /engineering and /engineering/quality", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "How this was built" })).toHaveAttribute(
    "href",
    "/engineering",
  );
  await expect(page.getByRole("link", { name: "Data quality" })).toHaveAttribute("href", "/engineering/quality");
});

test("the stack strip, the ingest counters and the sources block print what the JSON holds", async ({
  page,
}) => {
  const platform = (await (await page.request.get("/data/platform.json")).json()) as PlatformJson & {
    run: { versions: Record<string, string> };
    layers: { layer: string; downloaded?: number; verified?: number; bytes_read?: number }[];
  };
  const league = (await (await page.request.get("/data/euroleague/league.json")).json()) as {
    hex: { k: number };
    seasons: { season: string; games_played: number; cutoff: string }[];
  };
  await page.goto("/engineering");

  for (const [tool, version] of Object.entries(platform.run.versions)) {
    await expect(page.locator(`[data-stack] [data-tool="${tool}"]`)).toHaveText(`${tool} ${version}`);
  }

  const raw = platform.layers.find((l) => l.layer === "raw") as unknown as Record<string, number>;
  for (const field of ["downloaded", "verified", "bytes_read"] as const) {
    await expect(page.locator(`[data-counter="raw.${field}"]`)).toHaveText(
      raw[field].toLocaleString("en-US"),
    );
  }

  for (const src of platform.raw_sources) {
    const card = page.locator(`[data-source="${src.source_id}"]`);
    await expect(card.locator('[data-field="files"]')).toHaveText(String(src.files));
    await expect(card.locator('[data-field="bytes"]')).toHaveText(src.bytes.toLocaleString("en-US"));
    await expect(card.locator("[data-counts-in-out]")).toHaveText("yes");
  }
  const el = page.locator('[data-source="euroleague"]');
  for (const s of league.seasons) {
    const row = el.locator(`[data-season="${s.season}"]`);
    await expect(row.locator('[data-field="games"]')).toHaveText(String(s.games_played));
    await expect(row.locator('[data-field="cutoff"]')).toHaveText(s.cutoff);
  }
  await expect(el.locator('[data-field="k"]')).toHaveText(String(league.hex.k));
  await expect(el.locator("[data-counts-in-out]")).toHaveText(/^no/);

  // The title still counts SkillCorner only: EuroLeague is not in "out".
  await expect(page.locator("h1")).toHaveText("3.6 GB in, 9.6 MB out");
});

// Until P20 the repository was private and no route could link to it; P20 opens it, and the
// footer of every route links to that one repository and to no other address under the account.
test("every route links to the public repository from its footer, and to no other repository", async ({ page }) => {
  const routes = ["/", "/tracking", "/engineering", "/tracking/runs", "/engineering/quality", "/warehouse", "/tracking/replay", "/tracking/pose", "/learn", "/sql", "/euroleague", "/engineering/bulletin", "/engineering/history", "/about"];
  for (const route of routes) {
    await page.goto(route);
    const hrefs = await page.locator("a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
    const account = hrefs.filter((h) => h.includes("github.com/javiersr1996"));
    expect(account.length, route).toBeGreaterThan(0);
    expect(new Set(account), route).toEqual(new Set(["https://github.com/javiersr1996/pitch-and-parquet"]));
    await expect(page.locator("footer.site-footer").getByRole("link", { name: "Code on GitHub, MIT license" }), route).toHaveAttribute(
      "href",
      "https://github.com/javiersr1996/pitch-and-parquet",
    );
  }
});

test("the page does not claim a CI run", async ({ page }) => {
  await page.goto("/engineering");
  await expect(page.locator("main")).not.toContainText(/on every CI run|\(private repository\)|ci\.yml|CI run|GitHub Actions/i);
});

test("the guarantees and the Postgres block print what platform.json and warehouse_pg.json hold", async ({
  page,
}) => {
  const platform = (await (await page.request.get("/data/platform.json")).json()) as {
    guarantees: {
      dbt: { total: number; generic: number; by_kind: Record<string, number>; singular: string[] };
      contracts: { files: number; names: string[] };
      checks: { count: number; commands: string[] };
    };
  };
  const pg = (await (await page.request.get("/data/warehouse_pg.json")).json()) as {
    measured_at: string;
    source: { version: string; where: string; where_id: string };
    database_bytes: number;
    tables: { table: string; rows: number }[];
  };
  const g = platform.guarantees;
  await page.goto("/engineering");

  const field = (name: string) => page.locator(`[data-guarantees] [data-field="${name}"]`);
  await expect(field("dbt.total")).toHaveText(String(g.dbt.total));
  await expect(field("dbt.generic")).toHaveText(String(g.dbt.generic));
  await expect(field("dbt.singular")).toHaveText(String(g.dbt.singular.length));
  expect(g.dbt.generic + g.dbt.singular.length).toBe(g.dbt.total);
  for (const [kind, count] of Object.entries(g.dbt.by_kind)) {
    await expect(page.locator('[data-guarantee="dbt"] p')).toContainText(`${count} ${kind}`);
  }
  await expect(field("contracts.files")).toHaveText(String(g.contracts.files));
  await expect(field("checks.count")).toHaveText(String(g.checks.count));
  for (const [list, items] of [
    ["dbt.singular", g.dbt.singular],
    ["contracts.names", g.contracts.names],
    ["checks.commands", g.checks.commands],
  ] as const) {
    await expect(page.locator(`[data-list="${list}"] li`)).toHaveText([...items]);
  }
  expect(g.contracts.names).toHaveLength(g.contracts.files);
  expect(g.checks.commands).toHaveLength(g.checks.count);

  const n = (v: number) => v.toLocaleString("en-US");
  for (const t of pg.tables) {
    await expect(
      page.locator(`[data-pg-table="${t.table}"] [data-field="rows"]`),
    ).toHaveText(n(t.rows));
  }
  await expect(page.locator('[data-pg] [data-field="bytes"]')).toHaveText(n(pg.database_bytes));
  await expect(page.locator('[data-pg] [data-field="where"]')).toHaveText(pg.source.where);
  await expect(page.locator('[data-tool="postgres"]')).toHaveText(`Postgres ${pg.source.version}`);
  // The page says Neon only when the snapshot was measured there.
  if (pg.source.where_id !== "neon") {
    await expect(page.locator("main")).not.toContainText(/on Neon/);
  }

  await expect(page.locator("h1")).toHaveText("3.6 GB in, 9.6 MB out");
});

test("the guarantee cards do not overflow a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/engineering");
  for (const sel of ["[data-guarantees]", "[data-pg]"]) {
    const box = await page.locator(sel).boundingBox();
    expect(box!.x + box!.width, sel).toBeLessThanOrEqual(390);
  }
  const wide = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(wide).toBeLessThanOrEqual(390);
});
