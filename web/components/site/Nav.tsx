"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { isCurrent, SECTIONS } from "../../lib/sections";

// The header's links, a row that wraps on a phone (no menu to open). Client-side only for
// `aria-current`; no prefetch, so a page's byte budget does not pay for the seven others.
export function Nav() {
  const path = usePathname();
  return (
    <nav className="site-nav" aria-label="Sections">
      <ul>
        {SECTIONS.map((s) => (
          <li key={s.href}>
            <Link href={s.href} prefetch={false} aria-current={isCurrent(path, s.href) ? "page" : undefined}>
              {s.nav}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
