import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { formatClock, ReplayEngine, speedOf } from "../lib/replay/engine";
import type { Frame, Possession } from "../lib/replay/types";

const frames: Frame[] = [
  { t: 1000, clock: 24, o: [[0, 0, 0, null, 1], [1, 10, 2, 0.5, 1], [2, 5, 5, null, 1]] },
  { t: 1100, clock: 23.9, o: [[0, 1, 2, null, 0], [1, 12, 4, 1.5, 1]] },
  { t: 1200, clock: 23.8, o: [[0, 2, 4, null, 1], [1, 14, 6, 2.5, 1], [2, 6, 6, null, 1]] },
];
const engine = () => new ReplayEngine({ frames });

describe("ReplayEngine", () => {
  it("imports and runs in Node, with no window", () => {
    expect(typeof globalThis.window).toBe("undefined");
    expect(engine().state).toBe("idle");
  });

  it("goes from playing to ended exactly on the last t", () => {
    const e = engine();
    e.play();
    e.tick(150);
    expect([e.state, e.t]).toEqual(["playing", 1150]);
    e.tick(1000);
    expect([e.state, e.t]).toEqual(["ended", 1200]);
  });

  it("keeps t when paused", () => {
    const e = engine();
    e.play();
    e.tick(40);
    e.pause();
    e.tick(100);
    expect([e.state, e.t]).toEqual(["paused", 1040]);
  });

  it("advances twice as far per tick at rate 2", () => {
    const e = engine();
    e.setRate(2);
    e.play();
    e.tick(40);
    expect(e.t).toBe(1080);
  });

  it("clamps a seek to the possession", () => {
    const e = engine();
    e.seek(0);
    expect(e.t).toBe(1000);
    e.seek(99_999);
    expect(e.t).toBe(1200);
  });

  it("returns the midpoint halfway between two samples", () => {
    const snap = engine().frameAt(1050);
    const ball = snap.entities.find((o) => o.i === 1);
    console.log("frameAt(1050):", ball, "clock", snap.clock);
    expect(ball).toMatchObject({ x: 11, y: 3, detected: true });
    expect(ball?.z).toBeCloseTo(1.0, 12);
    expect(snap.clock).toBeCloseTo(23.95, 12);
  });

  it("treats an entity missing from a sample as absent, not interpolated", () => {
    const e = engine();
    expect(e.frameAt(1000).entities.map((o) => o.i)).toEqual([0, 1, 2]);
    expect(e.frameAt(1050).entities.map((o) => o.i)).toEqual([0, 1]);
    expect(e.frameAt(1150).entities.map((o) => o.i)).toEqual([0, 1]);
    expect(e.frameAt(1200).entities.map((o) => o.i)).toEqual([0, 1, 2]);
  });

  it("interpolates the same way at 10 fps as at 25 fps", () => {
    const at = (step: number) =>
      new ReplayEngine({
        frames: [
          { t: 0, clock: 0, o: [[0, 0, 0, null, 1]] },
          { t: step, clock: 0, o: [[0, 4, 0, null, 1]] },
        ],
      }).frameAt(step / 4).entities[0].x;
    expect([at(40), at(100)]).toEqual([1, 1]);
  });

  it("plays every published possession to its last frame", () => {
    const dir = join(__dirname, "..", "public", "data", "possessions");
    for (const name of readdirSync(dir)) {
      const p = JSON.parse(readFileSync(join(dir, name), "utf-8")) as Possession;
      const e = new ReplayEngine(p);
      e.play();
      while (e.state === "playing") e.tick(1000 / 60);
      expect(e.t, name).toBe(p.frames[p.frames.length - 1].t);
    }
  });
});

describe("formatClock", () => {
  it("reads a countdown like a scoreboard", () => {
    expect(formatClock(600, "countdown")).toBe("10:00");
    expect(formatClock(114.02, "countdown")).toBe("1:55");
    expect(formatClock(42.87, "countdown")).toBe("42.8");
  });

  it("reads an elapsed clock as minutes past the start", () => {
    expect(formatClock(1026.2, "elapsed")).toBe("17:06");
    expect(formatClock(1.9, "elapsed")).toBe("0:01");
  });
});

describe("speedOf", () => {
  it("is the distance between the ends of the window over its length", () => {
    // Entity 1 moves (2, 2) m every 100 ms: from (10, 2) at 1000 to (14, 6) at 1200.
    expect(speedOf(engine(), 1, 1200, 200)).toBeCloseTo(Math.hypot(4, 4) / 0.2, 6);
  });

  it("is null before the window has a start, and for an entity absent at an end", () => {
    expect(speedOf(engine(), 1, 1000, 200)).toBeNull();
    // Entity 2 is missing from the 1100 sample, so it is absent at 1050 and at 1150.
    expect(speedOf(engine(), 2, 1150, 100)).toBeNull();
  });
});
