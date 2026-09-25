import { expect, type Request, test } from "@playwright/test";

// `figure.platform[data-state]` drives the flow the same way `figure.hook`
// does in quality.spec.ts. The sequence itself (data-layer walking the five
// layers, data-state never touching "playing" under reduced motion) is
// recorded by a MutationObserver installed through an init script -- before
// any of the page's own scripts run -- rather than sampled by polling or
// slept past, so a layer skipped between two polls still shows up in the log.

declare global {
  interface Window {
    __platformLog?: { states: string[]; layers: string[] };
  }
}

// Runs in the page (stringified by Playwright), not in this test's own scope.
function installPlatformLogger(): void {
  const log: { states: string[]; layers: string[] } = { states: [], layers: [] };
  window.__platformLog = log;

  const record = (list: string[], value: string | null) => {
    if (value !== null && list[list.length - 1] !== value) list.push(value);
  };

  const watch = (figure: Element) => {
    record(log.states, figure.getAttribute("data-state"));
    record(log.layers, figure.getAttribute("data-layer"));
    new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.attributeName === "data-state") {
          record(log.states, figure.getAttribute("data-state"));
        } else if (mutation.attributeName === "data-layer") {
          record(log.layers, figure.getAttribute("data-layer"));
        }
      }
    }).observe(figure, { attributes: true, attributeFilter: ["data-state", "data-layer"] });
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
  layers: PlatformLayerRecord[];
}

const LAYER_ORDER = ["raw", "bronze", "silver", "quality", "publish"];

test("plays on its own, walks the five layers in order, and finishes cycle 1 exact", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  const requests: Request[] = [];
  page.on("requestfinished", (r) => requests.push(r));

  await page.addInitScript(installPlatformLogger);
  await page.goto("/platform");

  await expect(page.locator("figure.platform")).toHaveAttribute("data-state", "playing", {
    timeout: 2_000,
  });

  // "done" and "data-cycle" read together in one page evaluation: two
  // separate Playwright round-trips could straddle the moment cycle 2 starts.
  await page.waitForFunction(() => {
    const figure = document.querySelector("figure.platform");
    return figure?.getAttribute("data-state") === "done" && figure?.getAttribute("data-cycle") === "1";
  });

  const log = await page.evaluate(() => window.__platformLog);
  expect(log?.layers.slice(0, LAYER_ORDER.length)).toEqual(LAYER_ORDER);

  const platform = (await (await page.request.get("/data/platform.json")).json()) as PlatformJson;
  const counters = page.locator("[data-counter]");
  const count = await counters.count();
  expect(count).toBeGreaterThan(0);

  let compared = 0;
  for (let i = 0; i < count; i++) {
    const cell = counters.nth(i);
    const key = (await cell.getAttribute("data-counter")) ?? "";
    const [layerName, field] = key.split(".");
    const layer = platform.layers.find((l) => l.layer === layerName);
    expect(layer, `platform.json has no layer "${layerName}" for data-counter="${key}"`).toBeTruthy();
    const value = (layer as unknown as Record<string, number>)[field];
    const text = ((await cell.textContent()) ?? "").trim();
    const stripped = text.replace(/,/g, "");
    const expected = field === "seconds" ? value.toFixed(1) : String(value);
    expect(stripped, `${key}: page shows "${text}", platform.json has ${value}`).toBe(expected);
    compared++;
  }
  console.log(`/platform: ${compared} counters checked against platform.json at data-state="done"`);
  expect(compared).toBe(count);

  await page.waitForLoadState("networkidle");
  let transferred = 0;
  for (const r of requests) {
    const sizes = await r.sizes();
    transferred += sizes.responseBodySize + sizes.responseHeadersSize;
  }
  console.log(`/platform: ${transferred} bytes transferred`);
  expect(transferred).toBeLessThan(400_000);

  expect(errors).toEqual([]);
});

test.describe("prefers-reduced-motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("jumps straight to done, never through playing", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
    page.on("pageerror", (e) => errors.push(e.message));

    await page.addInitScript(installPlatformLogger);
    await page.goto("/platform");

    await expect(page.locator("figure.platform")).toHaveAttribute("data-state", "done");
    await expect(page.locator("figure.platform")).toHaveAttribute("data-cycle", "1");

    const log = await page.evaluate(() => window.__platformLog);
    expect(log?.states ?? []).not.toContain("playing");
    expect(log?.states.at(-1)).toBe("done");

    expect(errors).toEqual([]);
  });
});

test("the home page links to /platform and /quality", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "How this was built" })).toHaveAttribute(
    "href",
    "/platform",
  );
  await expect(page.getByRole("link", { name: "Data quality" })).toHaveAttribute("href", "/quality");
});
