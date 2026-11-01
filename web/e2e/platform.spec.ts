import { expect, type Request, test } from "@playwright/test";

// `figure.platform[data-state]` drives the flow the same way `figure.hook`
// does in quality.spec.ts. The sequence itself (data-layer walking the
// layers, data-state never touching "playing" under reduced motion) is
// recorded by a MutationObserver installed through an init script -- before
// any of the page's own scripts run -- rather than sampled by polling or
// slept past, so a layer skipped between two polls still shows up in the log.
// The idle render carries no data-layer at all (Flow.tsx), so the first layer
// logged is the first one the animation actually played.

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
    const current = {
      "data-state": figure.getAttribute("data-state"),
      "data-layer": figure.getAttribute("data-layer"),
    };
    const note = () => {
      record(log.states, current["data-state"]);
      record(log.layers, current["data-layer"]);
    };
    note();
    new MutationObserver((mutations) => {
      // One batch can hold several changes to the same attribute. Each change's
      // new value is the next change's oldValue (the live value for the last),
      // so a "playing" that lasted less than a batch is still replayed here.
      mutations.forEach((mutation, i) => {
        const name = mutation.attributeName as "data-state" | "data-layer";
        const later = mutations.slice(i + 1).find((m) => m.attributeName === name);
        current[name] = later ? later.oldValue : figure.getAttribute(name);
        note();
      });
    }).observe(figure, {
      attributes: true,
      attributeOldValue: true,
      attributeFilter: ["data-state", "data-layer"],
    });
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

const LAYER_ORDER = ["raw", "bronze", "silver", "gold", "quality", "publish"];

test("plays on its own, walks the layers in order, and finishes cycle 1 exact", async ({
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

  // State, cycle, log and every counter read in one page evaluation: "done"
  // holds for 700 ms, and separate Playwright round-trips could straddle the
  // start of cycle 2 and read interpolated counters.
  const snapshot = await (
    await page.waitForFunction(() => {
      const figure = document.querySelector("figure.platform");
      if (figure?.getAttribute("data-state") !== "done" || figure.getAttribute("data-cycle") !== "1") {
        return null;
      }
      const counters = [...document.querySelectorAll("[data-counter]")].map((cell) => ({
        key: cell.getAttribute("data-counter") ?? "",
        text: (cell.textContent ?? "").trim(),
      }));
      return { log: window.__platformLog, counters };
    })
  ).jsonValue();
  if (!snapshot) throw new Error("waitForFunction resolved without a snapshot");

  expect(snapshot.log?.layers.slice(0, LAYER_ORDER.length)).toEqual(LAYER_ORDER);

  const platform = (await (await page.request.get("/data/platform.json")).json()) as PlatformJson;
  // The H1 and the line under it are the title and subtitle the script printed (task 46).
  await expect(page.locator("h1")).toHaveText(platform.title);
  await expect(page.locator("[data-subtitle]")).toHaveText(platform.subtitle);
  const count = snapshot.counters.length;
  expect(count).toBeGreaterThan(0);

  let compared = 0;
  for (const { key, text } of snapshot.counters) {
    const [layerName, field] = key.split(".");
    const layer = platform.layers.find((l) => l.layer === layerName);
    expect(layer, `platform.json has no layer "${layerName}" for data-counter="${key}"`).toBeTruthy();
    const value = (layer as unknown as Record<string, number>)[field];
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

test("the logger keeps a state that lasted less than one mutation batch", async ({ page }) => {
  await page.setContent('<figure class="platform" data-state="idle"></figure>');
  await page.evaluate(installPlatformLogger);

  const states = await page.evaluate(async () => {
    const figure = document.querySelector("figure.platform") as Element;
    // Two changes in one task land in the same MutationObserver batch.
    figure.setAttribute("data-state", "playing");
    figure.setAttribute("data-state", "done");
    await new Promise((resolve) => setTimeout(resolve, 0));
    return window.__platformLog?.states;
  });

  expect(states).toEqual(["idle", "playing", "done"]);
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
  await page.goto("/platform");
  const line = page.locator("[data-pose-share]");
  await expect(line).toHaveText(
    `Of the ${n(raw!.bytes)} raw bytes, ${n(pose!.bytes)} come from the ${pose!.files} ` +
      `body-pose zip${pose!.files === 1 ? "" : "s"} of ` +
      `opendata-bodypose that P6 added (see /pose); the other sources account for ${n(others)}.`,
  );
  await expect(line.getByRole("link", { name: "/pose" })).toHaveAttribute("href", "/pose");
});

test("the home page links to /platform and /quality", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: "How this was built" })).toHaveAttribute(
    "href",
    "/platform",
  );
  await expect(page.getByRole("link", { name: "Data quality" })).toHaveAttribute("href", "/quality");
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
  await page.goto("/platform");

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
  await expect(page.locator("h1")).toHaveText("3.6 GB in, 7.6 MB out");
});

test("no route links to the private repository", async ({ page }) => {
  const routes = ["/", "/platform", "/runs", "/quality", "/warehouse", "/replay", "/pose", "/learn", "/sql", "/euroleague", "/bulletin"];
  for (const route of routes) {
    await page.goto(route);
    const hrefs = await page.locator("a[href]").evaluateAll((as) => as.map((a) => a.getAttribute("href") ?? ""));
    expect(hrefs.filter((h) => h.includes("github.com/javiersr1996/tracklab")), route).toEqual([]);
  }
});

test("the page does not claim a CI run", async ({ page }) => {
  await page.goto("/platform");
  await expect(page.locator("main")).not.toContainText(/on every CI run|\(private repository\)/);
});
