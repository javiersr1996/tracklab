import type { MetadataRoute } from "next";
import { LESSONS, lessonHref } from "../lib/learn/series";
import { SECTIONS, SITE } from "../lib/sections";
import { SQL_LESSONS, sqlHref } from "../lib/sql/course";

// The home page, the /tracking hub (P15), the nine sections, every published lesson (a lesson in
// preparation has no page), and the SQL course with its eight lessons.
export default function sitemap(): MetadataRoute.Sitemap {
  const paths = [
    "/",
    "/tracking",
    ...SECTIONS.map((s) => s.href),
    ...LESSONS.filter((l) => l.status === "published").map(lessonHref),
    "/sql",
    ...SQL_LESSONS.map((l) => sqlHref(l.slug)),
  ];
  return paths.map((p) => ({ url: `${SITE}${p === "/" ? "" : p}` }));
}
