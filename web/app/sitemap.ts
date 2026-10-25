import type { MetadataRoute } from "next";
import { LESSONS, lessonHref } from "../lib/learn/series";
import { SECTIONS, SITE } from "../lib/sections";

// The home page, the seven sections and every published lesson; a lesson in preparation has no page.
export default function sitemap(): MetadataRoute.Sitemap {
  const paths = ["/", ...SECTIONS.map((s) => s.href), ...LESSONS.filter((l) => l.status === "published").map(lessonHref)];
  return paths.map((p) => ({ url: `${SITE}${p === "/" ? "" : p}` }));
}
