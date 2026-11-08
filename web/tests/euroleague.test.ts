import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  type Cell,
  cellAt,
  CORNER_TOP,
  COURT,
  courtPaths,
  fade,
  fullAt,
  hexCenter,
  hexPath,
  hexScale,
  type League,
  leagueAverage,
  leagueDrawn,
  MAX_SCALE,
  MIN_FADE,
  MIN_SCALE,
  metresFromHoop,
  pct,
  playerDrawn,
  readingOrder,
  seasonLabel,
  shotSe,
  pointsSe,
  signedPp,
  signedPts,
  type Team,
  teamDrawn,
  toneOf,
  VIEW,
} from "../lib/euroleague/atlas";

// The atlas of /euroleague (task 116): the court, the hexagons and the arithmetic on the published
// aggregates. Mutations checked by hand, each restored byte for byte:
// - `hexCenter` with `q + r` in place of `q + r / 2`: "inverts it" fails.
// - `playerDrawn` subtracting the other way (league minus player): "a player's diff" fails.
// - `teamDrawn` against the whole league (no leave-one-out): "a team's diff" fails.
// - `fade` returning 1 always, or without the floor: "fades" tests fail.
// - `toneOf` without the three-decimal grid: "a cut point belongs to the side away from 0" fails.

const DATA = join(process.cwd(), "public", "data", "euroleague");
const league = JSON.parse(readFileSync(join(DATA, "league.json"), "utf-8")) as League;
const team = (code: string) => JSON.parse(readFileSync(join(DATA, "teams", `${code}.json`), "utf-8")) as Team;

describe("the FIBA half court", () => {
  it("has the measures FIBA sets, in cm from the hoop", () => {
    expect(COURT.three).toBe(675);
    expect(COURT.corner).toBe(660);
    expect(2 * COURT.keyHalfWidth).toBe(490);
    expect(COURT.keyLength).toBe(580);
    expect(2 * COURT.halfWidth).toBe(1500);
    expect(COURT.midline - COURT.baseline).toBe(1400);
    // The corner lines run 2.99 m from the baseline before they meet the arc.
    expect(CORNER_TOP - COURT.baseline).toBeCloseTo(299, 0);
  });

  it("draws the arc from corner to corner through 6.75 m, with y up on screen", () => {
    const { lines, outline } = courtPaths();
    expect(lines).toContain(`M-660,157.5V-141.5A675,675 0 0 1 660,-141.5V157.5`);
    expect(outline).toBe("M-750,157.5H750V-1242.5H-750Z");
  });

  it("frames every published cell, at full size, inside the view", () => {
    const side = league.hex.side_m * 100;
    const all: Cell[] = league.seasons.flatMap((s) => s.cells);
    for (const code of readdirSync(join(DATA, "teams")).map((f) => f.replace(".json", ""))) {
      for (const s of team(code).seasons) {
        all.push(...s.cells.map((c) => c.slice(0, 5) as Cell), ...s.players.flatMap((p) => p.cells));
      }
    }
    const radius = side * MAX_SCALE;
    for (const [q, r] of all) {
      const [x, y] = hexCenter(q, r, side);
      expect(x - radius).toBeGreaterThanOrEqual(VIEW.x);
      expect(x + radius).toBeLessThanOrEqual(VIEW.x + VIEW.width);
      expect(-y - radius).toBeGreaterThanOrEqual(VIEW.y);
      expect(-y + radius).toBeLessThanOrEqual(VIEW.y + VIEW.height);
    }
  });
});

describe("the hexagons", () => {
  it("finds a point's cell as aggregates.py's hex_cell does", () => {
    // [x, y, q, r] printed by `hex_cell(x, y, 100.0)` in the pipeline.
    const python = [
      [0, 0, 0, 0], [0, 74, 0, 0], [0, 76, 0, 0], [86.6, 50, 0, 0], [-300, 610, -4, 4],
      [660, 100, 3, 1], [-700, 141, -5, 1], [12.5, -150, 1, -1], [250, 1260, -3, 9], [0, 675, -2, 4],
    ];
    for (const [x, y, q, r] of python) expect(cellAt(x, y, 100), `${x}, ${y}`).toEqual([q, r]);
  });

  it("inverts it: a cell's centre falls in that cell", () => {
    for (const [q, r] of league.seasons[0].cells) {
      const [x, y] = hexCenter(q, r, 100);
      expect(cellAt(x, y, 100)).toEqual([q, r]);
    }
  });

  it("puts the rim cell on the hoop and draws six corners", () => {
    expect(hexCenter(0, 0, 100)).toEqual([0, 0]);
    const d = hexPath(0, 0, 100);
    expect(d.match(/[ML]/g)).toHaveLength(6);
    expect(d.startsWith("M0,-100L")).toBe(true);
  });

  it("sizes by volume, between a floor and a full size", () => {
    expect(hexScale(5, 500)).toBeCloseTo(MAX_SCALE * MIN_SCALE);
    expect(hexScale(500, 500)).toBeCloseTo(MAX_SCALE);
    expect(hexScale(5000, 500)).toBeCloseTo(MAX_SCALE);
    expect(hexScale(125, 500)).toBeCloseTo(MAX_SCALE * 0.5);
    expect(fullAt([])).toBe(1);
    expect(fullAt([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])).toBe(10);
  });

  it("reads top to bottom, then left to right", () => {
    const cells = leagueDrawn([[0, 0, 9, 1, 2], [-1, 3, 9, 1, 2], [2, 3, 9, 1, 2]]);
    expect(readingOrder(cells).map((c) => [c.q, c.r])).toEqual([[-1, 3], [2, 3], [0, 0]]);
  });
});

describe("against the league", () => {
  const season = league.seasons[0];

  it("the league's cells: points per shot against its average over the cells shown", () => {
    const avg = leagueAverage(season.cells);
    const shown = season.cells.reduce((s, c) => s + c[2], 0);
    expect(shown).toBe(season.shots_shown);
    const rim = leagueDrawn(season.cells).find((c) => c.q === 0 && c.r === 0)!;
    const cell = season.cells.find((c) => c[0] === 0 && c[1] === 0)!;
    expect(rim.diff).toBeCloseTo(cell[4] / cell[2] - avg, 3);
  });

  it("a team's diff is its % minus the rest of the league's, not the league's with the team in it", () => {
    const mad = team("MAD").seasons.find((s) => s.season === season.season)!;
    const drawn = teamDrawn(mad.cells, season.cells);
    let moved = 0;
    for (const [i, c] of mad.cells.entries()) {
      const l = season.cells.find((x) => x[0] === c[0] && x[1] === c[1])!;
      const rest = (l[3] - c[3]) / (l[2] - c[2]);
      expect(drawn[i].league).toBeCloseTo(rest, 12);
      expect(Math.abs(drawn[i].diff - (c[3] / c[2] - rest))).toBeLessThanOrEqual(0.0005 + 1e-9);
      if (drawn[i].diff !== c[5]) moved += 1;
    }
    // The JSON's diff still compares with the whole league, as the pipeline wrote it.
    expect(moved).toBeGreaterThan(0);
  });

  it("when nothing is left of the league's cell, the whole league's % stands", () => {
    const [d] = teamDrawn([[0, 0, 10, 5, 10, 0.1]], [[0, 0, 10, 4, 8]]);
    expect(d.league).toBeCloseTo(0.4);
    expect(d.diff).toBe(0.1);
  });

  it("a player's diff: his % minus the rest of the league's in the same cell, every cell kept", () => {
    const mad = team("MAD").seasons.find((s) => s.season === season.season)!;
    const p = mad.players[0];
    const drawn = playerDrawn(p.cells, season.cells);
    expect(drawn).toHaveLength(p.cells.length);
    const c = p.cells[0];
    const l = season.cells.find((x) => x[0] === c[0] && x[1] === c[1])!;
    const rest = (l[3] - c[3]) / (l[2] - c[2]);
    expect(drawn[0].diff).toBeCloseTo(c[3] / c[2] - rest, 3);
    expect(Math.sign(drawn[0].diff)).toBe(Math.sign(c[3] / c[2] - rest));
  });

  it("a cut point belongs to the side away from 0", () => {
    expect(toneOf(0.1, "fg")).toBe("hi");
    expect(toneOf(0.099, "fg")).toBe("up");
    expect(toneOf(0.03, "fg")).toBe("up");
    expect(toneOf(0.029, "fg")).toBe("mid");
    expect(toneOf(0, "fg")).toBe("mid");
    expect(toneOf(-0.029, "fg")).toBe("mid");
    expect(toneOf(-0.03, "fg")).toBe("down");
    expect(toneOf(-0.1, "fg")).toBe("lo");
    // 0.59 - 0.56 is 0.029999999999999916 in floating point: on the JSON's grid it is 0.03, "up".
    expect(toneOf(0.59 - 0.56, "fg")).toBe("up");
    expect(toneOf(0.2, "pps")).toBe("hi");
    expect(toneOf(-0.05, "pps")).toBe("down");
  });
});

describe("the printed figures", () => {
  it("labels seasons and signs differences", () => {
    expect(seasonLabel("E2025")).toBe("2025-26");
    expect(seasonLabel("E2099")).toBe("2099-00");
    expect(signedPp(0.039)).toBe("+3.9 pp");
    expect(signedPp(-0.411)).toBe("−41.1 pp");
    expect(signedPp(0)).toBe("0.0 pp");
    expect(signedPts(0.6912)).toBe("+0.69");
    expect(signedPts(-0.004)).toBe("0.00");
    expect(pct(3576, 4002)).toBe("89.4%");
    expect(metresFromHoop(0, 0, 100)).toBe("0.0");
    // (-2, 4) sits straight up the middle, 4 rows of 1.5 m.
    expect(metresFromHoop(-2, 4, 100)).toBe("6.0");
  });
});

describe("how sure a hexagon's colour is", () => {
  it("the error of a % shrinks with the shots and is never 0", () => {
    expect(shotSe(0, 5)).toBeGreaterThan(0);
    expect(shotSe(5, 5)).toBeGreaterThan(0);
    expect(shotSe(50, 100)).toBeCloseTo(Math.sqrt((51 / 102) * (51 / 102) / 102), 12);
    expect(shotSe(5, 10)).toBeGreaterThan(shotSe(50, 100));
    // Points a shot: a make is worth pts/made.
    expect(pointsSe(10, 30, 20)).toBeCloseTo(3 * shotSe(10, 20), 12);
    expect(pointsSe(0, 0, 20)).toBeCloseTo(2 * shotSe(0, 20), 12);
  });

  it("fades with the error, between a floor and the full colour", () => {
    expect(fade(0.01, "fg")).toBe(1);
    expect(fade(0.05, "fg")).toBe(1); // half the 10 pp cut: still full
    expect(fade(0.0625, "fg")).toBeCloseTo(0.8);
    expect(fade(0.5, "fg")).toBe(MIN_FADE);
    expect(fade(0.1, "pps")).toBe(1);
    expect(fade(0.4, "pps")).toBe(MIN_FADE);
    expect(fade(0, "fg")).toBe(1);
  });

  it("the files' cells of fewer than 10 shots that reach full colour fade", () => {
    let faded = 0;
    for (const code of readdirSync(join(DATA, "teams")).map((f) => f.replace(".json", ""))) {
      for (const s of team(code).seasons) {
        const lg = league.seasons.find((x) => x.season === s.season)!;
        for (const c of teamDrawn(s.cells, lg.cells)) {
          if (c.n < 10 && toneOf(c.diff, "fg") !== "mid") {
            expect(fade(c.se, "fg")).toBeLessThan(1);
            faded += 1;
          }
        }
      }
    }
    expect(faded).toBeGreaterThan(0);
  });
});
