import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type Page, type Request, test } from "@playwright/test";

// Task 137: /warehouse/scouting against `scouting.json`, which `tracklab publish scouting`
// computes in plain Python from the same Parquet files the page reads (DuckDB-WASM in the
// browser): two paths, so the numbers on the page are never compared with themselves. The
// expected values are read from the JSON on disk, never typed here and never taken from the DOM,
// except where a test says so (the player with two rows in (c), whose JSON entry does not exist).
// The JSON rounds values to 4 decimals and percentiles to 1.

interface Metric {
  id: string;
}
interface Key {
  player_id: number;
  team_id: number;
  position_group?: string;
}
interface Probe extends Key {
  in_pool: boolean;
  values?: Record<string, [number | null, number | null]>;
}
interface Pool {
  group: string | null;
  rows: number;
  players: number;
  sample_total: number;
  n: number[];
}
interface Table {
  table: string;
  sport: "football" | "basketball";
  metrics: Metric[];
  pools: Pool[];
  probes: Probe[];
}
interface Scouting {
  default_pairs: Record<"football" | "basketball", [Key, Key]>;
  aliases: { player_id: number; canonical_player_id: number }[];
  tables: Table[];
}

const SCOUTING = JSON.parse(readFileSync(path.join(process.cwd(), "public", "data", "scouting.json"), "utf-8")) as Scouting;
const tablesOf = (sport: string) => SCOUTING.tables.filter((t) => t.sport === sport);
const keyText = (k: Key) => [k.player_id, k.team_id, ...(k.position_group ? [k.position_group] : [])].join("-");
const poolOf = (t: Table, k: Key) => t.pools.find((p) => p.group === (k.position_group ?? null))!;
const probeOf = (t: Table, k: Key) => t.probes.find((p) => keyText(p) === keyText(k))!;

const VALUE_TOLERANCE = 6e-5; // the JSON's 4 decimals, rounded
const PCTL_TOLERANCE = 1e-4;

const scout = (page: Page) => page.locator("div.scout");
const LOAD_TIMEOUT = 150_000;

// Press "Load the table" and wait for the table's query and the comparison's.
async function load(page: Page, table: string) {
  await page.getByRole("button", { name: "Load the table" }).click();
  await waitLoaded(page, table);
}

async function waitLoaded(page: Page, table: string) {
  const s = scout(page);
  await expect(s).toHaveAttribute("data-loaded", new RegExp(`(^| )${table}( |$)`), { timeout: LOAD_TIMEOUT });
  await expect(s).toHaveAttribute("data-compared", /\S/, { timeout: LOAD_TIMEOUT });
  await expect(s).toHaveAttribute("data-query", "done", { timeout: LOAD_TIMEOUT });
  await expect(s).not.toHaveAttribute("data-error", /.*/);
}

async function chooseTable(page: Page, table: string) {
  await page.locator(`[data-table-button="${table}"]`).click();
  await waitLoaded(page, table);
  await expect(scout(page)).toHaveAttribute("data-table", table);
}

interface DomCell {
  value: string | null;
  pctl: string | null;
}
interface DomPool {
  pool: string;
  attrs: { rows: number; players: number; sample: number };
  headN: number[];
  // Counted from the rows themselves, not from the attributes the page prints on the head.
  rows: number;
  players: number;
  sample: number;
  n: number[];
  cells: Record<string, Record<string, DomCell>>;
}

// The table on show, per pool: the head's figures, the same figures counted from the rows, and
// every cell's value and percentile by row key and metric.
function readTable(page: Page, metricIds: string[]): Promise<DomPool[]> {
  return page.evaluate((ids) => {
    return Array.from(document.querySelectorAll("table.scout-table tbody")).map((tb) => {
      const body = tb as HTMLElement;
      const rows = Array.from(tb.querySelectorAll("tr[data-key]")) as HTMLElement[];
      const cells: Record<string, Record<string, { value: string | null; pctl: string | null }>> = {};
      for (const r of rows) {
        cells[r.dataset.key!] = {};
        for (const c of Array.from(r.querySelectorAll("td.scout-cell")) as HTMLElement[]) {
          cells[r.dataset.key!][c.dataset.metric!] = { value: c.getAttribute("data-value"), pctl: c.getAttribute("data-pctl") };
        }
      }
      return {
        pool: body.dataset.pool!,
        attrs: { rows: Number(body.dataset.poolRows), players: Number(body.dataset.poolPlayers), sample: Number(body.dataset.poolSample) },
        headN: Array.from(tb.querySelectorAll("tr.scout-pool td")).map((td) => Number((td as HTMLElement).dataset.poolN)),
        rows: rows.length,
        players: new Set(rows.map((r) => r.dataset.key!.split("-")[0])).size,
        sample: rows.reduce((sum, r) => sum + Number(r.querySelector('td[data-col="sample"]')!.textContent), 0),
        n: ids.map((id) => rows.filter((r) => r.querySelector(`td[data-metric="${id}"]`)?.getAttribute("data-value") != null).length),
        cells,
      };
    });
  }, metricIds);
}

function near(got: string | null, want: number | null, tolerance: number, what: string) {
  if (want === null) return expect(got, what).toBeNull();
  expect(got, what).not.toBeNull();
  expect(Math.abs(Number(got) - want), `${what}: page ${got}, JSON ${want}`).toBeLessThanOrEqual(tolerance);
}

// (b) The pools of a loaded table and its probe players, against the JSON.
async function expectTable(page: Page, t: Table) {
  const dom = await readTable(page, t.metrics.map((m) => m.id));
  expect(dom.map((d) => d.pool), `${t.table} pools`).toEqual(t.pools.map((p) => p.group ?? "league"));
  for (const [i, p] of t.pools.entries()) {
    const d = dom[i];
    const what = `${t.table} ${p.group ?? "league"}`;
    expect(d.rows, `${what} rows`).toBe(p.rows);
    expect(d.players, `${what} players`).toBe(p.players);
    expect(d.sample, `${what} sample (matches, performances or games)`).toBe(p.sample_total);
    expect(d.n, `${what} n per metric, counted from the rows`).toEqual(p.n);
    expect(d.attrs, `${what} head`).toEqual({ rows: p.rows, players: p.players, sample: p.sample_total });
    // The head prints `n` only where a metric's pool is smaller than the group's.
    expect(d.headN, `${what} head n`).toEqual(p.n);
  }
  for (const probe of t.probes) {
    expect(probe.in_pool, `${t.table} probe ${keyText(probe)} is in the pool`).toBe(true);
    const group = dom.find((d) => d.pool === (probe.position_group ?? "league"))!;
    const row = group.cells[keyText(probe)];
    expect(row, `${t.table}: row ${keyText(probe)}`).toBeDefined();
    for (const m of t.metrics) {
      const [value, pctl] = probe.values![m.id];
      near(row[m.id].value, value, VALUE_TOLERANCE, `${t.table} ${keyText(probe)} ${m.id} value`);
      near(row[m.id].pctl, pctl, PCTL_TOLERANCE, `${t.table} ${keyText(probe)} ${m.id} percentile`);
    }
  }
}

// (c) The comparison on show against the probes of the sport's tables: `who` is the pair in the
// slots A and B.
async function expectCompare(page: Page, sport: "football" | "basketball", who: [Key, Key]) {
  const bars = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".scout-compare-table")).map((t) => ({
      table: (t as HTMLElement).dataset.table!,
      bars: Array.from(t.querySelectorAll(".scout-bar")).map((b) => {
        const e = b as HTMLElement;
        return {
          metric: e.closest("li")!.dataset.metric!,
          slot: e.dataset.slot!,
          below: e.hasAttribute("data-below"),
          value: e.getAttribute("data-value"),
          pctl: e.getAttribute("data-pctl"),
          n: e.getAttribute("data-n"),
        };
      }),
    })),
  );
  expect(bars.map((b) => b.table)).toEqual(tablesOf(sport).map((t) => t.table));
  for (const t of tablesOf(sport)) {
    const got = bars.find((b) => b.table === t.table)!.bars;
    expect(got.length, `${t.table} bars`).toBe(t.metrics.length * 2);
    for (const [s, slot] of (["a", "b"] as const).entries()) {
      const probe = probeOf(t, who[s]);
      expect(probe.in_pool).toBe(true);
      const pool = poolOf(t, who[s]);
      for (const [i, m] of t.metrics.entries()) {
        const bar = got.find((g) => g.metric === m.id && g.slot === slot)!;
        const what = `${t.table} ${slot.toUpperCase()} ${keyText(who[s])} ${m.id}`;
        expect(bar.below, `${what} below the floor`).toBe(false);
        near(bar.value, probe.values![m.id][0], VALUE_TOLERANCE, `${what} value`);
        near(bar.pctl, probe.values![m.id][1], PCTL_TOLERANCE, `${what} percentile`);
        expect(Number(bar.n), `${what} n`).toBe(pool.n[i]);
      }
    }
  }
}

const sports = ["football", "basketball"] as const;

test("nothing of the engine is fetched before 'Load the table', and the page is under 400.000 B", async ({ page }) => {
  const sizes: Promise<void>[] = [];
  const urls: string[] = [];
  let transferred = 0;
  page.on("requestfinished", (r: Request) => {
    urls.push(r.url());
    sizes.push(
      r.sizes().then((s) => {
        transferred += s.responseBodySize + s.responseHeadersSize;
      }),
    );
  });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/warehouse/scouting");
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  console.log(`/warehouse/scouting: ${transferred} bytes transferred before "Load the table"`);
  expect(transferred).toBeLessThan(400_000);
  await expect(scout(page)).toHaveAttribute("data-engine", "idle");
  const engine = (u: string) => /\/duckdb\/|\.parquet|\.wasm/.test(u);
  expect(urls.filter(engine), "engine or Parquet requests before the press").toEqual([]);
  await expect(page.getByRole("button", { name: "Load the table" })).toBeVisible();

  // The same filter sees them once the table is loaded.
  await load(page, tablesOf("football")[0].table);
  expect(urls.filter(engine).length, "requests after the press").toBeGreaterThan(0);
  expect(errors).toEqual([]);
});

test("the sitemap lists the page", async ({ page }) => {
  const xml = await (await page.request.get("/sitemap.xml")).text();
  expect(xml).toContain("/warehouse/scouting</loc>");
});

for (const sport of sports) {
  test(`${sport}: pools, probe players and the default pair's comparison equal scouting.json`, async ({ page }) => {
    test.setTimeout(600_000);
    const tables = tablesOf(sport);
    await page.goto(`/warehouse/scouting?sport=${sport}`);
    await load(page, tables[0].table);
    const [a, b] = SCOUTING.default_pairs[sport];
    await expect(scout(page)).toHaveAttribute("data-compared", `${keyText(a)} ${keyText(b)}`);
    await expectCompare(page, sport, [a, b]);
    for (const t of tables) {
      const started = Date.now();
      if (t !== tables[0]) await chooseTable(page, t.table);
      await expectTable(page, t);
      console.log(`${t.table}: pools, n and probes equal the JSON (${Date.now() - started} ms)`);
    }
    // Going through the tables did not change the comparison.
    await expectCompare(page, sport, [a, b]);
  });
}

test("a deep link restores a pair, swapped, in a new context", async ({ browser }) => {
  test.setTimeout(400_000);
  const links = [
    { sport: "football" as const, table: "fb_passing", group: "Midfield" },
    { sport: "basketball" as const, table: "bb_drives", group: null },
  ];
  for (const l of links) {
    const [a, b] = SCOUTING.default_pairs[l.sport];
    const context = await browser.newContext();
    const page = await context.newPage();
    const query = new URLSearchParams({ sport: l.sport, table: l.table, ...(l.group ? { group: l.group } : {}), a: keyText(b), b: keyText(a) });
    await page.goto(`/warehouse/scouting?${query}`);
    await expect(scout(page)).toHaveAttribute("data-a", keyText(b));
    await expect(scout(page)).toHaveAttribute("data-b", keyText(a));
    await expect(scout(page)).toHaveAttribute("data-table", l.table);
    await load(page, l.table);
    await expect(scout(page)).toHaveAttribute("data-compared", `${keyText(b)} ${keyText(a)}`);
    await expectCompare(page, l.sport, [b, a]);
    if (l.group) {
      // The group of the link: one pool, and the select says so.
      await expect(page.locator("#scout-group")).toHaveValue(l.group);
      expect((await readTable(page, [])).map((d) => d.pool)).toEqual([l.group]);
      await expect(page.locator(`tr[data-key="${keyText(b)}"]`)).toHaveAttribute("data-picked", "a");
      await expect(page.locator(`tr[data-key="${keyText(a)}"]`)).toHaveAttribute("data-picked", "b");
    }
    await context.close();
  }
});

// A football player with a row in two position groups: the comparison's key must carry the
// group. The JSON holds no probe for such a player, so the page's own table (checked against
// the JSON by the test above) is the reference: the same row, in the same pool, in both queries.
test("two rows of one player compare as two rows, each in its own pool", async ({ browser }) => {
  test.setTimeout(400_000);
  const t = tablesOf("football")[0];
  const table = await (await browser.newContext()).newPage();
  await table.goto("/warehouse/scouting?sport=football");
  await load(table, t.table);
  const dom = await readTable(table, t.metrics.map((m) => m.id));
  const byPlayer = new Map<string, { group: string; key: string }[]>();
  for (const d of dom) for (const key of Object.keys(d.cells)) byPlayer.set(key.split("-")[0], [...(byPlayer.get(key.split("-")[0]) ?? []), { group: d.pool, key }]);
  const twice = [...byPlayer.entries()].find(([, rows]) => rows.length >= 2);
  expect(twice, "a football player with two rows in the first table").toBeDefined();
  const [first, second] = twice![1];
  expect(first.group).not.toBe(second.group);

  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto(`/warehouse/scouting?${new URLSearchParams({ sport: "football", table: t.table, a: first.key, b: second.key })}`);
  await load(page, t.table);
  await expect(scout(page)).toHaveAttribute("data-compared", `${first.key} ${second.key}`);
  const bars = await page.evaluate(() =>
    Array.from(document.querySelectorAll('.scout-compare-table[data-current] .scout-bar')).map((b) => {
      const e = b as HTMLElement;
      return { metric: e.closest("li")!.dataset.metric!, slot: e.dataset.slot!, value: e.getAttribute("data-value"), pctl: e.getAttribute("data-pctl"), n: e.getAttribute("data-n") };
    }),
  );
  expect(bars.length).toBe(t.metrics.length * 2);
  for (const [slot, row] of [["a", first], ["b", second]] as const) {
    const pool = t.pools.find((p) => p.group === row.group)!;
    for (const [i, m] of t.metrics.entries()) {
      const bar = bars.find((x) => x.slot === slot && x.metric === m.id)!;
      const cell = dom.find((d) => d.pool === row.group)!.cells[row.key][m.id];
      near(bar.value, cell.value === null ? null : Number(cell.value), 1e-9, `${slot} ${row.key} ${m.id} value`);
      near(bar.pctl, cell.pctl === null ? null : Number(cell.pctl), 1e-9, `${slot} ${row.key} ${m.id} percentile`);
      expect(Number(bar.n), `${slot} ${row.key} ${m.id} n (the JSON's pool of ${row.group})`).toBe(pool.n[i]);
    }
  }
  await context.close();
  await table.context().close();
});

test("a text filter, the group and the U23 box change no visible percentile", async ({ page }) => {
  test.setTimeout(300_000);
  const t = tablesOf("football")[0];
  const [a] = SCOUTING.default_pairs.football;
  const ids = t.metrics.map((m) => m.id);
  await page.goto("/warehouse/scouting?sport=football");
  await load(page, t.table);
  const base = (await readTable(page, ids)).reduce<Record<string, Record<string, DomCell>>>((all, d) => ({ ...all, ...d.cells }), {});
  const total = Object.keys(base).length;
  expect(total).toBe(t.pools.reduce((sum, p) => sum + p.rows, 0));

  const shown = async () => (await readTable(page, ids)).reduce<Record<string, Record<string, DomCell>>>((all, d) => ({ ...all, ...d.cells }), {});
  const same = (view: Record<string, Record<string, DomCell>>, what: string) => {
    for (const [key, row] of Object.entries(view)) expect(row, `${what}: ${key}`).toEqual(base[key]);
  };
  const probe = probeOf(t, a);

  // The text filter: a team of the JSON's default pair.
  const team = (await page.locator(`tr[data-key="${keyText(a)}"] td.scout-team`).textContent())!;
  await page.locator("#scout-search").fill(team.split(" ")[0]);
  await expect.poll(async () => Object.keys(await shown()).length).toBeLessThan(total);
  const filtered = await shown();
  expect(Object.keys(filtered).length).toBeGreaterThan(0);
  same(filtered, "search");

  // The group, on top of the search is not needed: clear it, then the group alone.
  await page.locator("#scout-search").fill("");
  await expect.poll(async () => Object.keys(await shown()).length).toBe(total);
  await page.locator("#scout-group").selectOption(a.position_group!);
  await expect.poll(async () => Object.keys(await shown()).length).toBe(poolOf(t, a).rows);
  same(await shown(), "group");

  // U23 on the group: fewer rows, every percentile as before.
  const inGroup = poolOf(t, a).rows;
  await page.getByRole("checkbox").check();
  await expect.poll(async () => Object.keys(await shown()).length).toBeLessThan(inGroup);
  const young = await shown();
  expect(Object.keys(young)).toContain(keyText(a));
  same(young, "U23");
  for (const m of t.metrics) near(young[keyText(a)][m.id].pctl, probe.values![m.id][1], PCTL_TOLERANCE, `U23 ${m.id} percentile of the probe`);

  // And the basketball table's search.
  await page.goto("/warehouse/scouting?sport=basketball");
  const bb = tablesOf("basketball")[0];
  await load(page, bb.table);
  const bbIds = bb.metrics.map((m) => m.id);
  const bbBase = (await readTable(page, bbIds))[0].cells;
  await page.locator("#scout-search").fill("girona");
  await expect.poll(async () => Object.keys((await readTable(page, bbIds))[0].cells).length).toBeLessThan(Object.keys(bbBase).length);
  const bbShown = (await readTable(page, bbIds))[0].cells;
  expect(Object.keys(bbShown).length).toBeGreaterThan(0);
  for (const [key, row] of Object.entries(bbShown)) expect(row, key).toEqual(bbBase[key]);
});

test("alias rows are the JSON's alias ids, in the three basketball tables", async ({ page }) => {
  test.setTimeout(400_000);
  const canonical = new Map(SCOUTING.aliases.map((x) => [String(x.player_id), String(x.canonical_player_id)]));
  await page.goto("/warehouse/scouting?sport=basketball");
  await expect(page.locator("[data-aliases]")).toHaveAttribute("data-aliases", String(SCOUTING.aliases.length));
  const tables = tablesOf("basketball");
  await load(page, tables[0].table);
  for (const t of tables) {
    if (t !== tables[0]) await chooseTable(page, t.table);
    const rows = await page.evaluate(() =>
      Array.from(document.querySelectorAll("table.scout-table tr[data-key]")).map((r) => {
        const e = r as HTMLElement;
        return { key: e.dataset.key!, alias: e.getAttribute("data-alias"), tags: Array.from(r.querySelectorAll(".scout-tag"), (s) => s.textContent) };
      }),
    );
    const tagged = rows.filter((r) => r.alias !== null);
    expect(tagged.length, `${t.table}: rows tagged as an old id`).toBeGreaterThan(0);
    for (const r of rows) {
      const [id, team] = r.key.split("-");
      expect(r.alias, `${t.table} ${r.key}`).toBe(canonical.get(id) ?? null);
      expect(r.tags.includes("old id"), `${t.table} ${r.key} old id tag`).toBe(canonical.has(id));
      // The replacing id, when it has a row in the same team, says so.
      if (r.alias !== null && rows.some((o) => o.key === `${r.alias}-${team}`)) {
        expect(rows.find((o) => o.key === `${r.alias}-${team}`)!.tags, `${t.table} new id of ${r.key}`).toContain("new id");
      }
    }
  }
});

test.describe("at 390 px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("no sideways scroll and text of 16 px or more, before and after loading", async ({ page }) => {
    test.setTimeout(300_000);
    const check = async (what: string) => {
      const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(over, `${what}: wider than the window by`).toBeLessThanOrEqual(0);
      const small = await page.evaluate(() =>
        Array.from(document.querySelectorAll("main *"))
          .filter((el) => Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""))
          .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
          .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}: ${(el.textContent ?? "").slice(0, 30)}`),
      );
      expect(small, `${what}: text under 16 px`).toEqual([]);
    };
    await page.goto("/warehouse/scouting");
    await check("before loading");
    await load(page, tablesOf("football")[0].table);
    await check("football table and comparison");
    await page.locator('[data-show-button="value"]').click();
    await check("football, values");
    await page.locator('[data-sport-button="basketball"]').click();
    await waitLoaded(page, tablesOf("basketball")[0].table);
    await check("basketball table and comparison");
  });
});

test("with reduced motion the head panel's bars are at their final width at the first paint", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/warehouse/scouting");
  const t = tablesOf("football")[0];
  const probe = probeOf(t, SCOUTING.default_pairs.football[0]);
  const panel = page.locator('[data-head-panel="probe"]');
  await expect.poll(() => panel.getAttribute("data-grow")).toBe("still");
  const bars = await panel.locator(".scout-probe-bars li").evaluateAll((lis) =>
    lis.map((li) => {
      const fill = li.querySelector(".scout-fill") as HTMLElement;
      const track = li.querySelector(".scout-track") as HTMLElement;
      return {
        metric: (li as HTMLElement).dataset.metric!,
        ratio: fill.getBoundingClientRect().width / track.getBoundingClientRect().width,
        animation: getComputedStyle(fill).animationName,
        text: li.querySelector(".scout-probe-pct")!.textContent,
      };
    }),
  );
  expect(bars.map((b) => b.metric)).toEqual(t.metrics.map((m) => m.id));
  for (const b of bars) {
    const pctl = probe.values![b.metric][1]!;
    expect(b.animation, `${b.metric} animation`).toBe("none");
    expect(Math.abs(b.ratio * 100 - pctl), `${b.metric}: bar ${(b.ratio * 100).toFixed(2)} %, JSON ${pctl}`).toBeLessThan(0.5);
    expect(b.text, `${b.metric} figure`).toBe(pctl.toFixed(1));
  }
});
