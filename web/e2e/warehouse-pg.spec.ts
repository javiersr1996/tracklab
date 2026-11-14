import { expect, type Page, test } from "@playwright/test";

// Task 45: the Postgres half of /warehouse, driven by `figure.warehouse[data-backend]`
// (`idle`, `running`, then `live`, `snapshot` or `absent`), never by a screenshot or a sleep.
// (a) a deployment without DATABASE_URL: `absent`, every example `done` from Parquet, and the
//     page neither draws a Postgres panel nor mentions one.
// (b) the page's own route blocked, or never answering, or answering badly: `snapshot`, every
//     example still `done`, no error thrown on the page.
// (c) a live backend: `live`, and the rows equal the Parquet ones. It needs a server started
//     with DATABASE_URL (the read-only role of a Postgres loaded by `tracklab load postgres`)
//     and TRACKLAB_E2E_BACKEND=live; without that variable (c) skips and (a) runs.
//     On a deployment: BASE_URL=<preview> TRACKLAB_E2E_BACKEND=live npx playwright test warehouse-pg
const LIVE = process.env.TRACKLAB_E2E_BACKEND === "live";
const ROUTE = "**/api/warehouse/pg**";

interface Snapshot {
  examples: { id: string; columns: string[]; rows: (string | number | null)[][] }[];
}
interface Expected {
  examples: { id: string; columns: { name: string; decimals: number | null }[] }[];
}

const figure = (page: Page) => page.locator("figure.warehouse");

// Page errors and console errors, with the console lines Chromium writes for a request that was
// blocked on purpose (named in `allowed`) kept apart: anything else is a failure.
function watch(page: Page) {
  const errors: string[] = [];
  const blocked: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() !== "error") return;
    (/Failed to load resource/.test(m.text()) ? blocked : errors).push(m.text());
  });
  return { errors, blocked };
}

async function ask(page: Page, id: string) {
  const f = figure(page);
  const before = Number(await f.getAttribute("data-run"));
  await page.locator(`[data-example-button="${id}"]`).click();
  await expect(f).toHaveAttribute("data-run", String(before + 1));
}

async function done(page: Page) {
  await expect(figure(page)).toHaveAttribute("data-query", "done", { timeout: 120_000 });
}

// The cells of a table as text, rows of columns.
const cells = (table: ReturnType<Page["locator"]>) =>
  table.locator("tbody tr").evaluateAll((trs) => trs.map((tr) => Array.from(tr.querySelectorAll("td"), (td) => td.textContent ?? "")));

async function snapshot(page: Page) {
  return (await (await page.request.get("/data/warehouse_pg.json")).json()) as Snapshot;
}

// Two cells as text: numbers agree to within half a unit of the last rounded digit, the rest exactly.
function sameCell(a: string, b: string, decimals: number | null) {
  const numeric = a.trim() !== "" && b.trim() !== "" && !Number.isNaN(Number(a)) && !Number.isNaN(Number(b));
  return numeric ? Math.abs(Number(a) - Number(b)) <= (decimals === null ? 0 : 0.5 * 10 ** -decimals) + 1e-6 : a === b;
}

test.describe("the route takes an example id and nothing else", () => {
  test("answers 400 to an unknown id, to SQL and to a method with a body", async ({ request }) => {
    for (const query of [
      "",
      "?id=nope",
      `?id=${encodeURIComponent("SELECT 1")}`,
      `?id=profile&sql=${encodeURIComponent("SELECT 1")}`,
      "?id=profile&id=teams",
    ]) {
      const res = await request.get(`/api/warehouse/pg${query}`);
      expect(res.status(), query).toBe(400);
    }
    const post = await request.post("/api/warehouse/pg?id=profile", { data: { sql: "SELECT 1" } });
    expect(post.status()).toBe(405);
  });
});

test.describe("(a) without DATABASE_URL", () => {
  test.skip(LIVE, "this server has a backend");

  test("every example is done from Parquet and no Postgres panel is drawn, nor promised above", async ({ page }) => {
    test.setTimeout(240_000);
    const { errors, blocked } = watch(page);
    const snap = await snapshot(page);
    await page.goto("/warehouse");
    await expect(figure(page)).toHaveAttribute("data-backend", "idle");

    for (const example of snap.examples) {
      await ask(page, example.id);
      await done(page);
      await expect(figure(page)).toHaveAttribute("data-backend", "absent");
      await expect(page.locator("[data-pg-panel]")).toHaveCount(0);
    }
    await expect(page.locator("main")).not.toContainText("Postgres");
    expect(errors).toEqual([]);
    expect(blocked).toEqual([]);
  });

  test("an edited query asks nothing of Postgres", async ({ page }) => {
    const seen: string[] = [];
    page.on("request", (r) => r.url().includes("/api/warehouse/pg") && seen.push(r.url()));
    await page.goto("/warehouse");
    await page.getByLabel("SQL").fill("SELECT 1");
    await page.getByRole("button", { name: "Run", exact: true }).click();
    await done(page);
    await expect(figure(page)).toHaveAttribute("data-backend", "idle");
    expect(seen).toEqual([]);
  });
});

test.describe("(b) the backend does not answer", () => {
  const variants: [string, (page: Page) => Promise<unknown>, string][] = [
    ["blocked (the request aborts)", (page) => page.route(ROUTE, (r) => r.abort()), "could not be reached"],
    ["never answers", (page) => page.route(ROUTE, () => {}), "did not answer in time"],
    [
      "answers that it timed out",
      (page) => page.route(ROUTE, (r) => r.fulfill({ json: { status: "timeout" } })),
      "did not answer in time",
    ],
    ["answers with a server error", (page) => page.route(ROUTE, (r) => r.fulfill({ status: 500, body: "boom" })), "could not be reached"],
  ];
  for (const [name, setup, sentence] of variants) {
    test(`${name}: snapshot, and the example is still done`, async ({ page }) => {
      test.setTimeout(180_000);
      const { errors } = watch(page);
      await setup(page);
      const snap = await snapshot(page);
      const example = snap.examples.find((e) => e.id === "teams")!;
      await page.goto("/warehouse");
      await ask(page, "teams");
      await done(page);
      // It may be waiting (the route that never answers): the state says so, and then ends.
      await expect(figure(page)).toHaveAttribute("data-backend", "snapshot", { timeout: 15_000 });
      await expect(page.locator("[data-pg-why]")).toContainText(sentence);
      await expect(page.locator("[data-pg-why]")).toContainText("asleep, down or not configured");
      expect(await cells(page.locator("[data-pg-result]"))).toEqual(example.rows.map((r) => r.map((c) => (c === null ? "" : String(c)))));
      expect(await cells(page.locator("figure.warehouse > .table-scroll table"))).not.toEqual([]);
      expect(errors).toEqual([]);
    });
  }
});

test.describe("(c) a live backend", () => {
  test.skip(!LIVE, "needs DATABASE_URL on the server and TRACKLAB_E2E_BACKEND=live");

  test("live, and the rows of Postgres are the rows of Parquet", async ({ page }) => {
    test.setTimeout(240_000);
    const { errors, blocked } = watch(page);
    const expected = (await (await page.request.get("/data/warehouse_examples.json")).json()) as Expected;
    const snap = await snapshot(page);
    await page.goto("/warehouse");
    for (const example of snap.examples) {
      await ask(page, example.id);
      await done(page);
      await expect(figure(page)).toHaveAttribute("data-backend", "live", { timeout: 30_000 });
      await expect(page.locator("[data-pg-panel]")).toHaveAttribute("data-pg-source", "live");
      const parquet = await cells(page.locator("figure.warehouse > .table-scroll table"));
      const postgres = await cells(page.locator("[data-pg-result]"));
      const decimals = expected.examples.find((e) => e.id === example.id)!.columns.map((c) => c.decimals);
      expect(postgres.length, example.id).toBe(parquet.length);
      expect(postgres.length, example.id).toBeGreaterThan(0);
      postgres.forEach((row, i) =>
        row.forEach((shown, j) => {
          expect(sameCell(shown, parquet[i][j], decimals[j]), `${example.id} row ${i} col ${j}: ${parquet[i][j]} vs ${shown}`).toBe(true);
        }),
      );
      await expect(page.locator("[data-pg-compare] [data-figure=live-ms]")).toBeVisible();
    }
    expect(errors).toEqual([]);
    expect(blocked).toEqual([]);
  });
});
