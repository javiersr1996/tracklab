import { expect, type Page, test } from "@playwright/test";

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

// Cells of the result table as text: header names, then rows.
async function resultTable(page: Page) {
  const header = await page.locator("figure.warehouse thead th").allTextContents();
  const rows = await page
    .locator("figure.warehouse tbody tr")
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

for (const width of [390, 1440]) {
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
