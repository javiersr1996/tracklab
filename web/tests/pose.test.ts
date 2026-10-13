import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { PoseEngine } from "../lib/pose/engine";
import { byDepth, type Camera, project } from "../lib/pose/project";
import { drawPitch, maeBand } from "../lib/pose/render";
import type { Joints, PoseClip, PoseFrame } from "../lib/pose/types";
import { viewOf } from "../lib/replay/render";

// Task 56 (P6): the viewer's own projection, the engine that never interpolates a skeleton and
// the drawing that reports what it drew.

const CLIP = JSON.parse(
  readFileSync(join(__dirname, "..", "public", "data", "pose", "1925299_phase406.json"), "utf-8"),
) as PoseClip;

// Points in the body frame, metres: a head-like one, a foot-like one, one off to the side.
const POINTS: [number, number, number][] = [
  [0.12, -0.05, 1.71],
  [-0.31, 0.22, 0.04],
  [0.8, 0.45, 0.9],
];

describe("project", () => {
  it("looking straight down (tilt 0), a point with dz > 0 lands where it would with dz = 0", () => {
    for (const yaw of [0, 37, 90, 180, -120]) {
      for (const [x, y, z] of POINTS) {
        const [u, v] = project(x, y, z, { yaw, tilt: 0 });
        const [u0, v0] = project(x, y, 0, { yaw, tilt: 0 });
        expect([u, v], `yaw ${yaw}`).toEqual([u0, v0]);
      }
    }
  });

  it("tipped (tilt > 0), a point with dz > 0 sits above the same point at dz = 0", () => {
    for (const tilt of [10, 45, 60, 90]) {
      for (const [x, y, z] of POINTS) {
        const v = project(x, y, z, { yaw: 0, tilt })[1];
        const v0 = project(x, y, 0, { yaw: 0, tilt })[1];
        expect(v - v0, `tilt ${tilt}`).toBeCloseTo(z * Math.sin((tilt * Math.PI) / 180), 12);
        expect(v, `tilt ${tilt}`).toBeGreaterThan(v0);
      }
    }
    // Level (tilt 90), v is z itself.
    expect(project(0.3, -0.2, 1.5, { yaw: 0, tilt: 90 })[1]).toBeCloseTo(1.5, 12);
  });

  it("yaw 180 turns u into -u", () => {
    for (const tilt of [0, 30, 90]) {
      for (const [x, y, z] of POINTS) {
        const u = project(x, y, z, { yaw: 0, tilt })[0];
        expect(project(x, y, z, { yaw: 180, tilt })[0]).toBeCloseTo(-u, 12);
      }
    }
  });

  it("orders by depth: higher is nearer from above, farther in y is farther when level", () => {
    const above: Camera = { yaw: 0, tilt: 0 };
    expect(project(0, 0, 1.7, above)[2]).toBeLessThan(project(0, 0, 0.1, above)[2]);
    const level: Camera = { yaw: 0, tilt: 90 };
    expect(project(0, 1, 1, level)[2]).toBeGreaterThan(project(0, -1, 1, level)[2]);
    // Bones are painted farthest first.
    const points = [project(0, -1, 1, level), project(0, 0, 1, level), project(0, 1, 1, level)];
    expect(byDepth(points, [[0, 1], [1, 2]])).toEqual([[1, 2], [0, 1]]);
  });
});

// A 2D context that records the dots it is asked to draw while no transform is set (the
// markings go in metres under a transform; players, joints and the ball in pixels without one).
function recorder(width = 960, height = 640) {
  const dots: { x: number; y: number; r: number }[] = [];
  let identity = true;
  const target = { canvas: { width, height } } as Record<string, unknown>;
  const ctx = new Proxy(target, {
    get: (t, name: string) => {
      if (name in t) return t[name];
      if (name === "setTransform")
        return (a: number, b: number, c: number, d: number, e: number, f: number) => {
          identity = a === 1 && b === 0 && c === 0 && d === 1 && e === 0 && f === 0;
        };
      if (name === "arc") return (x: number, y: number, r: number) => identity && dots.push({ x, y, r });
      return () => undefined;
    },
    set: () => true,
  }) as unknown as CanvasRenderingContext2D;
  return { ctx, dots };
}

describe("drawPitch", () => {
  it("at yaw 0 and tilt 0 puts a joint with dz = 0 where the replay puts (x + dx, y + dy)", () => {
    const xyz: Joints[0] = Array.from({ length: 29 }, (_, j) => [j * 3 - 40, 25 - j * 2, 0]);
    const frame: PoseFrame = {
      f: 1,
      t: 0,
      ball: [0, 0, 1],
      p: [[0, 2291, -1337, 1, [xyz, Array(29).fill(50)]]],
    };
    const { ctx, dots } = recorder();
    drawPitch(ctx, CLIP, frame, { yaw: 0, tilt: 0 }, null);
    const replay = viewOf({ width: 960, height: 640 }, { surface: CLIP.surface, attack_sign: 1 }, false);
    const joints = dots.slice(0, 29);
    xyz.forEach(([dx, dy], j) => {
      const [px, py] = replay.project((2291 + dx) / 100, (-1337 + dy) / 100);
      expect(joints[j].x, `joint ${j}`).toBeCloseTo(px, 9);
      expect(joints[j].y, `joint ${j}`).toBeCloseTo(py, 9);
    });
  });

  it("draws a skeleton for every player the frame gives a pose and a disc for every other", () => {
    for (const frame of CLIP.frames) {
      const { ctx } = recorder();
      const drawn = drawPitch(ctx, CLIP, frame, { yaw: 30, tilt: 60 }, null);
      const posed = frame.p.filter((e) => e[4] !== null).length;
      expect([drawn.skeletons, drawn.discs], `frame ${frame.f}`).toEqual([posed, frame.p.length - posed]);
    }
  });
});

describe("maeBand", () => {
  it("cuts at the clip's own median and 90th percentile", () => {
    const cuts = CLIP.coverage.p90_mae_cm;
    expect(maeBand(cuts.min * 10, cuts)).toBe(0);
    expect(maeBand(cuts.median * 10, cuts)).toBe(0);
    expect(maeBand(cuts.median * 10 + 1, cuts)).toBe(1);
    expect(maeBand(cuts.p90 * 10, cuts)).toBe(1);
    expect(maeBand(cuts.p90 * 10 + 1, cuts)).toBe(2);
    expect(maeBand(cuts.max * 10, cuts)).toBe(2);
  });
});

describe("PoseEngine", () => {
  const A: Joints = [Array.from({ length: 29 }, () => [0, 0, 100]), Array(29).fill(80)];
  const B: Joints = [Array.from({ length: 29 }, () => [40, 20, 140]), Array(29).fill(90)];
  const frames: PoseFrame[] = [
    { f: 10, t: 0, ball: [0, 0, 1], p: [[0, 0, 0, 1, A], [1, 500, 0, 1, A]] },
    { f: 11, t: 40, ball: [0, 0, 1], p: [[0, 10, 0, 1, B], [1, 510, 0, 1, null]] },
  ];
  const engine = () => new PoseEngine({ frames });

  it("returns the last native frame, never a blend, and loses a pose exactly where the file does", () => {
    const e = engine();
    for (const t of [0, 1, 20, 39.9]) expect(e.frameAt(t), `t ${t}`).toBe(frames[0]);
    expect(e.frameAt(40)).toBe(frames[1]);
    // The player who loses his pose: whole until the next frame, then null, never faded out.
    expect(e.frameAt(39.9).p[1][4]).toEqual(A);
    expect(e.frameAt(40).p[1][4]).toBeNull();
    // The one who keeps it: A then B, nothing in between.
    expect(e.frameAt(20).p[0][4]).toEqual(A);
    expect(e.frameAt(20).p[0][1]).toBe(0);
  });

  it("runs the replay's machine: idle, playing, paused, ended on the last t", () => {
    const e = engine();
    expect(e.state).toBe("idle");
    e.setRate(2);
    e.play();
    e.tick(10);
    expect([e.state, e.t]).toEqual(["playing", 20]);
    e.pause();
    e.tick(100);
    expect([e.state, e.t]).toEqual(["paused", 20]);
    e.play();
    e.tick(100);
    expect([e.state, e.t]).toEqual(["ended", 40]);
  });

  it("plays the published clip to its last frame", () => {
    const e = new PoseEngine(CLIP);
    e.play();
    while (e.state === "playing") e.tick(1000 / 60);
    expect(e.frameAt(e.t)).toBe(CLIP.frames[CLIP.frames.length - 1]);
  });
});
