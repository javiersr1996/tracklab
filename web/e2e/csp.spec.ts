import { type ConsoleMessage, expect as baseExpect, type Page, test } from "@playwright/test";

// P19, task 159: the Content-Security-Policy-Report-Only of next.config.ts. A browser that would
// have blocked something says so in the console ("[Report Only] Refused to ..."), and the page
// also gets a `securitypolicyviolation` event. This walks every route of /sitemap.xml and the four
// places that run DuckDB-WASM (the warehouse console, a lesson's "Run it here", an SQL lesson, the
// scouting table: the engine, its worker, its .wasm and the Parquet reads), and fails on the first
// report. Mutated by hand (restored byte for byte): `wasm-unsafe-eval` or `blob:` taken out of the
// policy makes the engine runs fail here.
const expect = baseExpect.configure({ timeout: 20_000 });
const ENGINE_TIMEOUT = 150_000;

// Chromium words a report-only violation two ways: "[Report Only] Refused to load ..." for sources,
// and "... The policy is report-only, so the violation has been logged" for WebAssembly.
const REPORT = /\[Report Only\]|policy is report-only/i;

async function watch(page: Page) {
  const reports: string[] = [];
  const hear = (m: ConsoleMessage) => {
    if (REPORT.test(m.text())) reports.push(`console: ${m.text()}`);
  };
  page.on("console", hear);
  // The engine runs in a worker, and a worker's violations reach neither the page's console nor its
  // events: they are log entries of the worker's own target. Attach to each worker before it runs
  // (waitForDebuggerOnStart) and listen to its Log domain.
  const cdp = await page.context().newCDPSession(page);
  cdp.on("Target.attachedToTarget", (e) => {
    const send = (id: number, method: string) =>
      cdp.send("Target.sendMessageToTarget", { sessionId: e.sessionId, message: JSON.stringify({ id, method }) });
    void send(1, "Log.enable").then(() => send(2, "Runtime.runIfWaitingForDebugger"));
  });
  cdp.on("Target.receivedMessageFromTarget", (e) => {
    const m = JSON.parse(e.message) as { method?: string; params?: { entry: { text: string } } };
    if (m.method === "Log.entryAdded" && REPORT.test(m.params!.entry.text)) {
      reports.push(`worker: ${m.params!.entry.text}`);
    }
  });
  await cdp.send("Target.setAutoAttach", { autoAttach: true, waitForDebuggerOnStart: true, flatten: false });
  page.on("pageerror", (e) => {
    if (REPORT.test(e.message)) reports.push(`pageerror: ${e.message}`);
  });
  await page.addInitScript(() => {
    const w = window as unknown as { __csp: string[] };
    w.__csp = [];
    document.addEventListener("securitypolicyviolation", (e) => {
      w.__csp.push(`${e.violatedDirective}: ${e.blockedURI || "inline"}`);
    });
  });
  const events = async () => {
    const seen = await page
      .evaluate(() => (window as unknown as { __csp?: string[] }).__csp ?? [])
      .catch(() => [] as string[]);
    return seen.map((s) => `event: ${s}`);
  };
  return { all: async () => [...reports, ...(await events())] };
}

async function routes(page: Page): Promise<string[]> {
  const xml = await (await page.request.get("/sitemap.xml")).text();
  return [...xml.matchAll(/<loc>https?:\/\/[^/]+(\/[^<]*)<\/loc>/g)].map((m) => m[1]).concat("/tracking/replay", "/tracking/runs", "/tracking/pose");
}

test("the policy is sent as Report-Only, with the enforced frame-ancestors beside it", async ({ request }) => {
  const res = await request.get("/");
  expect(res.headers()["content-security-policy"]).toBe("frame-ancestors 'none'");
  const policy = res.headers()["content-security-policy-report-only"];
  for (const part of [
    "default-src 'self'",
    "'wasm-unsafe-eval'",
    "worker-src 'self' blob:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
  ]) {
    expect(policy, part).toContain(part);
  }
});

test("no route of the site breaks the policy", async ({ page }) => {
  test.setTimeout(600_000);
  const csp = await watch(page);
  const paths = [...new Set(await routes(page))];
  expect(paths.length, "the sitemap lists the site").toBeGreaterThan(30);
  for (const path of paths) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await csp.all(), path).toEqual([]);
  }
});

test("the warehouse console runs DuckDB-WASM inside the policy", async ({ page }) => {
  test.setTimeout(300_000);
  const csp = await watch(page);
  await page.goto("/warehouse");
  const figure = page.locator("figure.warehouse");
  await page.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure).toHaveAttribute("data-query", "done", { timeout: ENGINE_TIMEOUT });
  expect(await csp.all()).toEqual([]);
});

test("a lesson's Run it here runs DuckDB-WASM and read_json inside the policy", async ({ page }) => {
  test.setTimeout(300_000);
  const csp = await watch(page);
  await page.goto("/learn/speed");
  const figure = page.locator("figure.run-here");
  await figure.getByLabel("SQL").fill("SELECT count(*) AS n FROM read_json('/data/learn/speed.json')");
  await figure.getByRole("button", { name: "Run", exact: true }).click();
  await expect(figure).toHaveAttribute("data-query", "done", { timeout: ENGINE_TIMEOUT });
  expect(await csp.all()).toEqual([]);
});

test("an SQL lesson runs a query inside the policy", async ({ page }) => {
  test.setTimeout(300_000);
  const csp = await watch(page);
  await page.goto("/sql/select");
  const box = page.locator("[data-exercise]").first();
  await box.getByRole("textbox", { name: "SQL" }).fill("SELECT player_name FROM bb_shots LIMIT 3");
  await box.getByRole("button", { name: "Run", exact: true }).click();
  await expect(box).not.toHaveAttribute("data-state", /^(idle|running)$/, { timeout: ENGINE_TIMEOUT });
  await expect(box).not.toHaveAttribute("data-state", "error");
  expect(await csp.all()).toEqual([]);
});

test("the scouting table loads its Parquet and compares two players inside the policy", async ({ page }) => {
  test.setTimeout(300_000);
  const csp = await watch(page);
  await page.goto("/warehouse/scouting");
  await page.getByRole("button", { name: "Load the table" }).click();
  const s = page.locator("div.scout");
  await expect(s).toHaveAttribute("data-compared", /\S/, { timeout: ENGINE_TIMEOUT });
  await expect(s).toHaveAttribute("data-query", "done", { timeout: ENGINE_TIMEOUT });
  expect(await csp.all()).toEqual([]);
});
