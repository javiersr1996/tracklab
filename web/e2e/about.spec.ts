import { expect, test } from "@playwright/test";

// P20, task 171: who made the site and what it is not, on /about, in the footer of every route and
// under the home's lede. The addresses are typed here, as the brief gave them, so a wrong constant
// in lib/sections.ts fails here.
const NAME = "Javier Sánchez Rueda";
const LINKEDIN = "https://www.linkedin.com/in/javier-sanchez-rueda/";
const REPO = "https://github.com/javiersr1996/tracklab";
const EMAIL = "javiersr1996@gmail.com";
const TAKEDOWN = "javiersr1996+tracklab@gmail.com";

const DISCLAIMER = [
  "Track Lab is a personal, non-commercial project built for learning.",
  "It is not affiliated with, endorsed by or sponsored by SkillCorner, EuroLeague Basketball or any league, club or player named on this site.",
  "All trademarks, names and data belong to their respective owners.",
  "SkillCorner's open data is used under its MIT license; of EuroLeague game data only aggregates are shown.",
  "The figures here are produced for educational purposes, may contain errors, and are not professional advice nor an assessment of any player or team.",
  `If you hold rights in anything shown here and want it corrected or removed, write to ${TAKEDOWN} and it will be taken down.`,
];

test("/about names the author, links to him and to the code, and prints the stack and the disclaimer", async ({ page }) => {
  await page.goto("/about");
  await expect(page).toHaveTitle("About | Track Lab");
  await expect(page.locator("h1")).toHaveText("A personal learning project");
  const author = page.locator("[data-about-author]");
  await expect(author).toContainText(NAME);
  await expect(author.getByRole("link", { name: "LinkedIn" })).toHaveAttribute("href", LINKEDIN);
  await expect(author.getByRole("link", { name: "GitHub repository" })).toHaveAttribute("href", REPO);
  await expect(author.getByRole("link", { name: EMAIL })).toHaveAttribute("href", `mailto:${EMAIL}`);

  // The versions are the ones /engineering prints, from the same files.
  const platform = (await (await page.request.get("/data/platform.json")).json()) as { run: { versions: Record<string, string> } };
  const pg = (await (await page.request.get("/data/warehouse_pg.json")).json()) as { source: { version: string } };
  for (const [tool, version] of Object.entries(platform.run.versions)) {
    await expect(page.locator(`[data-stack] [data-tool="${tool}"]`)).toHaveText(`${tool} ${version}`);
  }
  await expect(page.locator('[data-stack] [data-tool="postgres"]')).toHaveText(`Postgres ${pg.source.version}`);

  const disclaimer = page.locator("[data-disclaimer]");
  await expect(disclaimer.getByRole("heading", { level: 2 })).toHaveText("Disclaimer");
  const text = (await disclaimer.textContent())!.replace(/\s+/g, " ");
  for (const sentence of DISCLAIMER) expect(text, sentence).toContain(sentence);
  await expect(disclaimer.getByRole("link", { name: TAKEDOWN })).toHaveAttribute("href", `mailto:${TAKEDOWN}`);

  // Every card's link opens a page that answers, and its #fragment names an element of it.
  const hrefs = await page.locator(".about-cards a").evaluateAll((as) => as.map((a) => a.getAttribute("href")!));
  expect(hrefs.length).toBeGreaterThanOrEqual(7);
  for (const href of hrefs) {
    const [path, id] = href.split("#");
    expect((await page.request.get(path)).status(), href).toBe(200);
    if (id) {
      await page.goto(path);
      await expect(page.locator(`[id="${id}"]`), href).toHaveCount(1);
    }
  }
});

test("the footer of every route says who made it, links to /about, LinkedIn and the code, and what it is not", async ({ page }) => {
  for (const route of ["/", "/about", "/engineering", "/learn/gravity", "/euroleague", "/no-such-page"]) {
    await page.goto(route);
    const author = page.locator("footer.site-footer [data-footer-author]");
    await expect(author, route).toBeVisible();
    await expect(author, route).toContainText(`A personal learning project by ${NAME}`);
    await expect(author.getByRole("link", { name: "About", exact: true })).toHaveAttribute("href", "/about");
    await expect(author.getByRole("link", { name: "/about", exact: true })).toHaveAttribute("href", "/about");
    await expect(author.getByRole("link", { name: "LinkedIn" })).toHaveAttribute("href", LINKEDIN);
    await expect(author.getByRole("link", { name: "GitHub", exact: true })).toHaveAttribute("href", REPO);
    await expect(author, route).toContainText(
      "Non-commercial, built for learning; not affiliated with SkillCorner or EuroLeague. More in /about.",
    );
  }
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1440, height: 900 },
]) {
  test(`the home's byline links to /about inside the first screen at ${viewport.width} px`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    const byline = page.locator(".hero").getByRole("link", { name: `A personal learning project by ${NAME}` });
    await expect(byline).toHaveAttribute("href", "/about");
    const box = (await byline.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    expect(await byline.evaluate((e) => parseFloat(getComputedStyle(e).fontSize))).toBeGreaterThanOrEqual(16);
  });
}

// About joined the header (P20) without a third row of links on a phone: the six sections took two
// rows at 390 px before it, and the seven still do.
test("at 390 px the header's links still take two rows", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/about");
  const tops = await page
    .getByRole("navigation", { name: "Sections" })
    .getByRole("link")
    .evaluateAll((as) => as.map((a) => Math.round(a.getBoundingClientRect().top)));
  expect(tops).toHaveLength(7);
  expect(new Set(tops).size).toBe(2);
  await expect(page.getByRole("navigation", { name: "Sections" }).getByRole("link", { name: "About" })).toHaveAttribute(
    "aria-current",
    "page",
  );
});

test("/about is in the sitemap", async ({ page }) => {
  const xml = await (await page.request.get("/sitemap.xml")).text();
  expect(xml).toContain("<loc>https://tracklab-sable.vercel.app/about</loc>");
});
