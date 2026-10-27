import type { Metadata } from "next";
import { type SqlSlug, sqlHref, sqlLessonMeta } from "./course";

// The title is the lesson's question, the description its `about` in course.ts: the page, the
// card a link unfurls into and the sitemap read one source. The image comes from the folder's
// opengraph-image file.
export function sqlLessonMetadata(slug: SqlSlug): Metadata {
  const l = sqlLessonMeta(slug);
  return {
    title: `${l.title} | Learn SQL | Track Lab`,
    description: l.about,
    openGraph: { type: "article", title: l.title, description: l.about, url: sqlHref(slug) },
    twitter: { card: "summary_large_image", title: l.title, description: l.about },
  };
}

const ABOUT =
  "Eight lessons from a first SELECT to window functions and CTEs, each on the season aggregates of /warehouse, with exercises checked in the browser.";

export const sqlMetadata: Metadata = {
  title: "Learn SQL on the warehouse | Track Lab",
  description: ABOUT,
  openGraph: { type: "website", title: "Learn SQL on the warehouse", description: ABOUT, url: "/sql" },
  twitter: { card: "summary_large_image", title: "Learn SQL on the warehouse", description: ABOUT },
};
