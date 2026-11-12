import { expect, type Page, test } from "@playwright/test";

// The inner pages open in plain words: the first paragraph under the title says what the page shows
// to someone who arrives cold, and the copy a visitor sees carries no internal code (a phase, a
// milestone, a task or a decision number) unless the page pairs it with its meaning.

const PAGES = [
  "/tracking/pose",
  "/tracking/runs",
  "/tracking/replay",
  "/engineering",
  "/engineering/quality",
  "/engineering/bulletin",
  "/engineering/history",
  "/warehouse",
  "/warehouse/scouting",
  "/warehouse/positions",
  "/tracking/occupancy",
];

// Waits for what the page fetches before it writes its head (pose, runs).
async function settle(page: Page, path: string) {
  await page.goto(path);
  if (path === "/tracking/pose") await expect(page.locator("[data-section=status]")).toBeVisible();
  if (path === "/tracking/runs") await expect(page.locator("main.runs")).toHaveAttribute("data-loaded", "true");
}

for (const path of PAGES) {
  test(`${path} opens with a plain lede right under its title`, async ({ page }) => {
    await settle(page, path);
    // The paragraph after the h1, past the title's own second line (/engineering's subtitle).
    const next = await page.locator("main h1").evaluate((h1) => {
      let el = h1.nextElementSibling;
      while (el && el.hasAttribute("data-subtitle")) el = el.nextElementSibling;
      return el ? { lede: el.hasAttribute("data-lede"), text: (el.textContent ?? "").trim() } : null;
    });
    expect(next?.lede, `${path}: the element under the title is the lede`).toBe(true);
    expect(next!.text.split(/[.?!](\s|$)/).filter((s) => s.trim().length > 0).length).toBeLessThanOrEqual(3);
    expect(next!.text.length).toBeGreaterThan(60);
  });
}

// Codes a visitor would not know. Where one stays, the page prints its meaning beside it: the runs
// stage table (each code with its plain name), its status line and the home's runs card.
const CODES = /\bP\d{1,2}\b|\bM\d[ab]?\b|\btask \d+|\bdecision \d|\bCP\d*\b/g;
const PAIRED = ["tr[data-stage]", "[data-status]", '[data-finding="runs"] .finding-vs'];

// The bulletin is docs/bulletin.md as the pipeline writes it, outside this app: not checked here.
for (const path of ["/", ...PAGES.filter((p) => p !== "/engineering/bulletin")]) {
  test(`${path}: no internal code in the visible copy`, async ({ page }) => {
    await settle(page, path);
    const text = await page.evaluate((paired) => {
      let t = document.body.innerText;
      for (const sel of paired) for (const el of document.querySelectorAll<HTMLElement>(sel)) t = t.replace(el.innerText, "");
      return t;
    }, PAIRED);
    expect(text.match(CODES) ?? [], path).toEqual([]);
  });
}

test("the runs stage table names each stage beside its code", async ({ page }) => {
  await settle(page, "/tracking/runs");
  const cells = await page.locator("tr[data-stage] td:first-child").evaluateAll((tds) =>
    tds.map((td) => [td.closest("tr")!.getAttribute("data-stage"), td.querySelector(".runs-stage-name")?.textContent ?? ""]),
  );
  expect(cells.map(([stage]) => stage)).toEqual(["M1", "M2", "M3", "M4", "M5a", "M5b"]);
  for (const [stage, name] of cells) expect((name ?? "").trim().length, `${stage} has a name`).toBeGreaterThan(5);
});

test("the replay's possession picker reads as words, with the id as its value", async ({ page }) => {
  await page.goto("/tracking/replay?p=bb_possessions_possession-114243-3-79.json");
  const option = page.getByLabel("Possession").locator("option").first();
  await expect(option).toHaveAttribute("value", "bb:possessions:possession-114243-3-79");
  await expect(option).toHaveText(/^Possession 1 of \d+, [\d.]+ s$/);
});
