// Surface markings as data, in metres, venue frame: origin at the centre, x along
// the long axis. Drawing and testing read the same list.

export type Role = "hoop" | "goal" | "spot";

export type Primitive =
  | { kind: "line"; x1: number; y1: number; x2: number; y2: number; role?: Role }
  | { kind: "rect"; x: number; y: number; w: number; h: number }
  | { kind: "circle"; cx: number; cy: number; r: number; role?: Role }
  | { kind: "arc"; cx: number; cy: number; r: number; start: number; end: number };

export const line = (x1: number, y1: number, x2: number, y2: number, role?: Role): Primitive => ({
  kind: "line",
  x1,
  y1,
  x2,
  y2,
  ...(role && { role }),
});

export const circle = (cx: number, cy: number, r: number, role?: Role): Primitive => ({
  kind: "circle",
  cx,
  cy,
  r,
  ...(role && { role }),
});

// Both ends of a surface: `side` is -1 for the end at -x, +1 for the end at +x.
export const SIDES = [-1, 1] as const;
