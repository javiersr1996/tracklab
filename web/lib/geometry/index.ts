import type { Surface } from "../replay/types";
import { basketballPrimitives } from "./basketball";
import { footballPrimitives } from "./football";
import type { Primitive } from "./primitives";

export type { Primitive } from "./primitives";

// The one place a surface's markings are chosen: by the family of its `spec`
// (`fiba_28x15`, `provider_105x68`, ...). The sizes always come from the surface.
const FAMILIES: Record<string, (length: number, width: number) => Primitive[]> = {
  fiba: basketballPrimitives,
  provider: footballPrimitives,
};

export function surfacePrimitives(surface: Surface): Primitive[] {
  const family = surface.spec.split("_")[0];
  const build = FAMILIES[family];
  if (!build) throw new Error(`no markings for surface spec ${surface.spec}`);
  return build(surface.length_m, surface.width_m);
}

export type SurfaceContext = Pick<
  CanvasRenderingContext2D,
  "beginPath" | "moveTo" | "lineTo" | "arc" | "rect" | "stroke" | "fill"
>;

// Strokes every marking in metres; the caller sets the transform and the line width.
export function drawSurface(ctx: SurfaceContext, surface: Surface): void {
  for (const p of surfacePrimitives(surface)) {
    ctx.beginPath();
    switch (p.kind) {
      case "line":
        ctx.moveTo(p.x1, p.y1);
        ctx.lineTo(p.x2, p.y2);
        break;
      case "rect":
        ctx.rect(p.x, p.y, p.w, p.h);
        break;
      case "circle":
        ctx.arc(p.cx, p.cy, p.r, 0, 2 * Math.PI);
        break;
      case "arc":
        ctx.arc(p.cx, p.cy, p.r, p.start, p.end);
        break;
    }
    ctx.stroke();
  }
}
