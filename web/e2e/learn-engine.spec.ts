import { expect, test } from "@playwright/test";

// Task 85, first step: the engine of "Run it here" (`lib/learn/engine.ts`, an instance of the
// shared `lib/duckdb/engine.ts`) reads a published JSON file in the browser, loading the json
// extension from this deployment and nothing from another origin. Requests are watched on the
// context, which also sees the worker's. The engine's bytes are the worker's Resource Timing, the
// page's own count, printed.
const ROUTE = "/learn/speed";
const isEngine = (url: string) => !url.startsWith("blob:") && (url.endsWith(".wasm") || new URL(url).pathname.startsWith("/duckdb/"));

test("read_json runs in the browser with this deployment's json extension and nothing from another origin", async ({ page, baseURL }) => {
  const seen: string[] = [];
  const errors: string[] = [];
  page.context().on("request", (r) => seen.push(r.url()));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(ROUTE);
  await page.waitForLoadState("networkidle");
  expect(seen.filter(isEngine), "engine requested before Run").toEqual([]);

  const figure = page.locator("figure.run-here");
  await expect(figure).toHaveAttribute("data-engine", "idle");
  await figure.getByLabel("SQL").fill("SELECT count(*) AS n FROM read_json('/data/learn/speed.json')");
  await figure.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure).toHaveAttribute("data-query", /^(done|error)$/, { timeout: 120_000 });
  expect(await figure.getAttribute("data-error")).toBeNull();
  await expect(figure).toHaveAttribute("data-query", "done");
  await expect(figure.locator("table[data-result] td")).toHaveText(["1"]);

  const origin = new URL(baseURL!).origin;
  const foreign = seen.filter((u) => !u.startsWith("blob:") && new URL(u).origin !== origin);
  expect(foreign, "requests to another origin").toEqual([]);
  const extensions = seen.filter((u) => !u.startsWith("blob:") && new URL(u).pathname.startsWith("/duckdb/ext/"));
  expect(extensions.map((u) => new URL(u).pathname.split("/").pop()), "extensions requested").toEqual(["json.duckdb_extension.wasm"]);
  const engineBytes = Number(await figure.getAttribute("data-bytes-engine"));
  const dataBytes = Number(await figure.getAttribute("data-bytes-data"));
  console.log(`learn engine: ${engineBytes} bytes of engine, ${dataBytes} bytes of data`);
  expect(engineBytes).toBeGreaterThan(0);
  expect(dataBytes).toBeGreaterThan(0);

  // Locked: a file the lesson does not register is refused.
  await figure.getByLabel("SQL").fill("SELECT count(*) FROM read_json('/data/quality.json')");
  await figure.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure).toHaveAttribute("data-run", "2");
  await expect(figure).toHaveAttribute("data-query", "error", { timeout: 60_000 });
  expect(errors).toEqual([]);
});
