import { circle, line, type Primitive, SIDES } from "./primitives";

// IFAB pitch markings, parametric in the pitch's length and width.
export const IFAB = {
  goalWidth: 7.32,
  goalAreaDepth: 5.5,
  penaltyAreaDepth: 16.5,
  penaltySpot: 11,
  circleRadius: 9.15,
  spotRadius: 0.2,
};

export function footballPrimitives(length: number, width: number): Primitive[] {
  const L = length / 2;
  const W = width / 2;
  const goalHalf = IFAB.goalWidth / 2;
  const out: Primitive[] = [
    { kind: "rect", x: -L, y: -W, w: length, h: width },
    line(0, -W, 0, W),
    circle(0, 0, IFAB.circleRadius),
    circle(0, 0, IFAB.spotRadius, "spot"),
  ];
  for (const side of SIDES) {
    const goalLine = side * L;
    const inward = -side;
    const spotX = goalLine + inward * IFAB.penaltySpot;
    // The penalty arc is the part of the 9.15 m circle outside the penalty area.
    const theta = Math.acos((IFAB.penaltyAreaDepth - IFAB.penaltySpot) / IFAB.circleRadius);
    const facing = side === -1 ? 0 : Math.PI;
    for (const depth of [IFAB.goalAreaDepth, IFAB.penaltyAreaDepth]) {
      const half = goalHalf + depth;
      const inner = goalLine + inward * depth;
      out.push({ kind: "rect", x: Math.min(goalLine, inner), y: -half, w: depth, h: 2 * half });
    }
    out.push(
      line(goalLine, -goalHalf, goalLine, goalHalf, "goal"),
      circle(spotX, 0, IFAB.spotRadius, "spot"),
      { kind: "arc", cx: spotX, cy: 0, r: IFAB.circleRadius, start: facing - theta, end: facing + theta },
    );
  }
  return out;
}
