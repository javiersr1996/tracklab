import { circle, line, type Primitive, SIDES } from "./primitives";

// FIBA court markings, parametric in the court's length and width.
export const FIBA = {
  hoopFromBaseline: 1.575,
  hoopRadius: 0.225,
  backboardFromBaseline: 1.2,
  backboardHalfWidth: 0.9,
  threePointRadius: 6.75,
  cornerFromSideline: 0.9,
  keyWidth: 4.9,
  keyLength: 5.8,
  circleRadius: 1.8,
};

export function basketballPrimitives(length: number, width: number): Primitive[] {
  const L = length / 2;
  const W = width / 2;
  const out: Primitive[] = [
    { kind: "rect", x: -L, y: -W, w: length, h: width },
    line(0, -W, 0, W),
    circle(0, 0, FIBA.circleRadius),
  ];
  for (const side of SIDES) {
    const baseline = side * L;
    const hoopX = side * (L - FIBA.hoopFromBaseline);
    const inward = -side;
    const cornerY = W - FIBA.cornerFromSideline;
    // Where the straight corner lines meet the arc, measured from the hoop along x.
    const meet = Math.sqrt(FIBA.threePointRadius ** 2 - cornerY ** 2);
    const theta = Math.atan2(cornerY, meet);
    const facing = side === -1 ? 0 : Math.PI;
    const keyX = baseline + inward * FIBA.keyLength;
    out.push(
      circle(hoopX, 0, FIBA.hoopRadius, "hoop"),
      line(
        side * (L - FIBA.backboardFromBaseline),
        -FIBA.backboardHalfWidth,
        side * (L - FIBA.backboardFromBaseline),
        FIBA.backboardHalfWidth,
      ),
      line(baseline, -cornerY, hoopX + inward * meet, -cornerY),
      line(baseline, cornerY, hoopX + inward * meet, cornerY),
      { kind: "arc", cx: hoopX, cy: 0, r: FIBA.threePointRadius, start: facing - theta, end: facing + theta },
      {
        kind: "rect",
        x: Math.min(baseline, keyX),
        y: -FIBA.keyWidth / 2,
        w: FIBA.keyLength,
        h: FIBA.keyWidth,
      },
      circle(keyX, 0, FIBA.circleRadius),
    );
  }
  return out;
}
