// The MathML elements the lessons use, typed as plain elements: React renders them natively.
import type { DetailedHTMLProps, HTMLAttributes } from "react";

type MathElement = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement>;

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      math: MathElement & { display?: "block" | "inline" };
      mrow: MathElement;
      mi: MathElement;
      mn: MathElement;
      mo: MathElement;
      mtext: MathElement;
      msub: MathElement;
      msup: MathElement;
      mfrac: MathElement;
      msqrt: MathElement;
      mtable: MathElement;
      mtr: MathElement;
      mtd: MathElement;
      mover: MathElement;
      mspace: MathElement & { width?: string };
    }
  }
}
