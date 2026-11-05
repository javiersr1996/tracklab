import type { MetadataRoute } from "next";
import { LESSONS, lessonHref } from "../lib/learn/series";
import { SECTIONS, SITE } from "../lib/sections";
import { SQL_LESSONS, sqlHref } from "../lib/sql/course";

// The home page, the /tracking hub (P15), the nine sections, the bulletin and the build history
// (P16), the scouting table (P17), every published
// lesson (a lesson in preparation has no page), and the SQL lessons (/sql is a section).
export default function sitemap(): MetadataRoute.Sitemap {
  const paths = [
    "/",
    "/tracking",
    ...SECTIONS.map((s) => s.href),
    "/engineering/bulletin",
    "/engineering/history",
    "/warehouse/scouting",
    ...LESSONS.filter((l) => l.status === "published").map(lessonHref),
    ...SQL_LESSONS.map((l) => sqlHref(l.slug)),
  ];
  return paths.map((p) => ({ url: `${SITE}${p === "/" ? "" : p}` }));
}
