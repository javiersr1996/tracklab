import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { MARKS } from "../components/learn/coordinates/FrameFigure";
import { EXTERNAL_EDGE, SCHEMA_COLOR } from "../components/platform/Lineage";
import { BASE_COLOR, DATA_COLOR, REAL_COLOR, TRACE_ALPHA } from "../components/quality/Hook";
import { MARKER_COLOR, OTHER_COLOR } from "../components/runs/Hook";
import { RING_COLOR } from "../lib/pose/render";
import { COLORS, DIM_ALPHA } from "../lib/replay/render";

// The colour tokens of globals.css (P13, task 109), read from the file and resolved the way the
// cascade resolves them: the palette in `:root`, the slots in `:root, .surface-neon`, and what the
// alternate band (`.surface-dark`) overrides. WCAG floors: text 4.5:1; a control's edge, a focus
// ring and a mark on the canvas 3:1. The ratios in globals.css's comments are the ones printed here.
//
// Mutations checked by hand, each restored byte for byte:
// - `--neon-muted: #4b5563`: "text" fails (2.66:1 on the page).
// - `--canvas-axis: #334155`: "marks on the canvas" fails (1.94:1).
// - The lineage nodes' resting opacity back at 0.8: "marks drawn in TS" fails (frozen's label 4.23:1).
// - `COLORS.ball` back at #f5c518: "the tokens they name" fails on the replay's ball.
// - `--neon-band` back at #0b1220: "the alternate band reads as a band" fails (1.08:1).
// - `--el-down: #8a2a5c`: "the shot atlas of /euroleague" fails (2.5:1 on the canvas).
// - `--pct-1: #0d6e86`: "the scouting table's percentile steps" fails (2.80:1 on the band).

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

  it("the colours the canvases and SVGs draw with in TS are the tokens they name (task 111)", () => {
    const token = (name: string) => palette[name]?.toLowerCase();
    const mirrors: [string, string, string][] = [
      ["replay COLORS.surface", COLORS.surface, "--canvas-muted"],
      ["replay COLORS.attack", COLORS.attack, "--neon"],
      ["replay COLORS.defence", COLORS.defence, "--neon-alt"],
      ["replay COLORS.ball", COLORS.ball, "--canvas-hi"],
      ["replay COLORS.text", COLORS.text, "--canvas-ink"],
      ["pose RING_COLOR", RING_COLOR, "--canvas-hi"],
      ["coordinates MARKS.surface, the replay's markings", MARKS.surface, "--canvas-muted"],
      ["coordinates MARKS.ball, the replay's ball", MARKS.ball, "--canvas-hi"],
      ["coordinates MARKS.ballEdge, the replay's ball edge", MARKS.ballEdge, "--canvas"],
      ["quality DATA_COLOR", DATA_COLOR, "--neon"],
      ["quality REAL_COLOR", REAL_COLOR, "--neon-alt"],
      ["quality BASE_COLOR", BASE_COLOR, "--canvas-axis"],
      ["runs MARKER_COLOR", MARKER_COLOR, "--canvas-hi"],
      ["runs OTHER_COLOR", OTHER_COLOR, "--neon-ink"],
      ["lineage code", SCHEMA_COLOR.code, "--neon"],
      ["lineage frozen", SCHEMA_COLOR.frozen, "--neon-alt"],
      ["lineage none", SCHEMA_COLOR.none, "--neon-muted"],
      ["lineage EXTERNAL_EDGE", EXTERNAL_EDGE, "--neon-ink"],
    ];
    expect(mirrors.filter(([, ts, name]) => ts.toLowerCase() !== token(name)).map(([what, ts, name]) => `${what} ${ts} is not ${name}`)).toEqual([]);
  });

  it("marks drawn in TS: 3:1 or more on the canvas, as drawn (task 111)", () => {
    const canvas = resolve(page, "--canvas");
    const hex = (h: string): Rgba => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(1) as Rgba;
    const at = (h: string, alpha: number): Rgba => [...hex(h).slice(0, 3), alpha] as Rgba;
    const pairs = [
      ...Object.entries(COLORS)
        .filter(([k]) => !["text", "dimText", "ballEdge"].includes(k))
        .map(([k, c]) => measure(`replay ${k}`, hex(c as string), canvas, 3)),
      measure("quality data's path", at(DATA_COLOR, TRACE_ALPHA), canvas, 3),
      measure("quality standard's path", at(REAL_COLOR, TRACE_ALPHA), canvas, 3),
      measure("quality baseline", hex(BASE_COLOR), canvas, 3),
      measure("runs other arrows", hex(OTHER_COLOR), canvas, 3),
    ];
    // A lineage node at its resting opacity (globals.css) and its dark label on it.
    const rest = Number(css.match(/:not\(\[data-lit\]\) rect\s*\{\s*opacity:\s*([\d.]+)/)?.[1]);
    expect(rest).toBeGreaterThan(0);
    for (const [kind, c] of Object.entries(SCHEMA_COLOR)) {
      const node = over(at(c, rest), canvas);
      pairs.push(measure(`lineage ${kind} node at rest`, node, canvas, 3));
      pairs.push(measure(`lineage ${kind} label at rest`, resolve(page, "--canvas-ink"), node, 4.5));
    }
    pairs.push(measure("jersey number on the other team's disc", hex(COLORS.text), hex(COLORS.defence), 4.5));
    // A player not detected: the disc at DIM_ALPHA over the canvas, the number on top at full alpha.
    for (const team of ["attack", "defence"] as const) {
      const disc = over(at(COLORS[team], DIM_ALPHA), canvas);
      pairs.push(measure(`jersey number of a player not detected, ${team} disc`, hex(COLORS.dimText!), disc, 4.5));
      // The ball's dark edge against a disc it overlaps, and the ball against its edge.
      pairs.push(measure(`ball edge on the ${team} disc`, hex(COLORS.ballEdge!), hex(COLORS[team]), 3));
    }
    pairs.push(measure("ball against its edge", hex(COLORS.ball), hex(COLORS.ballEdge!), 3));
    expect(low(pairs)).toEqual([]);
  });

  it("the shot atlas of /euroleague: its tones, its court and its bars (task 116)", () => {
    const canvas = resolve(page, "--canvas");
    const tones = ["--el-hi", "--el-up", "--el-mid", "--el-down", "--el-lo"];
    const pairs = tones.map((t) => measure(`hexagon ${t} on --canvas`, resolve(page, t), canvas, 3));
    // The legend's swatches sit on the dark band, not on the canvas.
    for (const t of tones) pairs.push(measure(`swatch ${t} on the band`, resolve(band, t), resolve(band, "--bg"), 3));
    pairs.push(measure("the court's lines (--neon-line-strong on --canvas)", resolve(page, "--neon-line-strong"), canvas, 3));
    pairs.push(measure("the active hexagon's edge (--canvas-hi) on --canvas", resolve(page, "--canvas-hi"), canvas, 3));
    // The strip's bars sit in a team card on the page; each share is printed on its own segment.
    for (const seg of ["--canvas-hi", "--canvas-muted", "--neon"]) {
      pairs.push(measure(`bar ${seg} on a page card`, resolve(page, seg), resolve(page, "--raised"), 3));
      pairs.push(measure(`--canvas-ink on the bar ${seg}`, resolve(page, "--canvas-ink"), resolve(page, seg), 4.5));
    }
    expect(low(pairs)).toEqual([]);
  });

  it("the scouting table's percentile steps, its paired bars and its head panel (task 136)", () => {
    const onBand = resolve(band, "--bg");
    const pairs: Pair[] = [];
    // A cell's fill is a mark on the band; its number is text on the fill.
    for (const step of [1, 2, 3, 4]) {
      const fill = resolve(band, `--pct-${step}`);
      pairs.push(measure(`percentile step ${step} on the band`, fill, onBand, 3));
      pairs.push(measure(`--pct-ink-${step} on step ${step}`, resolve(band, `--pct-ink-${step}`), fill, 4.5));
    }
    // The comparison's bars on the band (A cyan, B magenta) and the head panel's on a page card.
    pairs.push(measure("bar A (--neon) on the band", resolve(band, "--neon"), onBand, 3));
    pairs.push(measure("bar B (--neon-alt) on the band", resolve(band, "--neon-alt"), onBand, 3));
    pairs.push(measure("the head panel's bar (--neon) on a page card", resolve(page, "--neon"), resolve(page, "--raised"), 3));
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

  it("the alternate band reads as a band: 1.2:1 to 1.3:1 on the page (task 112)", () => {
    const step = contrast(resolve(band, "--bg"), resolve(page, "--bg"));
    expect(step).toBeGreaterThanOrEqual(1.2);
    expect(step).toBeLessThanOrEqual(1.3);
  });
});
