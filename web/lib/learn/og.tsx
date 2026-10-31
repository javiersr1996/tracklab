import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { LESSONS } from "./series";

// The card a link to a lesson unfurls into: the question, "Lesson n · Level" and the mark, in the
// site's neon (P13): the page's near-black, the eyebrow and "lab" in cyan (13.1:1), the question in
// the ink (16.3:1). No figure of any kind, so the rule that every number comes from an artifact has
// nothing to check. Satori reads TTF, not WOFF2: JetBrainsMono-latin-bold.ttf is the site's own
// JetBrains Mono file instanced at wght 700 with fontTools (OFL, app/fonts/OFL-JetBrainsMono.txt),
// read here at build time and never served.
export const OG_SIZE = { width: 1200, height: 630 };
export const OG_TYPE = "image/png";

const FONT = join(process.cwd(), "app", "fonts", "JetBrainsMono-latin-bold.ttf");

export async function card(eyebrow: string, title: string) {
  const data = await readFile(FONT);
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#030712", color: "#e2e8f0", fontFamily: "JetBrains Mono" }}>
        <div style={{ display: "flex", fontSize: 30, letterSpacing: 3, textTransform: "uppercase", color: "#00e5ff" }}>{eyebrow}</div>
        <div style={{ display: "flex", fontSize: title.length > 34 ? 68 : 80, lineHeight: 1.15, letterSpacing: -1 }}>{title}</div>
        <div style={{ display: "flex", fontSize: 44, letterSpacing: -1, color: "#ffffff" }}>
          track<span style={{ color: "#00e5ff" }}>lab</span>
        </div>
      </div>
    ),
    { ...OG_SIZE, fonts: [{ name: "JetBrains Mono", data, weight: 700, style: "normal" }] },
  );
}

export function lessonImage(slug: string) {
  const l = LESSONS.find((x) => x.slug === slug);
  if (!l) throw new Error(`no lesson ${slug} in series.ts`);
  return card(`Lesson ${l.n} · ${l.level}`, l.title);
}

export const learnImage = () => card("Learn", "Learn from the tracking data");
