import { expect, type Page, type Route, test } from "@playwright/test";

// Task 43: the console on /warehouse, driven by the state on `figure.warehouse` and checked
// against `warehouse_examples.json`, which `tracklab publish examples` computes from gold in
// Python (sorting and counting, no SQL): the engine's answer is compared with another path.
// The layout checks run at 390 and 1440 px.

interface Expected {
  params: { football_metric: string };
  examples: {
    id: string;
    table: string;
    columns: { name: string; decimals: number | null }[];
    rows: (string | number)[][];
  }[];
}

interface Manifest {
  tables: { table: string; row_groups: { rows: number; min: string | number | null; max: string | number | null }[] }[];
}

const figure = (page: Page) => page.locator("figure.warehouse");

async function finished(page: Page, before: number) {
  const f = figure(page);
  await expect(f).toHaveAttribute("data-run", String(before + 1));
  await expect(f).toHaveAttribute("data-query", /^(done|error)$/, { timeout: 120_000 });
  return f.evaluate((el) => ({ ...(el as HTMLElement).dataset }));
}

async function click(page: Page, selector: string) {
  const before = Number(await figure(page).getAttribute("data-run"));
  await page.locator(selector).click();
  return finished(page, before);
}

async function runSql(page: Page, sql: string) {
  await page.getByLabel("SQL").fill(sql);
  const before = Number(await figure(page).getAttribute("data-run"));
  await page.getByRole("button", { name: "Run", exact: true }).click();
  return finished(page, before);
}

// Cells of the result table as text: header names, then rows. The Parquet one only: the Postgres
// panel of task 45 has a table of its own, inside a section.
async function resultTable(page: Page) {
  const header = await page.locator("figure.warehouse > .table-scroll thead th").allTextContents();
  const rows = await page
    .locator("figure.warehouse > .table-scroll tbody tr")
    .evaluateAll((trs) => trs.map((tr) => Array.from(tr.querySelectorAll("td"), (td) => td.textContent ?? "")));
  return { header, rows };
}

// A rounded column is right to within half a unit of its last digit (the query rounds, the
// expected value does not).
function matches(actual: string, expected: string | number, decimals: number | null): boolean {
  if (typeof expected === "string") return actual === expected;
  const tolerance = decimals === null ? 0 : 0.5 * 10 ** -decimals + 1e-6;
  return Math.abs(Number(actual) - expected) <= tolerance;
}

test("every example runs and returns what gold gives, and the panel counts the data apart from the engine", async ({
  page,
}) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  const expected = (await (await page.request.get("/data/warehouse_examples.json")).json()) as Expected;
  const manifest = (await (await page.request.get("/data/warehouse.json")).json()) as Manifest;

  expect(expected.examples.length).toBeGreaterThanOrEqual(4);

  for (const example of expected.examples) {
    // A fresh page for each: the engine keeps what it read, so a second query on a file that
    // an earlier one touched can fetch nothing, and its line would not be there to check.
    await page.goto("/warehouse");
    await expect(figure(page)).toHaveAttribute("data-engine", "idle");
    const attrs = await click(page, `[data-example-button="${example.id}"]`);
    expect(attrs.error, attrs.error).toBeUndefined();
    expect(attrs, example.id).toMatchObject({ engine: "ready", query: "done", example: example.id });
    expect(Number(attrs.rows), example.id).toBeGreaterThan(0);

    // The panel shows the query that ran, the engine's bytes apart from the data's, and a file
    // line for each Parquet file the query touched (the example's table, nothing else).
    await expect(page.locator("pre[data-sql]")).toHaveText(await page.getByLabel("SQL").inputValue());
    expect(Number(attrs.bytesEngine)).toBeGreaterThan(0);
    const files = await page
      .locator("li[data-file]")
      .evaluateAll((lis) => lis.map((li) => ({ ...(li as HTMLElement).dataset })));
    expect(files.map((f) => f.table), example.id).toEqual([example.table]);
    console.log(
      `${example.id}: ${attrs.bytesDistinct} B of ${files[0].fileBytes} B fetched (${attrs.bytesQuery} requested) in ${attrs.requests} requests, ${files[0].rowGroupsRead} of ${files[0].rowGroupsTotal} row groups, ${attrs.ms} ms; engine ${attrs.bytesEngine} B`,
    );

    // The answer, against gold computed another way.
    const { header, rows } = await resultTable(page);
    expect(header, example.id).toEqual(example.columns.map((c) => c.name));
    expect(rows.length, example.id).toBe(example.rows.length);
    example.rows.forEach((want, i) =>
      want.forEach((value, j) => {
        const got = rows[i][j];
        expect(
          matches(got, value, example.columns[j].decimals),
          `${example.id} row ${i} ${header[j]}: page ${got}, gold ${value}`,
        ).toBe(true);
      }),
    );
  }

  // Running the long table's example again in the same visit is a repeat. The panel says it
  // fetched nothing instead of presenting 0 as what the query costs.
  await page.goto("/warehouse");
  await click(page, `[data-example-button="fact"]`);
  const again = await click(page, `[data-example-button="fact"]`);
  expect(again.error, again.error).toBeUndefined();
  expect(Number(again.bytesQuery)).toBe(0);
  await expect(page.locator("[data-cached]")).toBeVisible();

  // EXPLAIN ANALYZE is DuckDB's own plan, as text.
  await page.locator("button[data-explain]").click();
  await expect(page.locator("pre[data-plan]")).toContainText("READ_PARQUET");

  // Row groups of a cold read, on a fresh page. The long table is sorted
  // by metric and cut into row groups: the ones whose footer range holds the metric must have
  // bytes fetched, and not all of them.
  await page.reload();
  const cold = await click(page, `[data-example-button="fact"]`);
  expect(Number(cold.bytesQuery)).toBeGreaterThan(0);
  const fact = manifest.tables.find((t) => t.table === "fact")!;
  const metric = expected.params.football_metric;
  const holding = fact.row_groups.filter((g) => String(g.min) <= metric && metric <= String(g.max)).length;
  const li = page.locator('li[data-table="fact"]');
  const read = Number(await li.getAttribute("data-row-groups-read"));
  const total = Number(await li.getAttribute("data-row-groups-total"));
  console.log(
    `fact, ${metric}: ${read} of ${total} row groups with fetched bytes (${holding} hold the metric by their footer range), ${cold.bytesDistinct} B of ${await li.getAttribute("data-file-bytes")} B`,
  );
  expect(total).toBe(fact.row_groups.length);
  expect(read).toBeGreaterThanOrEqual(holding);
  expect(read).toBeLessThan(total);
  expect(errors).toEqual([]);
});

test("results are text: a value that looks like HTML is not parsed", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/warehouse");
  const html = '<img src=x onerror="window.__pwned=1"><b>x</b>';
  await page.getByLabel("SQL").fill(`SELECT '${html.replaceAll("'", "''")}' AS s`);
  const before = Number(await figure(page).getAttribute("data-run"));
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const attrs = await finished(page, before);
  expect(attrs.query, attrs.error).toBe("done");
  await expect(page.locator("figure.warehouse tbody td")).toHaveText(html);
  expect(await page.locator("figure.warehouse img, figure.warehouse tbody b").count()).toBe(0);
  expect(await page.evaluate(() => (window as unknown as { __pwned?: number }).__pwned)).toBeUndefined();
});

// Arrow hands back a DECIMAL as its unscaled integer and a DATE or TIMESTAMP as milliseconds
// since 1970: before `lib/warehouse/cell.ts` this row read 15, 25, -5, 982108800000 and
// 1735787045000. The warehouse files carry no DATE column since P18 (they publish `player_age`), so the DATE comes from a literal.
test("values are written by their type: decimals at their scale, dates as dates, integers whole", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/warehouse");
  const attrs = await runSql(
    page,
    "SELECT 1.5 AS a, 0.25::DECIMAL(4,2) AS b, -0.05::DECIMAL(4,2) AS c, DATE '2001-02-14' AS d, " +
      "TIMESTAMP '2025-01-02 03:04:05' AS e, 9007199254740993::BIGINT AS f, 12345678901234567890::HUGEINT AS g",
  );
  expect(attrs.query, attrs.error).toBe("done");
  const { rows } = await resultTable(page);
  expect(rows).toEqual([
    ["1.5", "0.25", "-0.05", "2001-02-14", "2025-01-02 03:04:05", "9007199254740993", "12345678901234567890"],
  ]);
});

// INTERVAL and what sits inside LIST, STRUCT, MAP and UNION, which arrow's own `get()` reads
// wrongly (`0,0` for a day, `[15,25]` for [1.5, 2.5]). Each is written as DuckDB prints it.
test("intervals and nested values are written as DuckDB prints them", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/warehouse");
  let attrs = await runSql(page, "SELECT * FROM (VALUES (INTERVAL 1 DAY), (INTERVAL 2 MONTH), (INTERVAL 3 HOUR)) t(i)");
  expect(attrs.query, attrs.error).toBe("done");
  expect((await resultTable(page)).rows).toEqual([["1 day"], ["2 months"], ["03:00:00"]]);

  attrs = await runSql(
    page,
    "SELECT age(DATE '2025-01-01', born) AS a, list(born) AS l, " +
      "{'name': player_name, 'born': born} AS s, [1.5, 2.5] AS d, MAP {'k': 1.5} AS m, " +
      "union_value(k := 1.5) AS u FROM (SELECT player_name, DATE '2001-02-14' AS born FROM fb_physical " +
      "WHERE player_name = 'Jay Barnett') GROUP BY player_name, born",
  );
  expect(attrs.query, attrs.error).toBe("done");
  expect((await resultTable(page)).rows).toEqual([
    ["23 years 10 months 15 days", "[2001-02-14]", "{'name': Jay Barnett, 'born': 2001-02-14}", "[1.5, 2.5]", "{k=1.5}", "1.5"],
  ]);
});

// A typo and its correction: the failing query already read the view's footer, which the engine
// keeps, so the corrected one fetches less than a cold read and its line has to say a file was
// held. Before the fix it read 16,384 B in 1 request and said nothing.
test("after a query that fails, the next one on the same file is not presented as cold", async ({ page }) => {
  test.setTimeout(180_000);
  const good = "SELECT player_name, team_name FROM bb_picks WHERE NOT is_season_total LIMIT 3";
  const line = page.locator('li[data-table="bb_picks"]');
  await page.goto("/warehouse");
  expect((await runSql(page, good)).query).toBe("done");
  await expect(line).toHaveAttribute("data-warm", "false");

  await page.reload();
  const bad = await runSql(page, "SELECT no_such_column FROM bb_picks");
  expect(bad.error).toMatch(/no_such_column/);
  const after = await runSql(page, good);
  expect(after.query, after.error).toBe("done");
  await expect(line).toHaveAttribute("data-warm", "true");
  await expect(line).toContainText("an earlier query had already read this file");
});

// EXPLAIN ANALYZE and an example clicked in the same tick (a double click is enough). Each empties
// the engine's request log when it starts and reads it when it ends: before they ran one at a
// time, the EXPLAIN took the example's first reads and `teams` showed 16,384 B in 1 request.
test("EXPLAIN ANALYZE and an example clicked together do not share the example's reads", async ({ page }) => {
  test.setTimeout(240_000);
  await page.goto("/warehouse");
  const cold = await click(page, '[data-example-button="teams"]');
  expect(cold.query, cold.error).toBe("done");

  await page.reload();
  await click(page, '[data-example-button="fact"]');
  const before = Number(await figure(page).getAttribute("data-run"));
  await page.evaluate(() => {
    document.querySelector<HTMLButtonElement>("button[data-explain]")!.click();
    document.querySelector<HTMLButtonElement>('[data-example-button="teams"]')!.click();
  });
  const raced = await finished(page, before);
  expect(raced.query, raced.error).toBe("done");
  expect(raced.example).toBe("teams");
  expect([raced.bytesQuery, raced.requests]).toEqual([cold.bytesQuery, cold.requests]);
  await expect(page.locator('li[data-table="bb_shots"]')).toHaveAttribute("data-warm", "false");
  // The plan of the fact query is not shown under the teams result.
  await expect(page.locator("pre[data-plan]")).toHaveCount(0);
});

// A query that would run for hours (B3 of the review of 38, 42 and 43: still running at 45 s,
// with Run and the examples disabled). Cancel ends the engine's worker and the next query starts
// a new engine.
test("Cancel stops a query that runs on, and the next query starts a new engine", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/warehouse");
  expect((await runSql(page, "SELECT 1 AS x")).query).toBe("done");
  await page.getByLabel("SQL").fill("SELECT count(*) FROM range(1000000000000)");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure(page)).toHaveAttribute("data-query", "running");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(figure(page)).toHaveAttribute("data-query", "error");
  await expect(figure(page)).toHaveAttribute("data-error", /^Cancelled/);
  await expect(figure(page)).toHaveAttribute("data-engine", "idle");
  await expect.poll(() => page.workers().length, { timeout: 10_000 }).toBe(0);

  const next = await runSql(page, "SELECT 42 AS x");
  expect(next).toMatchObject({ query: "done", engine: "ready" });
  expect((await resultTable(page)).rows).toEqual([["42"]]);
  // The new engine was started by this query, not by the first of the visit.
  await expect(figure(page)).toContainText("fetched when this engine started");
});

// EXPLAIN ANALYZE runs the result's query again (N6 of the second pass: nothing on the page said
// so, and Cancel did not exist for it). While it runs the figure says so and Cancel stops it.
test("EXPLAIN ANALYZE shows that it runs and Cancel stops it", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/warehouse");
  const attrs = await runSql(page, "SELECT count(*) AS n FROM range(300000000) t(i) WHERE i % 7 = 3");
  expect(attrs.query, attrs.error).toBe("done");
  await page.locator("button[data-explain]").click();
  await expect(figure(page)).toHaveAttribute("data-explaining", "true");
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(figure(page)).toHaveAttribute("data-explaining", "false");
  await expect(figure(page)).toHaveAttribute("data-error", /^Cancelled/);
  await expect(figure(page)).toHaveAttribute("data-query", "done");
  await expect.poll(() => page.workers().length, { timeout: 10_000 }).toBe(0);
  await expect(page.locator("pre[data-plan]")).toHaveCount(0);
});

// N2: a query can fail after the engine has read the file, while its rows are written (arrow
// throws on a TIMESTAMP that does not fit in 2^53 ms). The file is still held.
test("a query that fails while its rows are written still marks the file as read", async ({ page }) => {
  test.setTimeout(180_000);
  const good = "SELECT player_name, team_name, psv99, player_age FROM fb_physical WHERE NOT is_season_total";
  await page.goto("/warehouse");
  const bad = await runSql(page, "SELECT player_name, TIMESTAMP 'infinity' AS t FROM fb_physical LIMIT 1");
  expect(bad.query).toBe("error");
  const after = await runSql(page, good);
  expect(after.query, after.error).toBe("done");
  await expect(page.locator('li[data-table="fb_physical"]')).toHaveAttribute("data-warm", "true");
});

// N7 of the second pass: a file whose first request fails (here aborted) could not be opened again
// by the same engine until the page was reloaded ("file system operations are disabled").
test("a file that failed to open can be queried again once the network is back", async ({ page }) => {
  test.setTimeout(180_000);
  const sql = "SELECT player_name, team_name FROM bb_shots WHERE NOT is_season_total LIMIT 3";
  await page.goto("/warehouse");
  expect((await runSql(page, "SELECT 1 AS x")).query).toBe("done");
  const pattern = /bb_shots..*.parquet/;
  const abort = (route: Route) => route.abort();
  await page.route(pattern, abort);
  expect((await runSql(page, sql)).query).toBe("error");
  await page.unroute(pattern, abort);
  const again = await runSql(page, sql);
  expect(again.query, again.error).toBe("done");
  expect((await resultTable(page)).rows).toHaveLength(3);
});

// 320 is narrower than the brief asks for: the long column names overflowed there first.
for (const width of [320, 390, 1440]) {
  test(`/warehouse at ${width} px: under 400,000 bytes without the engine, no sideways scroll, text of 16 px or more`, async ({
    page,
  }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width, height: 900 });
    let transferred = 0;
    const sizes: Promise<void>[] = [];
    page.on("requestfinished", (r) =>
      sizes.push(
        r.sizes().then((s) => {
          transferred += s.responseBodySize + s.responseHeadersSize;
        }),
      ),
    );
    await page.goto("/warehouse");
    await page.waitForLoadState("networkidle");
    await Promise.all(sizes);
    console.log(`/warehouse at ${width} px: ${transferred} bytes transferred before any query`);
    expect(transferred).toBeLessThan(400_000);
    await expect(figure(page)).toHaveAttribute("data-engine", "idle");

    const check = async (what: string) => {
      const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(sideways, `${what}: page wider than the window by`).toBeLessThanOrEqual(0);
      const small = await page.evaluate(() =>
        Array.from(document.querySelectorAll("main *"))
          .filter((el) =>
            Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""),
          )
          .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
          .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}: ${(el.textContent ?? "").slice(0, 30)}`),
      );
      expect(small, `${what}: text under 16 px`).toEqual([]);
    };
    await check("before any query");

    // The widest things the page can show: a long query with its plan, a result table, and 686 column names.
    await click(page, `[data-example-button="percentile"]`);
    await page.locator("button[data-explain]").click();
    await expect(page.locator("pre[data-plan]")).toBeVisible();
    await check("after an example and its plan");
    await click(page, `[data-columns-button="bb_picks"]`);
    await expect(page.locator("[data-columns]")).toContainText("686 columns");
    await check("after listing 686 columns");
  });
}

// P19, task 153: the engine has a memory limit (MEMORY_LIMIT), so a query that wants gigabytes
// fails early with DuckDB's own message, in MiB (the 4 GiB address space gave "GiB"), and the
// same engine runs the next query. A long but small query still finishes.
test("a query that wants gigabytes fails with a readable error and the engine survives", async ({ page }) => {
  test.setTimeout(180_000);
  await page.goto("/warehouse");
  const big = await runSql(page, "SELECT length(list(range)) FROM range(300000000)");
  expect(big.query).toBe("error");
  expect(big.error).toMatch(/^Out of Memory Error: .*MiB\/\d+\.\d MiB used/);
  expect(big.engine).toBe("ready");
  const sum = await runSql(page, "SELECT sum(range) AS s FROM range(100000000)");
  expect(sum.query, sum.error).toBe("done");
  expect((await resultTable(page)).rows).toEqual([["4999999950000000"]]);
});

// P24: on a slow CPU hydration lasts long enough for `fill` to straddle it, and hydrating the
// textarea dropped the selection, so "SELECT 1" landed in front of the example instead of replacing
// it (seen once on production, 2026-11-13; 12 runs of 12 at 6x throttling). The editor is now
// read-only until hydrated, so typing waits for React.
test("on a slow CPU an edit typed as the page hydrates replaces the example", async ({ page }) => {
  test.setTimeout(180_000);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 6 });
  await page.goto("/warehouse");
  await page.getByLabel("SQL").fill("SELECT 1");
  await expect(page.getByLabel("SQL")).toHaveValue("SELECT 1");
  const before = Number(await figure(page).getAttribute("data-run"));
  await page.getByRole("button", { name: "Run", exact: true }).click();
  const f = await finished(page, before);
  expect(f.error).toBeUndefined();
  expect(f.rows).toBe("1");
});
