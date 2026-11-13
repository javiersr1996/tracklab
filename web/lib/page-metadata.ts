import type { Metadata } from "next";
import { SECTIONS } from "./sections";

// Title and description of a page that is one of the nine sections: the home page's card text,
// so the page and its card say the same thing. The og:image comes from app/opengraph-image.tsx.
export function sectionMetadata(href: (typeof SECTIONS)[number]["href"]): Metadata {
  const s = SECTIONS.find((x) => x.href === href);
  if (!s) throw new Error(`no section ${href} in sections.ts`);
  return { title: `${s.title} | Pitch & Parquet`, description: s.about };
}
