import type { Metadata } from "next";
import { LESSONS } from "./series";

// The title is the lesson's question, the description its `about` in series.ts: the page, the
// card a link unfurls into and the sitemap read one source. The image comes from the folder's
// opengraph-image file.
export function lessonMetadata(slug: string): Metadata {
  const l = LESSONS.find((x) => x.slug === slug);
  if (!l) throw new Error(`no lesson ${slug} in series.ts`);
  return {
    title: l.title,
    description: l.about,
    openGraph: { type: "article", title: l.title, description: l.about, url: `/learn/${l.slug}` },
    twitter: { card: "summary_large_image", title: l.title, description: l.about },
  };
}

export const learnMetadata: Metadata = {
  title: "Learn from the tracking data",
  description: "Short lessons that each start from a question about SkillCorner's open tracking data or the EuroLeague's shot counts and end with a query you can run.",
  openGraph: { type: "website", title: "Learn from the tracking data", url: "/learn" },
  twitter: { card: "summary_large_image", title: "Learn from the tracking data" },
};
