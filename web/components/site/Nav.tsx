"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isCurrent, NAV } from "../../lib/sections";

// The header's entries, a row that wraps on a phone (no menu to open; the brackets around each
// link are CSS, from 640 px up), and under Tracking, Engineering or Warehouse a second row with the
// pages of that group (P15, P17). Client-side only for `aria-current`; no prefetch, so a page's byte budget does
// not pay for the others.
export function Nav() {
  const path = usePathname();
  const group = NAV.find((n) => n.pages && isCurrent(path, n.href));
  return (
    <>
      <nav className="site-nav" aria-label="Sections">
        <ul>
          {NAV.map((n) => (
            <li key={n.href}>
              <Link href={n.href} prefetch={false} aria-current={isCurrent(path, n.href) ? "page" : undefined}>
                {n.nav}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
      {group?.pages && (
        <nav className="site-nav site-subnav" aria-label={group.nav}>
          <ul>
            {group.pages.map((p) => (
              <li key={p.href}>
                <Link href={p.href} prefetch={false} aria-current={path === p.href ? "page" : undefined}>
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
