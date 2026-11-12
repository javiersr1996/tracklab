"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type RefObject, useLayoutEffect, useRef } from "react";
import { inEntry, NAV, pageOf } from "../../lib/sections";

// Whether a strip has links hidden past either edge, as data attributes the CSS fades by.
function markEdges(ul: HTMLUListElement) {
  ul.dataset.start = String(ul.scrollLeft <= 1);
  ul.dataset.end = String(ul.scrollLeft + ul.clientWidth >= ul.scrollWidth - 1);
}

// A row of links that is one line on a phone, scrolled sideways (P21): on each page the current
// link is brought into the strip, and its edges fade where more links wait. From 640 px every link
// fits and nothing scrolls.
function useStrip(ref: RefObject<HTMLUListElement | null>, path: string) {
  // Before paint, so the strip does not show its start and then jump.
  useLayoutEffect(() => {
    const ul = ref.current;
    if (!ul) return;
    const current = ul.querySelector<HTMLElement>("[aria-current]");
    if (current && ul.scrollWidth > ul.clientWidth) {
      const a = current.getBoundingClientRect();
      const box = ul.getBoundingClientRect();
      ul.scrollLeft += a.left - box.left - (box.width - a.width) / 2;
    }
    markEdges(ul);
    const onScroll = () => markEdges(ul);
    ul.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      ul.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, [ref, path]);
}

// The header's entries, and under Tracking, Engineering, Warehouse or Learn a second row with the
// pages of that group (P15, P17, P21). The brackets around each link are CSS, from 640 px.
// Client-side only for `aria-current`; no prefetch, so a page's byte budget does not pay for the
// others.
export function Nav() {
  const path = usePathname();
  const group = NAV.find((n) => n.pages && inEntry(path, n));
  const on = group?.pages ? pageOf(path, group.pages) : undefined;
  const top = useRef<HTMLUListElement>(null);
  const sub = useRef<HTMLUListElement>(null);
  useStrip(top, path);
  useStrip(sub, path);
  return (
    <>
      <nav className="site-nav" aria-label="Sections">
        <ul ref={top}>
          {NAV.map((n) => (
            <li key={n.href}>
              <Link href={n.href} prefetch={false} aria-current={inEntry(path, n) ? "page" : undefined}>
                {n.nav}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {group?.pages && (
        <nav className="site-nav site-subnav" aria-label={group.nav}>
          <ul ref={sub}>
            {group.pages.map((p) => (
              <li key={p.href}>
                <Link href={p.href} prefetch={false} aria-current={p === on ? "page" : undefined}>
                  {p.nav}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </>
  );
}
