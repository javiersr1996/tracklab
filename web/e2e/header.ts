import type { Page } from "@playwright/test";

// Every link of the header as a reader sees it: its box, and the part of it its row shows. On a
// phone the entries and a group's pages are strips that scroll sideways (P21), so a link past a
// strip's edge is hidden in the strip, not off the page.
export interface HeaderLink {
  text: string;
  x: number;
  y: number;
  r: number;
  b: number;
  // The visible part, clipped to the strip; empty when the link is scrolled out of it.
  shownX: number;
  shownR: number;
  strip: { x: number; r: number; scrolls: boolean } | null;
  current: boolean;
  size: number;
}

export function headerLinks(page: Page): Promise<HeaderLink[]> {
  return page.locator(".site-header a").evaluateAll((els) =>
    els.map((e) => {
      const r = e.getBoundingClientRect();
      const ul = e.closest("ul");
      const clip = ul?.getBoundingClientRect();
      return {
        text: (e.textContent ?? "").trim(),
        x: r.left,
        y: r.top,
        r: r.right,
        b: r.bottom,
        shownX: Math.max(r.left, clip?.left ?? r.left),
        shownR: Math.min(r.right, clip?.right ?? r.right),
        strip: ul && clip ? { x: clip.left, r: clip.right, scrolls: ul.scrollWidth > ul.clientWidth } : null,
        current: e.hasAttribute("aria-current"),
        size: parseFloat(getComputedStyle(e).fontSize),
      };
    }),
  );
}

// A link the strip shows whole, to within a sub-pixel.
export const whole = (l: HeaderLink) => l.shownX <= l.x + 0.5 && l.shownR >= l.r - 0.5;
