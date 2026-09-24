import { describe, expect, it } from "vitest";
import { drawSurface, type Primitive, surfacePrimitives, type SurfaceContext } from "../lib/geometry";
import type { Surface } from "../lib/replay/types";

const FIBA: Surface = { spec: "fiba_28x15", length_m: 28, width_m: 15 };
const PITCHES: Surface[] = [
  { spec: "provider_105x68", length_m: 105, width_m: 68 },
  { spec: "provider_104x68", length_m: 104, width_m: 68 },
];
const EPS = 1e-9;

// Points that bound a primitive: arcs are sampled, since their extent depends on the angles.
function extent(p: Primitive): [number, number][] {
  switch (p.kind) {
    case "line":
      return [
        [p.x1, p.y1],
        [p.x2, p.y2],
      ];
    case "rect":
      return [
        [p.x, p.y],
        [p.x + p.w, p.y + p.h],
      ];
    case "circle":
      return [
        [p.cx - p.r, p.cy - p.r],
        [p.cx + p.r, p.cy + p.r],
      ];
    case "arc":
      return Array.from({ length: 101 }, (_, k) => {
        const a = p.start + ((p.end - p.start) * k) / 100;
        return [p.cx + p.r * Math.cos(a), p.cy + p.r * Math.sin(a)] as [number, number];
      });
  }
}

function recorder() {
  const calls: string[] = [];
  const ctx = new Proxy({} as SurfaceContext, {
    get: (_, name: string) => () => calls.push(name),
  });
  return { ctx, calls };
}

describe("surface geometry", () => {
  it("puts the hoops 1.575 m inside each baseline", () => {
    const hoops = surfacePrimitives(FIBA).filter((p) => "role" in p && p.role === "hoop");
    const xs = hoops.map((p) => (p.kind === "circle" ? p.cx : NaN)).sort((a, b) => a - b);
    console.log("hoops at x =", xs);
    expect(xs).toEqual([-(14 - 1.575), 14 - 1.575]);
  });

  it("puts the goals on each goal line", () => {
    for (const pitch of PITCHES) {
      const goals = surfacePrimitives(pitch).filter((p) => "role" in p && p.role === "goal");
      const xs = goals.map((p) => (p.kind === "line" ? p.x1 : NaN)).sort((a, b) => a - b);
      console.log(`${pitch.spec}: goals at x =`, xs);
      expect(xs).toEqual([-pitch.length_m / 2, pitch.length_m / 2]);
    }
  });

  it("keeps every marking on the surface", () => {
    for (const surface of [FIBA, ...PITCHES]) {
      const L = surface.length_m / 2;
      const W = surface.width_m / 2;
      const outside = surfacePrimitives(surface).filter((p) =>
        extent(p).some(([x, y]) => Math.abs(x) > L + EPS || Math.abs(y) > W + EPS),
      );
      expect(outside, surface.spec).toEqual([]);
    }
  });

  it("meets the corner three-point lines with the arc", () => {
    const prims = surfacePrimitives(FIBA);
    const arc = prims.find((p) => p.kind === "arc" && p.cx < 0);
    const corner = prims.find((p) => p.kind === "line" && p.y1 === 7.5 - 0.9 && p.x1 < 0);
    if (arc?.kind !== "arc" || corner?.kind !== "line") throw new Error("missing markings");
    expect(arc.cx + arc.r * Math.cos(arc.end)).toBeCloseTo(corner.x2, 9);
    expect(arc.cy + arc.r * Math.sin(arc.end)).toBeCloseTo(corner.y2, 9);
  });

  it("draws both sports through the same call", () => {
    for (const surface of [FIBA, PITCHES[0]]) {
      const { ctx, calls } = recorder();
      drawSurface(ctx, surface);
      const strokes = calls.filter((c) => c === "stroke").length;
      expect(strokes).toBe(surfacePrimitives(surface).length);
    }
  });

  it("refuses a surface it has no markings for", () => {
    expect(() => surfacePrimitives({ spec: "nba_94x50", length_m: 28.6512, width_m: 15.24 })).toThrow(
      /nba_94x50/,
    );
  });
});
