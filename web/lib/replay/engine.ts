import type { ClockKind, Frame, Possession } from "./types";

// Playback of one possession, with no DOM: the renderer calls `tick` from its
// animation loop and draws `frameAt(engine.t)`. Time is the possession's own `t`
// (ms of video clock), so a seek is a number from the published file.

export type PlayState = "idle" | "playing" | "paused" | "ended";
export type Rate = 0.5 | 1 | 2;

export interface EntityAt {
  i: number;
  x: number;
  y: number;
  z: number | null;
  detected: boolean;
}

export interface Snapshot {
  t: number;
  clock: number;
  entities: EntityAt[];
}

// The play, pause, seek and rate machine over samples sorted by `t`, with no idea of what
// a sample holds: the replay and the pose viewer (task 56) each add their own `frameAt`.
export class Playback {
  state: PlayState = "idle";
  rate: Rate = 1;
  t: number;
  readonly t0: number;
  readonly tEnd: number;
  private readonly times: number[];

  constructor(times: number[]) {
    this.times = times;
    this.t0 = times[0];
    this.tEnd = times[times.length - 1];
    this.t = this.t0;
  }

  play(): void {
    if (this.state === "ended") this.t = this.t0;
    this.state = this.t >= this.tEnd ? "ended" : "playing";
  }

  pause(): void {
    if (this.state === "playing") this.state = "paused";
  }

  seek(t: number): void {
    this.t = Math.min(Math.max(t, this.t0), this.tEnd);
    if (this.state === "ended" && this.t < this.tEnd) this.state = "paused";
  }

  setRate(rate: Rate): void {
    this.rate = rate;
  }

  tick(dtMs: number): void {
    if (this.state !== "playing") return;
    this.t = Math.min(this.t + dtMs * this.rate, this.tEnd);
    if (this.t === this.tEnd) this.state = "ended";
  }

  // The last sample at or before `t` (binary search; samples are sorted by t).
  indexAt(t: number): number {
    let lo = 0;
    let hi = this.times.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (this.times[mid] <= t) lo = mid;
      else hi = mid - 1;
    }
    return lo;
  }
}

export class ReplayEngine extends Playback {
  private readonly frames: Frame[];

  constructor(possession: Pick<Possession, "frames">) {
    super(possession.frames.map((f) => f.t));
    this.frames = possession.frames;
  }

  // Linear between the two native samples around `t`, the same at 25 and 10 fps.
  // An entity missing from either sample is absent, never interpolated across the gap.
  frameAt(t: number): Snapshot {
    const clamped = Math.min(Math.max(t, this.t0), this.tEnd);
    const k = this.indexAt(clamped);
    const a = this.frames[k];
    const b = this.frames[Math.min(k + 1, this.frames.length - 1)];
    const alpha = b.t === a.t ? 0 : (clamped - a.t) / (b.t - a.t);
    const clock = a.clock + (b.clock - a.clock) * alpha;
    if (alpha === 0) {
      return {
        t: clamped,
        clock,
        entities: a.o.map(([i, x, y, z, d]) => ({ i, x, y, z, detected: d === 1 })),
      };
    }
    const next = new Map(b.o.map((o) => [o[0], o]));
    const entities: EntityAt[] = [];
    for (const [i, x, y, z, d] of a.o) {
      const o = next.get(i);
      if (!o) continue;
      entities.push({
        i,
        x: x + (o[1] - x) * alpha,
        y: y + (o[2] - y) * alpha,
        z: z === null || o[3] === null ? null : z + (o[3] - z) * alpha,
        detected: (alpha < 0.5 ? d : o[4]) === 1,
      });
    }
    return { t: clamped, clock, entities };
  }
}

// A countdown reads like a scoreboard (tenths in the last minute); an elapsed
// clock reads like a match clock, minutes past the start.
export function formatClock(seconds: number, kind: ClockKind): string {
  const s = Math.max(seconds, 0);
  if (kind === "countdown" && s < 60) return (Math.floor(s * 10) / 10).toFixed(1);
  const whole = kind === "countdown" ? Math.ceil(s) : Math.floor(s);
  const mm = Math.floor(whole / 60);
  const ss = String(whole % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}
