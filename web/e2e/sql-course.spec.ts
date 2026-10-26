import { readFileSync } from "node:fs";
import { expect as baseExpect, type Page, test } from "@playwright/test";
import { display } from "../lib/learn/display";

// Task 102, the cross-check of P11: the reference SQL of every exercise of course.json (the count
// comes from the file) typed in its box in the browser must give "Correct", so DuckDB-WASM and
// Python agree on each hash. Then the shape hints, the gate, the progress on the index, a page
// whose localStorage throws, the links in, and every `data-fact` equal to course.json's value.
const expect = baseExpect.configure({ timeout: 20_000 });

type Exercise = { id: string; solution: string };
type Lesson = { slug: string; facts: Record<string, string>; exercises: Exercise[] };
const course = JSON.parse(readFileSync("public/data/sql/course.json", "utf-8")) as { lessons: Lesson[] };
const FIRST = course.lessons[0];
const SELECT1 = FIRST.exercises[0];

// Types `sql` in the box of `id`, runs it and waits for a verdict.
async function run(page: Page, id: string, sql: string) {
  const box = page.locator(`[data-exercise="${id}"]`);
  await box.getByRole("textbox", { name: "SQL" }).fill(sql);
  await box.getByRole("button", { name: "Run", exact: true }).click();
  await expect(box).not.toHaveAttribute("data-state", /^(idle|running)$/, { timeout: 120_000 });
  return {
    box,
    state: await box.getAttribute("data-state"),
    message: ((await box.locator("[data-message]").textContent()) ?? "").trim(),
  };
}

test("course.json has lessons with exercises", () => {
  expect(course.lessons.length).toBeGreaterThan(0);
  expect(course.lessons.every((l) => l.exercises.length >= 2)).toBe(true);
});

for (const lesson of course.lessons) {
  const route = `/sql/${lesson.slug}`;

  test(`${route}: the ${lesson.exercises.length} references give Correct`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.goto(route);
    // The page has one box per exercise of the file.
    await expect(page.locator("[data-exercise]")).toHaveCount(lesson.exercises.length);
    for (const e of lesson.exercises) {
      const r = await run(page, e.id, e.solution);
      expect(r.state, `${e.id}: ${r.message}`).toBe("correct");
      await expect(r.box).toHaveAttribute("data-solved", "true");
    }
  });

  test(`${route}: every data-fact is course.json's value`, async ({ page }) => {
    await page.goto(route);
    const printed = await page
      .locator("[data-fact]")
      .evaluateAll((els) => els.map((el) => [el.getAttribute("data-fact"), el.textContent]));
    console.log(`${route}: ${printed.length} facts printed`);
    expect(printed.length).toBeGreaterThan(0);
    const wrong = printed.filter(([name, shown]) => {
      const value = lesson.facts[name ?? ""];
      return value === undefined || shown !== display(value, name ?? "");
    });
    expect(wrong).toEqual([]);
  });
}

test("/sql/select: wrong queries give the shape hint, the gate stops a DROP", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/sql/${FIRST.slug}`);
  const id = SELECT1.id;
  let r = await run(page, id, "SELECT 1");
  expect(r.state).toBe("columns");
  expect(r.message).toMatch(/3 columns expected, you have 1/);
  r = await run(page, id, "SELECT player_name, team_name, attempts FROM bb_shots ORDER BY attempts DESC LIMIT 12");
  expect(r.state).toBe("rows");
  expect(r.message).toMatch(/11 rows expected, you have 12/);
  r = await run(page, id, "SELECT player_name, team_name, attempts FROM bb_shots ORDER BY attempts LIMIT 11");
  expect(r.state).toBe("values");
  r = await run(page, id, "DROP VIEW bb_shots");
  expect(r.state).toBe("error");
  expect(r.message).toBe("Only SELECT, WITH, EXPLAIN run here.");
  await expect(r.box).not.toHaveAttribute("data-solved", "true");
  // The gate stopped it: the view is still there for the next query.
  r = await run(page, id, SELECT1.solution);
  expect(r.state).toBe("correct");
});

test("a correct answer followed by ; and a comment is still Correct", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto(`/sql/${FIRST.slug}`);
  for (const tail of ["; -- done", ";\n-- fin", "; /* c */"]) {
    const r = await run(page, SELECT1.id, `${SELECT1.solution.trim().replace(/;+$/, "")}${tail}`);
    expect(r.state, `${tail}: ${r.message}`).toBe("correct");
  }
});

test("solving an exercise marks it on the /sql index", async ({ page }) => {
  test.setTimeout(120_000);
  const progress = () => page.locator(`[data-lesson="${FIRST.slug}"] .sql-progress`);
  await page.goto("/sql");
  await expect(progress()).toHaveAttribute("data-solved", "0");
  await page.goto(`/sql/${FIRST.slug}`);
  const r = await run(page, SELECT1.id, SELECT1.solution);
  expect(r.state).toBe("correct");
  await page.goto("/sql");
  await expect(progress()).toHaveAttribute("data-solved", "1");
  await expect(progress()).toHaveText(`1 of ${FIRST.exercises.length} solved`);
  // The other lessons are untouched.
  for (const other of course.lessons.slice(1)) {
    await expect(page.locator(`[data-lesson="${other.slug}"] .sql-progress`)).toHaveAttribute("data-solved", "0");
  }
});

test("the page works when localStorage throws", async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // The init script runs before `document.documentElement` exists: it only redefines the property.
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("blocked", "SecurityError");
      },
    });
  });
  await page.goto("/sql");
  await expect(page.locator(`[data-lesson="${FIRST.slug}"] .sql-progress`)).toHaveText(new RegExp(`^0 of ${FIRST.exercises.length} solved$`));
  await page.goto(`/sql/${FIRST.slug}`);
  const r = await run(page, SELECT1.id, SELECT1.solution);
  expect(r.state).toBe("correct");
  await expect(r.box).toHaveAttribute("data-solved", "true");
  expect(errors).toEqual([]);
});

test("/warehouse, /learn and / link to /sql", async ({ page }) => {
  await page.goto("/warehouse");
  await expect(page.getByRole("link", { name: "Learn SQL on these tables" })).toHaveAttribute("href", "/sql");
  await page.goto("/learn");
  await expect(page.getByRole("link", { name: "Learn SQL on the warehouse" })).toHaveAttribute("href", "/sql");
  await page.goto("/");
  await expect(page.locator('a.card-more[href="/sql"]')).toHaveCount(1);
  await page.locator("a.card-more").click();
  await expect(page).toHaveURL(/\/sql$/);
});
