import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The colour tokens of globals.css (P13, task 109), read from the file and resolved the way the
// cascade resolves them: the palette in `:root`, the slots in `:root, .surface-neon`, and what the
// alternate band (`.surface-dark`) overrides. WCAG floors: text 4.5:1; a control's edge, a focus
// ring and a mark on the canvas 3:1. The ratios in globals.css's comments are the ones printed here.
//
// Mutations checked by hand, each restored byte for byte:
// - `--neon-muted: #4b5563`: "text" fails (2.66:1 on the page).
// - `--canvas-axis: #334155`: "marks on the canvas" fails (1.94:1).

const css = readFileSync(join(process.cwd(), "app", "globals.css"), "utf-8").replace(/\/\*[\s\S]*?\*\//g, "");

type Decls = Record<string, string>;

// The custom properties of the rules whose selector list is exactly `selectors`.
function rule(...selectors: string[]): Decls {
  const out: Decls = {};
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    const list = m[1].split(",").map((s) => s.trim());
    if (list.length !== selectors.length || list.some((s, i) => s !== selectors[i])) continue;
    for (const d of m[2].matchAll(/(--[\w-]+):\s*([^;]+);/g)) out[d[1]] = d[2].trim();
  }
  if (Object.keys(out).length === 0) throw new Error(`no rule ${selectors.join(", ")} in globals.css`);
  return out;
}

type Rgba = [number, number, number, number];

function resolve(scope: Decls, name: string): Rgba {
  const value = scope[name];
  if (value === undefined) throw new Error(`${name} is not defined`);
  const ref = value.match(/^var\((--[\w-]+)\)$/);
  if (ref) return resolve(scope, ref[1]);
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)).concat(1) as Rgba;
  const rgba = value.match(/^rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)$/);
  if (rgba) return rgba.slice(1).map(Number) as Rgba;
  throw new Error(`${name}: cannot read "${value}" as a colour`);
}

// A translucent colour composited over the opaque one it sits on.
const over = (fg: Rgba, bg: Rgba): Rgba => [0, 1, 2].map((i) => fg[i] * fg[3] + bg[i] * (1 - fg[3])).concat(1) as Rgba;

function luminance([r, g, b]: Rgba): number {
  const lin = (c: number) => ((c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(fg: Rgba, bg: Rgba): number {
  const [hi, lo] = [luminance(over(fg, bg)), luminance(bg)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const palette = rule(":root");
const page: Decls = { ...palette, ...rule(":root", ".surface-neon") };
const band: Decls = { ...page, ...rule(".surface-dark") };

// Each surface: the scope its slots resolve in, and the token that paints it.
const SURFACES = {
  page: [page, "--bg"],
  "page card": [page, "--raised"],
  band: [band, "--bg"],
  "band card": [band, "--raised"],
} as const;

const TEXT = ["--fg", "--fg-strong", "--fg-muted", "--link", "--tag"];

type Pair = { what: string; ratio: number; floor: number };
const rows: Pair[] = [];
const measure = (what: string, fg: Rgba, bg: Rgba, floor: number) => {
  const pair = { what, ratio: contrast(fg, bg), floor };
  rows.push(pair);
  return pair;
};
const low = (pairs: Pair[]) => pairs.filter((p) => p.ratio < p.floor).map((p) => `${p.what} ${p.ratio.toFixed(2)}:1`);

describe("the colour tokens", () => {
  it("text: every slot is 4.5:1 or more on the page, the band and a card on either", () => {
    const pairs = Object.entries(SURFACES).flatMap(([surface, [scope, bg]]) =>
      TEXT.map((t) => measure(`${t} on the ${surface}`, resolve(scope, t), resolve(scope, bg), 4.5)),
    );
    for (const [where, scope] of [["page", page], ["band", band]] as const) {
      pairs.push(measure(`--fg on code, ${where}`, resolve(scope, "--fg"), resolve(scope, "--code-bg"), 4.5));
      pairs.push(measure(`--fg in a control, ${where}`, resolve(scope, "--fg"), resolve(scope, "--control-bg"), 4.5));
    }
    pairs.push(measure("a primary button (--neon-bg on --neon)", resolve(page, "--neon-bg"), resolve(page, "--neon"), 4.5));
    pairs.push(measure("its hover (--neon-bg on --neon-2)", resolve(page, "--neon-bg"), resolve(page, "--neon-2"), 4.5));
    pairs.push(measure("a tick label (--canvas-muted on --canvas)", resolve(page, "--canvas-muted"), resolve(page, "--canvas"), 4.5));
    expect(low(pairs)).toEqual([]);
  });

  it("controls and focus: an edge or a ring is 3:1 or more where it sits", () => {
    const pairs: Pair[] = [];
    for (const [surface, [scope, bg]] of Object.entries(SURFACES)) {
      pairs.push(measure(`--control-line on the ${surface}`, resolve(scope, "--control-line"), resolve(scope, bg), 3));
      pairs.push(measure(`--focus on the ${surface}`, resolve(scope, "--focus"), resolve(scope, bg), 3));
    }
    pairs.push(measure("--control-line on --control-bg", resolve(page, "--control-line"), resolve(page, "--control-bg"), 3));
    expect(low(pairs)).toEqual([]);
  });

  it("marks on the canvas: every token a figure draws with is 3:1 or more", () => {
    const marks = ["--neon", "--neon-alt", "--canvas-hi", "--canvas-muted", "--canvas-edge", "--canvas-axis"];
    const pairs = marks.map((m) => measure(`${m} on --canvas`, resolve(page, m), resolve(page, "--canvas"), 3));
    expect(low(pairs)).toEqual([]);
  });

  it("the band and the cards stand apart from what they sit on (reported, no floor)", () => {
    const steps = [
      measure("the band on the page", resolve(band, "--bg"), resolve(page, "--bg"), 1),
      measure("a card on the page", resolve(page, "--raised"), resolve(page, "--bg"), 1),
      measure("a card on the band", resolve(band, "--raised"), resolve(band, "--bg"), 1),
      measure("the canvas in a band or a figure card", resolve(page, "--canvas"), resolve(band, "--bg"), 1),
    ];
    for (const s of steps) expect(s.ratio).toBeGreaterThan(1);
    console.log(rows.map((r) => `${r.ratio.toFixed(2).padStart(6)}:1  (floor ${r.floor})  ${r.what}`).join("\n"));
  });
});
