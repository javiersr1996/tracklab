import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { LESSONS } from "./series";

// The card a link to a lesson unfurls into: the question, "Lesson n · Level" and the mark. No
// figure of any kind, so the rule that every number comes from an artifact has nothing to check.
// Satori reads TTF, not WOFF2: SpaceGrotesk-latin-bold.ttf is Space Grotesk's variable file
// instanced at wght 700 (OFL, app/fonts/OFL.txt), read here at build time and never served.
export const OG_SIZE = { width: 1200, height: 630 };
export const OG_TYPE = "image/png";

const FONT = join(process.cwd(), "app", "fonts", "SpaceGrotesk-latin-bold.ttf");

export async function card(eyebrow: string, title: string) {
  const data = await readFile(FONT);
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#252525", color: "#f2f2f2", fontFamily: "Space Grotesk" }}>
        <div style={{ display: "flex", fontSize: 36, letterSpacing: 4, textTransform: "uppercase", color: "#e0883a" }}>{eyebrow}</div>
        <div style={{ display: "flex", fontSize: title.length > 40 ? 76 : 92, lineHeight: 1.1, letterSpacing: -2 }}>{title}</div>
        <div style={{ display: "flex", fontSize: 44, letterSpacing: -1 }}>
          track<span style={{ color: "#e0883a" }}>lab</span>
        </div>
      </div>
    ),
    { ...OG_SIZE, fonts: [{ name: "Space Grotesk", data, weight: 700, style: "normal" }] },
  );
}

export function lessonImage(slug: string) {
  const l = LESSONS.find((x) => x.slug === slug);
  if (!l) throw new Error(`no lesson ${slug} in series.ts`);
  return card(`Lesson ${l.n} · ${l.level}`, l.title);
}

export const learnImage = () => card("Learn", "Learn from the tracking data");
