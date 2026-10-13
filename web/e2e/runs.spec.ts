import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, type Page, test } from "@playwright/test";
import type { Possession } from "../lib/replay/types";
import type { Runs } from "../lib/runs/types";

// `/runs` (task 53) fetches `/data/runs.json`, so each test hands the page the file it wants
// through `page.route`: the published one (dead at M5a), the same with another `dead_at`, and
// `fixtures/runs.alive.json`, the alive branch (the alive document of task 51 does not exist; the
// fixture is the dead file with the fields that make it alive, checked in
// pipeline/tests/unit/test_publish_runs.py). Every figure is read back from the file the page
// was given, never typed here. The animation is driven through `window.__replays` and the
// figure's `data-state`, which exist in a test build (task 21), not against a deployment.

const EXPOSED = !process.env.BASE_URL;
const WIDTHS = [390, 1440];

const resolve = (root: unknown, dotted: string): unknown =>
  dotted.split(".").reduce<unknown>((node, key) => (node as Record<string, unknown>)?.[key], root);

async function publishedRuns(page: Page): Promise<Runs> {
  return (await (await page.request.get("/data/runs.json")).json()) as Runs;
}

const aliveRuns = (): Runs =>
  JSON.parse(readFileSync(path.join(process.cwd(), "e2e", "fixtures", "runs.alive.json"), "utf-8"));

// The dead file with its death moved earlier: M2 dead, everything after it not reached.
function deadAtM2(runs: Runs): Runs {
  const copy = structuredClone(runs);
  copy.dead_at = "M2";
  copy.stages.M2.state = "dead";
  for (const stage of ["M3", "M4", "M5a", "M5b"] as const) copy.stages[stage].state = "not_reached";
  return copy;
}

async function open(page: Page, runs: Runs) {
  await page.route("**/data/runs.json", (route) => route.fulfill({ json: runs }));
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/runs");
  await expect(page.locator("main.runs")).toHaveAttribute("data-loaded", "true");
  await expect(page.locator("[data-status]")).toBeVisible();
  return errors;
}

// Every `data-fig` element holds the value at its path in the file.
async function expectFiguresOf(page: Page, runs: Runs) {
  const shown = await page
    .locator("[data-fig]")
    .evaluateAll((els) => els.map((e) => [e.getAttribute("data-fig"), (e.textContent ?? "").trim()]));
  expect(shown.length).toBeGreaterThan(400);
  const wrong: string[] = [];
  for (const [p, text] of shown) {
    const value = resolve(runs, p ?? "");
    if (value === undefined) wrong.push(`${p}: not in the file`);
    else if (text !== String(value)) wrong.push(`${p}: page "${text}", file ${String(value)}`);
    else if (typeof value === "number" && Number(text) !== value) wrong.push(`${p}: ${text}`);
  }
  expect(wrong.slice(0, 5)).toEqual([]);
  // The figures come from every part of the file, not from one corner.
  const roots = new Set(shown.map(([p]) => (p ?? "").split(".")[0]));
  for (const root of [
    "stages",
    "effect_by_subtype",
    "instrument",
    "funnel",
    "power",
    "null",
    "never_opened",
    "post_hoc_kinematics",
    "protocol",
    "hook",
    "dead_at",
  ]) {
    if (root === "dead_at" && runs.dead_at === null) continue;
    expect(roots, `no figure of ${root}`).toContain(root);
  }
  return shown.length;
}

test("the dead branch: the status line, the stage that died and every figure of runs.json", async ({
  page,
}) => {
  const runs = await publishedRuns(page);
  expect(runs.status).toBe("dead");
  const errors = await open(page, runs);

  await expect(page.locator("h1")).toHaveText("The run that moves nobody");
  const status = page.locator("[data-status]");
  await expect(status).toHaveAttribute("data-status", "dead");
  await expect(status).toHaveAttribute("data-dead-at", runs.dead_at ?? "");
  await expect(status).toContainText(`Dead at ${runs.dead_at}`);
  await expect(status).not.toContainText("Alive");
  await expect(status).toContainText("never opened");

  // Exactly the stage the file names is marked as the one that died.
  const died = await page.locator("tr[data-stage]").evaluateAll((rows) =>
    rows.map((r) => [r.getAttribute("data-stage"), r.getAttribute("data-died")]),
  );
  expect(died.filter(([, flag]) => flag === "true")).toEqual([[runs.dead_at, "true"]]);
  expect(died.map(([stage]) => stage)).toEqual(["M1", "M2", "M3", "M4", "M5a", "M5b"]);
  // The negative next to the positive: M2 passed while M3 ruled every subtype out.
  await expect(page.locator('tr[data-stage="M2"]')).toHaveAttribute("data-state", runs.stages.M2.state);
  await expect(page.locator('tr[data-stage="M3"]')).toHaveAttribute("data-state", runs.stages.M3.state);
  const subtypeRows = page.locator('tr[data-row="subtype"]');
  await expect(subtypeRows).toHaveCount(runs.effect_by_subtype.length);
  for (const [j, s] of runs.effect_by_subtype.entries()) {
    const row = subtypeRows.nth(j);
    await expect(row).toHaveAttribute("data-subtype", s.subtype);
    // The line's secondary label sits in the row of the marker figure it qualifies.
    await expect(row).toContainText(s.line.testability);
    // The line was never read by M3 or M4: a subtype it cannot test gets no verdict in its cell.
    const lineCell = row.locator('[data-cell="line-passes"]');
    if (s.line.testability.startsWith("not testable")) await expect(lineCell).toHaveText("not testable");
    else await expect(lineCell).toHaveText(s.line.pooled.passes_bar ? "yes" : "no");
    await expect(row.locator(`[data-fig="effect_by_subtype.${j}.marker.pooled.mean_m"]`)).toBeVisible();
    await expect(row.locator(`[data-fig="effect_by_subtype.${j}.verdict.M3.pre_trend_ratio"]`)).toBeVisible();
  }

  await expect(page.locator('[data-note="line-not-candidate"]')).toContainText("never went through M3 or M4");
  await expect(page.locator('section[data-section="negative"] thead th').filter({ hasText: "(marker)" })).toHaveCount(4);

  // M1 prints all three counts of the probable lists, not only the one it decides on.
  const m1 = page.locator('tr[data-stage="M1"]');
  for (const k of ["probable_subtypes", "probable_by_line", "probable_by_both", "needs_at_least"]) {
    await expect(m1.locator(`[data-fig="stages.M1.figures.${k}"]`)).toHaveText(String(runs.stages.M1.figures[k]));
  }

  // The held-out half: counts, for exactly the matches the file lists, and nothing else.
  const held = page.locator('section[data-section="held-out"]');
  await expect(held).toHaveAttribute("data-opened", "false");
  await expect(held.locator("h2")).toHaveText("Held-out half: never opened");
  const heldIds = await held.locator("tbody tr").evaluateAll((rows) => rows.map((r) => Number(r.getAttribute("data-match"))));
  expect(heldIds).toEqual(runs.never_opened.match_ids);
  expect(await held.locator("thead th").allTextContents()).toEqual([
    "match",
    "runs",
    "runner detected",
    "clean",
    "placebo found",
    "analysis set",
  ]);

  // The calibration tables list the calibration matches and no others.
  const calibrationIds = runs.funnel.coverage.filter((r) => r.half === "calibration").map((r) => r.match_id);
  const funnelIds = await page
    .locator('tbody[data-table="funnel"] tr')
    .evaluateAll((rows) => rows.map((r) => Number(r.getAttribute("data-match"))));
  expect(funnelIds).toEqual(calibrationIds);
  expect(funnelIds.filter((id) => heldIds.includes(id))).toEqual([]);
  for (const table of ["marker", "line", "pre-trend", "fully-detected", "null"]) {
    const ids = await page
      .locator(`tbody[data-table="${table}"] tr`)
      .evaluateAll((rows) => rows.map((r) => Number(r.getAttribute("data-match"))));
    expect(ids, table).toEqual(calibrationIds);
  }

  // The order the plan gives the page.
  const sections = await page
    .locator("main [data-section]")
    .evaluateAll((els) => els.map((e) => e.getAttribute("data-section")));
  expect(sections).toEqual([
    "hook",
    "stages",
    "negative",
    "per-match-effects",
    "calibration",
    "held-out",
    "reason",
    "protocol",
    "scope",
  ]);

  // The reason is labelled post hoc, once per finding, and its tables are per subtype and per match.
  await expect(page.locator('[data-label="post-hoc"]')).toContainText("post hoc");
  await expect(page.locator("[data-finding]")).toHaveCount(4);
  for (const finding of await page.locator("[data-finding]").all()) {
    await expect(finding.locator("tbody").first().locator("tr")).toHaveCount(runs.post_hoc_kinematics.per_subtype.length);
  }

  // The protocol: its fingerprint and stage, from the file, and the scope line.
  const protocol = page.locator('section[data-section="protocol"]');
  await expect(protocol).toContainText(runs.protocol.fingerprint);
  await expect(protocol).toContainText(`seen: ${runs.protocol.stages_seen.join(", ")}`);
  await expect(protocol.locator("[data-history]")).toHaveCount(runs.protocol.history.length);
  const scope = page.locator('[data-section="scope"]');
  await expect(scope.locator('[data-scope="matches"]')).toHaveText(String(runs.funnel.coverage.length));

  const compared = await expectFiguresOf(page, runs);
  console.log(`/runs (dead): ${compared} figures checked against runs.json`);

  // Words the page must not use: no intention, no ranking, no claim that a subtype moves the defence.
  const prose = await page.evaluate(() =>
    Array.from(document.querySelectorAll("main > *:not([data-section='scope'])"))
      .map((e) => (e as HTMLElement).innerText)
      .join("\n"),
  );
  expect(prose).not.toMatch(/\b(drag|drags|dragged|dragging|fool|fools|fooled|pulls?|pulled|decoys?)\b/i);
  expect(prose).not.toMatch(/\b(moves?|moved) the defen[cs]e\b/i);
  expect(prose).not.toMatch(/\b(rank|ranks|ranked|ranking|rankings|intent|intents|intention|intentions|intentional)\b/i);
  expect(errors).toEqual([]);
});

test("the dead branch follows dead_at: dead at M2, the later stages are not reached", async ({ page }) => {
  const runs = deadAtM2(await publishedRuns(page));
  await open(page, runs);

  await expect(page.locator("[data-status]")).toHaveAttribute("data-dead-at", "M2");
  await expect(page.locator("[data-status]")).toContainText("Dead at M2");
  await expect(page.locator('tr[data-stage="M2"]')).toHaveAttribute("data-died", "true");
  await expect(page.locator('tr[data-stage="M5a"]')).toHaveAttribute("data-died", "false");
  await expect(page.locator('tr[data-stage="M5a"]')).toHaveAttribute("data-state", "not_reached");
  await expectFiguresOf(page, runs);
});

test("the alive branch: no stage died, the held-out half is opened", async ({ page }) => {
  const runs = aliveRuns();
  expect(runs.status).toBe("alive");
  const errors = await open(page, runs);

  await expect(page.locator("h1")).toHaveText("The run that moves nobody");
  const status = page.locator("[data-status]");
  await expect(status).toHaveAttribute("data-status", "alive");
  await expect(status).toHaveAttribute("data-dead-at", "");
  await expect(status).toContainText("Alive");
  await expect(status).not.toContainText("Dead at");
  await expect(status).not.toContainText("never opened");
  await expect(page.locator('tr[data-died="true"]')).toHaveCount(0);
  await expect(page.locator('tr[data-stage="M5a"]')).toHaveAttribute("data-state", "passed");
  const held = page.locator('section[data-section="held-out"]');
  await expect(held).toHaveAttribute("data-opened", "true");
  await expect(held.locator("h2")).toHaveText("Held-out half: opened");
  await expectFiguresOf(page, runs);
  expect(errors).toEqual([]);
});

// The hook, driven by the player's own state: it starts on its own, ends on its last frame, and
// the arrows of the defence appear when the clip reaches the instant and not before.
test("the hook plays the run and its placebo and paints the defence from the instant on", async ({
  page,
}) => {
  test.skip(!EXPOSED, "window.__replays exists only in dev and test builds");
  const runs = await publishedRuns(page);
  const errors = await open(page, runs);

  for (const clip of runs.hook.clips) {
    const leg = page.locator(`section[data-leg="${clip.role}"]`);
    const clipFile = (await (await page.request.get(`/data/${clip.file}`)).json()) as Possession;
    const t0 = clipFile.frames[0].t;
    const tInstant = clipFile.frames[clip.instant_index].t;
    const tEnd = clipFile.frames[clipFile.frames.length - 1].t;
    expect(clipFile.frames.length).toBe(clip.frames);
    const replay = () => page.evaluate((role) => window.__replays![role], clip.role);

    // idle at load is not observable (autoplay): it starts playing, then ends on the last frame.
    await expect(leg.locator("figure.replay")).toHaveAttribute("data-state", /playing|ended/);
    await expect(leg.locator("figure.replay")).toHaveAttribute("data-state", "ended", { timeout: 15_000 });
    await expect.poll(async () => (await replay()).t).toBe(tEnd);
    expect((await replay()).overlay).toBe(clip.defence.length);

    // Scrubbing back: before the instant nothing is painted, from it on one arrow per opponent.
    const scrub = leg.getByLabel("Scrub");
    for (const [t, painted] of [
      [t0, 0],
      [tInstant - 1, 0],
      [tInstant, clip.defence.length],
      [tEnd, clip.defence.length],
    ] as const) {
      await scrub.fill(String(t));
      await expect.poll(async () => (await replay()).t, { message: `${clip.role} at ${t}` }).toBe(t);
      await expect
        .poll(async () => (await replay()).overlay, { message: `${clip.role} arrows at ${t}` })
        .toBe(painted);
      await expect(leg.locator("figure.replay")).toHaveAttribute("data-state", "paused");
    }

    // The marker is the one opponent the table calls so, with the displacement the clip names.
    const markerRow = leg.locator("[data-opponent]", { hasText: "marker" });
    await expect(markerRow).toHaveCount(1);
    await expect(markerRow).toContainText(clip.marker_entity_id);
    await expect(markerRow.locator("[data-fig]")).toHaveText(String(clip.marker_displacement_m));
    expect(clip.defence.filter((d) => d.is_marker).map((d) => d.entity_id)).toEqual([clip.marker_entity_id]);
  }
  expect(errors).toEqual([]);
});

for (const width of WIDTHS) {
  test(`/runs at ${width} px: no sideways scroll, no overlaps, text of 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const runs = await publishedRuns(page);
    await open(page, runs);
    await expect(page.locator("figure.replay")).toHaveCount(2);

    const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(sideways, "page wider than the window by").toBeLessThanOrEqual(0);

    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .filter((el) =>
          Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""),
        )
        .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
        .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}: ${(el.textContent ?? "").slice(0, 30)}`),
    );
    expect(small, "text under 16 px").toEqual([]);

    // Blocks stack: each top-level child starts at or below where the previous one ends, and
    // nothing, tables and canvases included, reaches past the right edge of the window.
    const boxes = await page.evaluate(() => {
      const main = document.querySelector("main")!;
      const rect = (e: Element) => {
        const r = e.getBoundingClientRect();
        return { top: r.top + window.scrollY, bottom: r.bottom + window.scrollY, right: r.right };
      };
      return {
        blocks: Array.from(main.children).map((e) => ({ tag: e.tagName.toLowerCase(), ...rect(e) })),
        wide: Array.from(main.querySelectorAll("canvas, .table-scroll, table, section, p, h1, h2, h3, dl"))
          .filter((e) => !e.closest(".table-scroll") || e.classList.contains("table-scroll"))
          .filter((e) => rect(e).right > window.innerWidth + 0.5)
          .map((e) => `${e.tagName.toLowerCase()} ${(e.textContent ?? "").slice(0, 20)}`),
      };
    });
    for (let i = 1; i < boxes.blocks.length; i++) {
      expect(boxes.blocks[i].top, `${boxes.blocks[i].tag} #${i} overlaps the block above`).toBeGreaterThanOrEqual(
        boxes.blocks[i - 1].bottom - 1,
      );
    }
    expect(boxes.wide, "reaches past the window").toEqual([]);

    // The two clips side by side only when there is room; never overlapping each other.
    const legs = await page.locator("section[data-leg]").evaluateAll((els) =>
      els.map((e) => {
        const r = e.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
      }),
    );
    expect(legs).toHaveLength(2);
    const [a, b] = legs;
    const apart = a.right <= b.left + 0.5 || b.right <= a.left + 0.5 || a.bottom <= b.top + 0.5 || b.bottom <= a.top + 0.5;
    expect(apart, "the two legs overlap").toBe(true);
  });
}

test("the home page links to /runs", async ({ page }) => {
  await page.goto("/");
  const link = page.getByRole("link", { name: "The run that moves nobody" });
  await expect(link).toHaveAttribute("href", "/runs");
  await link.click();
  await expect(page).toHaveURL(/\/runs$/);
  await expect(page.locator("h1")).toHaveText("The run that moves nobody");
});
