// Playwright reads what lesson 1's figures computed from `window.__learn` (task 79), the way the
// viewers expose `window.__replay` and `window.__pose`; a production build leaves it out.
export const EXPOSE =
  process.env.NODE_ENV === "development" || process.env.NEXT_PUBLIC_EXPOSE_REPLAY === "1";

export type Learn = Record<string, unknown>;

declare global {
  interface Window {
    __learn?: Learn;
  }
}

// Merges one figure's part into `window.__learn`. Called from an effect, never during render.
export function expose(part: Learn): void {
  if (EXPOSE) window.__learn = { ...window.__learn, ...part };
}

// A figure as the page prints it: rounded to `digits` decimals, and the same number in
// `window.__learn`, so the text and the exposed value compare with `String(value)`.
export const shown = (x: number, digits: number): number => Number(x.toFixed(digits));
