// Lesson 8's arithmetic: the entry-angle check of P3 (`quality/entry_angle.py`, and `learn/entry.py`,
// the script the lesson reproduces it with), on one flight, with the reader's g and height scale.
//
// v_h is the median of the horizontal speeds between the run's first samples, T = D / v_h the
// time to the rim's centre, k = round(T · fps) the arrival sample. The reported angle comes from
// the least-squares slope of the heights over samples max(k − tail_back, tail_min_index) to k;
// the required one from a projectile that leaves the first sample's height and reaches the rim
// after T under g.
export interface EntryConstants {
  fps: number;
  g: number;
  rim_height: number;
  v_h_frames: number;
  tail_back: number;
  tail_min_index: number;
}

export interface Sample {
  t: number; // s
  x: number;
  y: number;
  z: number; // m
}

export interface Options {
  g?: number; // the gravity the required angle assumes
  zScale?: number; // every height multiplied by it, as if the file's heights were off by that much
  rim?: number; // the rim's height
}

// Python's statistics.median: the middle value, or the mean of the two middle ones.
export function median(xs: readonly number[]): number {
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

// Python's round(x): to the nearest integer, a half to the even one.
export function roundHalfEven(x: number): number {
  const r = Math.round(x);
  return Math.abs(x % 1) === 0.5 && r % 2 !== 0 ? r - 1 : r;
}

export function lsSlope(t: readonly number[], z: readonly number[]): number {
  const n = t.length;
  const tbar = t.reduce((s, v) => s + v, 0) / n;
  const zbar = z.reduce((s, v) => s + v, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (t[i] - tbar) * (z[i] - zbar);
    den += (t[i] - tbar) ** 2;
  }
  return num / den;
}

const deg = (rad: number) => (rad * 180) / Math.PI;

export function flight(run: readonly Sample[], c: EntryConstants, rimX: number, o: Options = {}) {
  const g = o.g ?? c.g;
  const s = o.zScale ?? 1;
  const rim = o.rim ?? c.rim_height;
  const first = run.slice(0, c.v_h_frames);
  const speeds = first.slice(1).map((b, i) => {
    const a = first[i];
    const dt = b.t - a.t;
    return dt > 0 ? Math.hypot(b.x - a.x, b.y - a.y) / dt : 0;
  });
  const vH = median(speeds);
  const d = Math.hypot(rimX - run[0].x, -run[0].y);
  const T = d / vH;
  const k = roundHalfEven(T / (1 / c.fps));
  if (k >= run.length) throw new Error(`the arrival sample ${k} is past the flight's ${run.length}`);
  const tail = run.slice(Math.max(k - c.tail_back, c.tail_min_index), k + 1);
  const vzRep = lsSlope(
    tail.map((p) => p.t - tail[0].t),
    tail.map((p) => s * p.z),
  );
  const vz0 = (rim - s * run[0].z + 0.5 * g * T * T) / T;
  const vzReq = vz0 - g * T;
  const reported = deg(Math.atan2(Math.abs(vzRep), vH));
  const required = deg(Math.atan2(Math.abs(vzReq), vH));
  return { vH, d, T, k, vzRep, vz0, vzReq, reported, required, gap: required - reported };
}

export type Flight = ReturnType<typeof flight>;

// The same flight as a projectile that obeys g exactly: the run's first sample, its v_h, and the
// vertical speed that reaches the rim after T, sampled at the file's rate. Its reported angle is
// what the method reads off a perfect flight.
export function perfectRun(run: readonly Sample[], f: Flight, c: EntryConstants, g = c.g): Sample[] {
  return run.map((p, i) => {
    const t = i / c.fps;
    return { t: run[0].t + t, x: p.x, y: p.y, z: run[0].z + f.vz0 * t - 0.5 * g * t * t };
  });
}
