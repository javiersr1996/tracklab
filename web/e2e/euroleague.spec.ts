import { expect, type Page, type Request, test } from "@playwright/test";
import { headerLinks, whole } from "./header";
import type { League, Team } from "../lib/euroleague/atlas";
import type { Pair, Runs } from "../lib/euroleague/runs";

// /euroleague (task 116): every figure against the published aggregates, the one file a team
// asks for, nothing of euroleague.net, a phone, reduced motion and the attribution.

// Printed here, not imported from the page's helpers, so a broken helper cannot agree with itself.
const pct = (made: number, n: number) => `${((made / n) * 100).toFixed(1)}%`;
const signedPp = (d: number) => `${d > 0 ? "+" : d < 0 ? "−" : ""}${Math.abs(d * 100).toFixed(1)} pp`;
const wholePct = (share: number) => `${Math.round(share * 100)}%`;

const league = async (page: Page) =>
  (await (await page.request.get("/data/euroleague/league.json")).json()) as League;
const team = async (page: Page, code: string) =>
  (await (await page.request.get(`/data/euroleague/teams/${code}.json`)).json()) as Team;

// Point at a hexagon of the court and read what the readout says.
async function hover(page: Page, q: number, r: number) {
  const hex = page.locator(`.el-hex[data-q="${q}"][data-r="${r}"]`);
  await hex.scrollIntoViewIfNeeded();
  const box = (await hex.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await expect(page.locator("[data-readout]")).toHaveAttribute("data-readout", `${q},${r}`);
}

test("the head panel and a hexagon's readout are league.json's", async ({ page }) => {
  await page.goto("/euroleague");
  const data = await league(page);
  for (const s of data.seasons) {
    const share = Math.round((s.zones.three.n / s.shots_total) * 1000) / 10;
    // Counted up, then landed on the file's numbers.
    await expect(page.locator(`[data-panel="${s.season}-shots"]`)).toHaveText(s.shots_total.toLocaleString("en-US"));
    await expect(page.locator(`[data-panel="${s.season}-games"]`)).toHaveText(String(s.games_played));
    await expect(page.locator(`[data-panel="${s.season}-threes"]`)).toHaveText(`${share}%`);
    await expect(page.locator(`[data-panel="${s.season}-cutoff"]`)).toHaveText(s.cutoff);
  }
  await expect.poll(() => page.locator("[data-panel] [data-count]").evaluateAll((els) => els.every((e) => e.getAttribute("data-count") === "done")), {
    timeout: 10_000,
  }).toBe(true);

  // The league by default, the first season: the rim cell's shots, % and points a shot.
  const first = data.seasons[0];
  await expect(page.locator(".el-hex")).toHaveCount(first.cells.length);
  const [q, r, n, made, pts] = first.cells.find((c) => c[0] === 0 && c[1] === 0)!;
  await hover(page, q, r);
  await expect(page.locator("[data-readout-n]")).toHaveText(`${n.toLocaleString("en-US")} shots`);
  await expect(page.locator("[data-readout-pct]")).toHaveText(`${pct(made, n)} made`);
  await expect(page.locator("[data-readout-diff]")).toContainText(`${(pts / n).toFixed(2)} points a shot`);
  const shown = first.cells.reduce((s, c) => s + c[2], 0);
  const average = first.cells.reduce((s, c) => s + c[4], 0) / shown;
  await expect(page.locator("[data-readout-diff]")).toContainText(`against the league's ${average.toFixed(2)}`);
  await expect(page.locator("[data-caption]")).toContainText(
    `${first.shots_shown.toLocaleString("en-US")} of ${first.shots_total.toLocaleString("en-US")} field goals`,
  );

  // A team: its cell's % against the rest of the league's in that cell (the league's without the
  // team's own shots), with the error beside it.
  await page.locator("#el-team").selectOption("MAD");
  await expect(page.locator(".el-atlas")).toHaveAttribute("data-view", `${first.season}|MAD|`);
  const mad = (await team(page, "MAD")).seasons.find((s) => s.season === first.season)!;
  await expect(page.locator(".el-hex")).toHaveCount(mad.cells.length);
  const cell = mad.cells.find((c) => c[0] === 0 && c[1] === 1)!;
  const lc = first.cells.find((c) => c[0] === 0 && c[1] === 1)!;
  const rest = (lc[3] - cell[3]) / (lc[2] - cell[2]);
  const p1 = (cell[3] + 1) / (cell[2] + 2);
  const se = Math.sqrt((p1 * (1 - p1)) / (cell[2] + 2));
  await hover(page, cell[0], cell[1]);
  await expect(page.locator("[data-readout-n]")).toHaveText(`${cell[2].toLocaleString("en-US")} shots`);
  await expect(page.locator("[data-readout-diff]")).toHaveText(
    `${signedPp(Math.round((cell[3] / cell[2] - rest) * 1000) / 1000)} (±${(se * 100).toFixed(1)} pp) against the league's ${(rest * 100).toFixed(1)}% here`,
  );
});

test("choosing a team asks for its file and nothing else; nothing goes to euroleague.net", async ({ page }) => {
  const all: string[] = [];
  page.on("request", (r: Request) => all.push(r.url()));
  await page.goto("/euroleague");
  await page.waitForLoadState("networkidle");
  expect(all.filter((u) => u.includes("/data/euroleague/")), "no aggregate fetched before a click").toEqual([]);

  const after = all.length;
  await page.locator("#el-team").selectOption("PAN");
  await expect(page.locator(".el-atlas")).toHaveAttribute("data-view", /\|PAN\|$/);
  // A player and the other season come from the same file: no request.
  await page.locator("#el-player").selectOption({ index: 1 });
  await page.getByRole("button", { name: "2026-27" }).click();
  await page.locator("#el-team").selectOption("BAR");
  await expect(page.locator(".el-atlas")).toHaveAttribute("data-view", /\|BAR\|/);
  // Back to a team already fetched: no second request.
  await page.locator("#el-team").selectOption("PAN");
  await expect(page.locator(".el-atlas")).toHaveAttribute("data-view", /\|PAN\|/);
  await page.waitForLoadState("networkidle");
  const asked = all.slice(after).map((u) => new URL(u).pathname);
  expect(asked).toEqual(["/data/euroleague/teams/PAN.json", "/data/euroleague/teams/BAR.json"]);
  expect(all.filter((u) => new URL(u).hostname.endsWith("euroleague.net"))).toEqual([]);
});

test("the season under way says how far it is, and the strip lights the team chosen", async ({ page }) => {
  await page.goto("/euroleague");
  const data = await league(page);
  const now = data.seasons.find((s) => s.season === "E2026")!;
  let players = 0;
  let withPlayers = 0;
  let min = 0;
  for (const t of now.teams) {
    const file = await team(page, t.code);
    const n = file.seasons.find((s) => s.season === "E2026")!.players.length;
    players += n;
    if (n > 0) withPlayers += 1;
    min = file.player_min_shots;
  }
  await page.getByRole("button", { name: "2026-27" }).click();
  const note = page.locator('[data-note="in-progress"]');
  await expect(note).toContainText(`${now.games_played} games through ${now.cutoff}`);
  await expect(note).toContainText(`${players} players have reached ${min} shots`);
  // "so only n of m teams ..." is there exactly while some team has no player hexagons yet.
  const tail = `so only ${withPlayers} of ${now.teams.length} teams have player hexagons yet`;
  if (withPlayers < now.teams.length) await expect(note).toContainText(tail);
  else await expect(note).not.toContainText("so only");
  await expect(page.locator(".el-hex")).toHaveCount(now.cells.length);

  await page.locator("#el-team").selectOption("MAD");
  const card = page.locator('[data-change-team="MAD"]');
  await expect(card).toHaveAttribute("data-selected", "true");
  await expect(page.locator(".el-change").first()).toHaveAttribute("data-change-team", "MAD");
  await expect(page.locator(".el-change[data-selected]")).toHaveCount(1);
  for (const c of (await team(page, "MAD")).changes) {
    for (const zone of ["rim", "mid", "three"] as const) {
      await expect(card.locator(`[data-bar="${c.season}"] [data-zone="${zone}"]`)).toHaveText(wholePct(c[zone].share));
    }
  }
});

// "Runs and comebacks" (task 118): the lists and the cards against runs.json, in each season, for the
// team chosen, on a phone. The expectations are built here from the file, not from the page's helpers.
const runsFile = async (page: Page) => (await (await page.request.get("/data/euroleague/runs.json")).json()) as Runs;
const dash = ([own, rival]: Pair) => `${own}–${rival}`;

async function streaksMatch(page: Page, file: Runs, data: League, season: string) {
  const block = file.seasons.find((s) => s.season === season)!;
  const names = Object.fromEntries(data.seasons.flatMap((s) => s.teams.map((t) => [t.code, t.name])));
  const strip = page.locator(`[data-streaks="${season}"]`);
  await expect(strip).toContainText(`${block.games_read} games read, through ${block.cutoff}`);
  await expect(strip).toContainText(`top ${file.top} of the season`);
  const rows = [
    { id: "runs", list: block.runs.map((r) => ({ ...r, size: r.size, text: `from ${dash(r.from)} to ${dash(r.to)}` })) },
    {
      id: "comebacks",
      list: block.comebacks.map((c) => ({ ...c, size: c.deficit, text: `trailed ${dash(c.at)}, won ${dash(c.final)}` })),
    },
  ];
  for (const { id, list } of rows) {
    const items = strip.locator(`[data-ranking="${id}"] > li`);
    await expect(items).toHaveCount(list.length);
    for (const [i, r] of list.entries()) {
      const item = items.nth(i);
      const place = 1 + list.filter((o) => o.size > r.size).length;
      await expect(item).toHaveAttribute("data-rank-team", r.team);
      await expect(item.locator(".el-rank-place")).toHaveText(String(place));
      await expect(item.locator("[data-rank-size]")).toContainText(String(r.size));
      await expect(item.locator(".el-rank-who")).toHaveText(`${names[r.team]} against ${names[r.opp]}`);
      await expect(item.locator(".el-rank-meta")).toHaveText(`${r.date}, ${r.text}`);
    }
  }
  await expect(strip.locator("[data-streak-team]")).toHaveCount(block.teams.length);
  for (const t of block.teams) {
    const card = strip.locator(`[data-streak-team="${t.code}"]`);
    await expect(card.locator(".el-streak-name")).toHaveText(names[t.code]);
    for (const key of ["best_run", "runs_n", "comeback_for", "comeback_against", "wins_from_n"] as const) {
      await expect(card.locator(`[data-stat="${key}"]`)).toHaveText(String(t[key]));
    }
  }
  return block;
}

test("runs and comebacks: the lists and the cards are runs.json's, in each season", async ({ page }) => {
  await page.goto("/euroleague");
  const [file, data] = await Promise.all([runsFile(page), league(page)]);
  const strip = page.locator(".el-streaks-band");
  await expect(strip).toContainText(`from ${file.run_min} points in a row`);
  await expect(strip).toContainText(`from ${file.deficit_min} points behind`);
  const first = await streaksMatch(page, file, data, data.seasons[0].season);
  expect(first.runs.length, "the top 10 and its ties").toBeGreaterThanOrEqual(file.top);
  await page.getByRole("button", { name: "2026-27" }).click();
  await streaksMatch(page, file, data, "E2026");
});

test("runs and comebacks: the team chosen comes first, lit, and so do its rows", async ({ page }) => {
  await page.goto("/euroleague");
  const [file, data] = await Promise.all([runsFile(page), league(page)]);
  await page.locator("#el-team").selectOption("OLY");
  const block = file.seasons.find((s) => s.season === data.seasons[0].season)!;
  const card = page.locator('[data-streak-team="OLY"]');
  await expect(card).toHaveAttribute("data-selected", "true");
  await expect(page.locator(".el-streak-team").first()).toHaveAttribute("data-streak-team", "OLY");
  await expect(page.locator(".el-streak-team[data-selected]")).toHaveCount(1);
  const oly = block.teams.find((t) => t.code === "OLY")!;
  await expect(card.locator('[data-stat="best_run"]')).toHaveText(String(oly.best_run));
  const lit = block.runs.filter((r) => r.team === "OLY").length + block.comebacks.filter((c) => c.team === "OLY").length;
  expect(lit, "OLY is in a top list, so the rows can be lit").toBeGreaterThan(0);
  await expect(page.locator(".el-rank-row[data-selected]")).toHaveCount(lit);
  const litBy = await page.locator(".el-rank-row[data-selected]").evaluateAll((els) => els.map((e) => e.getAttribute("data-rank-team")));
  expect(litBy, "a row is lit by the team that did it, not by its rival").toEqual(Array(lit).fill("OLY"));
  // Another team, and no team: nothing stays lit.
  await page.locator("#el-team").selectOption("BAR");
  await expect(page.locator(".el-streak-team").first()).toHaveAttribute("data-streak-team", "BAR");
  await page.locator("#el-team").selectOption("");
  await expect(page.locator(".el-streak-team[data-selected]")).toHaveCount(0);
  await expect(page.locator(".el-rank-row[data-selected]")).toHaveCount(0);
  // Without a team the cards go by the biggest run, the greatest first.
  const best = await page.locator('[data-stat="best_run"]').allTextContents();
  expect(best.map(Number)).toEqual([...best.map(Number)].sort((a, b) => b - a));
});

test("runs and comebacks on a phone: no sideways scroll, text of 16 px or more, ties kept", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/euroleague");
  const strip = page.locator(".el-streaks-band");
  await strip.scrollIntoViewIfNeeded();
  const m = await page.evaluate(() => {
    const band = document.querySelector(".el-streaks-band")!;
    const small = [...band.querySelectorAll("*")]
      .filter((e) => [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim() !== ""))
      .filter((e) => parseFloat(getComputedStyle(e).fontSize) < 16)
      .map((e) => e.className || e.tagName);
    const wide = [...band.querySelectorAll("*")].filter((e) => e.getBoundingClientRect().right > innerWidth + 0.5);
    return {
      page: document.documentElement.scrollWidth,
      width: innerWidth,
      small,
      wide: wide.map((e) => e.className || e.tagName),
    };
  });
  expect(m.page).toBeLessThanOrEqual(m.width);
  expect(m.small).toEqual([]);
  expect(m.wide).toEqual([]);
});

test("the keyboard steps through the hexagons with a visible focus", async ({ page }) => {
  await page.goto("/euroleague");
  const court = page.locator(".el-court");
  // From the team picker, Tab skips the player picker (disabled until a team) and lands on the court.
  await page.locator("#el-team").focus();
  await page.keyboard.press("Tab");
  await expect(court).toBeFocused();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("[data-readout]")).not.toHaveAttribute("data-readout", "none");
  const outline = await court.evaluate((e) => getComputedStyle(e).outlineStyle);
  expect(outline).toBe("solid");
  await expect(page.locator(".el-hex-active")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.locator("[data-readout]")).toHaveAttribute("data-readout", "none");
});

test("under prefers-reduced-motion nothing moves: figures still, hexagons placed at once", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/euroleague");
  // Hydrated, the figures read the media query and stay still (the server's HTML says "idle").
  const counts = page.locator("[data-panel] [data-count]");
  await expect(counts).toHaveCount(6);
  await expect.poll(() => counts.evaluateAll((els) => els.every((e) => e.getAttribute("data-count") === "still"))).toBe(true);
  await page.locator("#el-team").selectOption("MAD");
  await expect(page.locator(".el-atlas")).toHaveAttribute("data-view", /\|MAD\|/);
  expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
});

test("with motion allowed, a new selection's hexagons do enter (the check above can fail)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/euroleague");
  await page.locator("#el-team").selectOption("MAD");
  await expect(page.locator(".el-atlas")).toHaveAttribute("data-view", /\|MAD\|/);
  const entering = await page.evaluate(
    () => document.getAnimations().filter((a) => (a.effect as KeyframeEffect | null)?.target?.classList.contains("el-hex")).length,
  );
  expect(entering).toBeGreaterThan(0);
});

test("the attribution: source, no affiliation, aggregates only, and the removal contact", async ({ page }) => {
  await page.goto("/euroleague");
  const data = await league(page);
  await expect(page.locator('[data-attribution="source"]')).toContainText("Data: EuroLeague (live.euroleague.net)");
  await expect(page.locator('[data-attribution="source"] a')).toHaveAttribute("href", "https://www.euroleaguebasketball.net/euroleague/");
  await expect(page.locator('[data-attribution="affiliation"]')).toHaveText("Not affiliated with EuroLeague.");
  await expect(page.locator('[data-attribution="aggregates"]')).toContainText(
    `aggregates only: a count of shots, makes and points per hexagon, never a shot, and a hexagon with fewer than ${data.hex.k} shots is dropped`,
  );
  const removal = page.locator('[data-attribution="removal"]');
  await expect(removal).toHaveText("Removal requests: javiersr1996+tracklab@gmail.com.");
  await expect(removal.locator("a")).toHaveAttribute("href", "mailto:javiersr1996+tracklab@gmail.com");
  // The footer gives EuroLeague its own note; the MIT sentence names SkillCorner's sources only.
  const footer = page.locator(".site-footer");
  await expect(footer.locator('[data-footer-source="euroleague"]')).toContainText("no open license");
  await expect(footer.getByText("Not affiliated with EuroLeague.")).toBeVisible();
  const mit = await footer.locator("p", { hasText: "MIT license" }).first().textContent();
  expect(mit).not.toContain("EuroLeague");
});

test("/euroleague is light: under 400,000 B before a team is chosen", async ({ page }) => {
  const requests: Request[] = [];
  page.on("requestfinished", (r) => requests.push(r));
  await page.goto("/euroleague");
  await page.waitForLoadState("networkidle");
  let transferred = 0;
  for (const r of requests) {
    const sizes = await r.sizes();
    transferred += sizes.responseBodySize + sizes.responseHeadersSize;
  }
  console.log(`/euroleague: ${transferred} bytes transferred`);
  expect(transferred).toBeLessThan(400_000);
});

test("the ninth section: in the header, on the home page and in the sitemap", async ({ page }) => {
  await page.goto("/");
  const card = page.locator('[data-section="/euroleague"]');
  await expect(card).toBeVisible();
  await expect(page.locator(".cards > li")).toHaveCount(9);
  await card.getByRole("link").click();
  await expect(page).toHaveURL(/\/euroleague$/);
  const nav = page.getByRole("navigation", { name: "Sections" });
  await expect(nav.getByRole("link", { name: "EuroLeague" })).toHaveAttribute("aria-current", "page");
  await expect(nav.locator("[aria-current]")).toHaveCount(1);
  const xml = await (await page.request.get("/sitemap.xml")).text();
  expect(xml).toContain("<loc>https://tracklab-sable.vercel.app/euroleague</loc>");
  const og = await page.request.get("/euroleague/opengraph-image");
  expect(og.status()).toBe(200);
  expect(og.headers()["content-type"]).toBe("image/png");
});

for (const width of [390, 1000, 1200, 1440]) {
  test(`at ${width} px: the six header links neither overlap nor overflow; no sideways scroll; text 16 px or more`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/euroleague");
    await page.waitForLoadState("networkidle");
    const sideways = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(sideways, "page wider than the window by").toBeLessThanOrEqual(0);
    // The five sections and About (P21: Learn holds the SQL course). On a phone they are a strip
    // that scrolls: its box stays in the window, and a link past its edge is hidden in it.
    const links = (await headerLinks(page)).slice(1);
    expect(links).toHaveLength(6);
    for (const [i, a] of links.entries()) {
      expect(a.strip!.x, `link ${i}'s row starts inside the window`).toBeGreaterThanOrEqual(0);
      expect(a.strip!.r, `link ${i}'s row ends inside the window`).toBeLessThanOrEqual(width);
      if (!whole(a)) expect(a.strip!.scrolls && width < 640, `link ${i} cut by a row that does not scroll`).toBe(true);
      if (a.current) expect(whole(a), "EuroLeague in view").toBe(true);
      for (const b of links.slice(i + 1)) {
        if (a.shownR <= a.shownX || b.shownR <= b.shownX) continue; // scrolled out of view
        expect(a.shownX < b.shownR && b.shownX < a.shownR && a.y < b.b && b.y < a.b, `header link ${i} overlaps another`).toBe(false);
      }
    }
    const small = await page.evaluate(() =>
      Array.from(document.querySelectorAll("main *"))
        .filter((el) => Array.from(el.childNodes).some((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== ""))
        .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
        .map((el) => `${el.tagName.toLowerCase()} ${getComputedStyle(el).fontSize}`),
    );
    expect(small, "text under 16 px").toEqual([]);
    // The court fills its column, and it is all on the page.
    const court = (await page.locator(".el-court").boundingBox())!;
    expect(court.x).toBeGreaterThanOrEqual(0);
    expect(court.x + court.width).toBeLessThanOrEqual(width);
  });
}
