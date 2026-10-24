import { expect as baseExpect, type Page, test } from "@playwright/test";

// Task 86: "Run it here" on the five lessons of P8. Before Run the page stays under its budget and
// has fetched nothing of the engine; after Run the query is done, every row it returns names a
// figure the lesson prints and gives that figure's text (`data-matched` of `data-figures`, and
// `window.__learn.reproduce` in a test build), with no error on the console.
const expect = baseExpect.configure({ timeout: 20_000 });
const EXPOSED = !process.env.BASE_URL;
const LESSONS = ["gravity", "speed", "coordinates", "rebound", "cadence"];
const isEngine = (url: string) => !url.startsWith("blob:") && (url.endsWith(".wasm") || new URL(url).pathname.startsWith("/duckdb/"));

async function weigh(page: Page, route: string) {
  let bytes = 0;
  const sizes: Promise<void>[] = [];
  const seen: string[] = [];
  page.on("requestfinished", (r) =>
    sizes.push(
      r.sizes().then((s) => {
        bytes += s.responseBodySize + s.responseHeadersSize;
      }),
    ),
  );
  page.context().on("request", (r) => seen.push(r.url()));
  await page.goto(route);
  await page.waitForLoadState("networkidle");
  await Promise.all(sizes);
  return { bytes, seen };
}

for (const slug of LESSONS) {
  const route = `/learn/${slug}`;
  test(`${route}: Run it here gives the lesson's own figures`, async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));
    const { bytes, seen } = await weigh(page, route);
    console.log(`${route}: ${bytes} bytes transferred before Run`);
    expect(bytes).toBeLessThan(400_000);
    expect(seen.filter(isEngine), "engine requested before Run").toEqual([]);

    const figure = page.locator("figure.run-here");
    await expect(figure).toHaveAttribute("data-engine", "idle");
    await figure.getByRole("button", { name: "Run", exact: true }).click();
    await expect(figure).toHaveAttribute("data-query", /^(done|error)$/, { timeout: 120_000 });
    expect(await figure.getAttribute("data-error")).toBeNull();
    await expect(figure).toHaveAttribute("data-figures", /^\d+$/);
    const n = Number(await figure.getAttribute("data-figures"));
    const rows = await figure.locator("table[data-result] tbody tr").evaluateAll((trs) =>
      trs.map((tr) => [tr.getAttribute("data-matched"), ...Array.from(tr.querySelectorAll("td"), (td) => td.textContent)]),
    );
    expect(rows.filter((r) => r[0] !== "true"), "rows that do not match the page").toEqual([]);
    expect(n).toBe(rows.length);
    expect(n).toBeGreaterThan(0);
    await expect(figure).toHaveAttribute("data-matched", String(n));
    if (EXPOSED) {
      const r = await page.evaluate(() => (window.__learn as { reproduce?: { matched: number; n: number } }).reproduce);
      expect(r).toMatchObject({ matched: n, n });
    }
    console.log(`${route}: ${n} of ${n} rows match; engine ${await figure.getAttribute("data-bytes-engine")} B, data ${await figure.getAttribute("data-bytes-data")} B`);
    expect(errors).toEqual([]);
  });
}
