import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { ReactNode } from "react";
import { Band, PageHead } from "../../../components/site/Band";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Data quality bulletin | Track Lab",
  description:
    "The data quality bulletin: what the checks on the two tracking bundles found, written from the quality tables at each build.",
};

// `docs/bulletin.md`, one directory up from `web/` (`tracklab publish quality`
// writes it there from the CSVs), read at build time like `quality.json` in
// `lib/quality.ts`. Served as its own page rather than linked on GitHub: a
// `blob/<branch>` link would have to name a branch, and `docs/bulletin.md`
// does not exist on `main` until this one merges, so a page that reads the
// file locally is the link that works both before and after that merge.
const BULLETIN_PATH = join(process.cwd(), "..", "docs", "bulletin.md");

// The Markdown the bulletin uses, and no more (P15: until then `## Detection` showed as written):
// `##` headings, `>` quotes and paragraphs, with `code` and [links](url) inside them.
function inline(text: string): ReactNode[] {
  return text.split(/(\[[^\]]+\]\([^)]+\)|`[^`]+`)/).map((part, i) => {
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) return <a key={i} href={link[2]}>{inline(link[1])}</a>;
    if (part.length > 1 && part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    return part;
  });
}

function block(text: string, i: number): ReactNode {
  if (text.startsWith("## ")) return <h2 key={i}>{inline(text.slice(3))}</h2>;
  if (text.startsWith("> ")) {
    return (
      <blockquote key={i}>
        <p>{inline(text.replace(/^> ?/gm, ""))}</p>
      </blockquote>
    );
  }
  return <p key={i}>{inline(text)}</p>;
}

export default function BulletinPage() {
  const bulletin = readFileSync(BULLETIN_PATH, "utf-8");
  // The file's own title line is the page's heading; the rest is its blocks, one per blank line.
  const [first, ...rest] = bulletin.split("\n");
  const title = first.startsWith("# ") ? first.slice(2) : null;
  const blocks = (title ? rest.join("\n") : bulletin)
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean);
  return (
    <main id="main" className="page">
      <PageHead eyebrow="Data quality">
        {title ? <h1>{title}</h1> : null}
        <p className="lede" data-lede>
          The quality checks written up in prose: what each one measures, what it found across the
          matches, and what that means for anyone building on the data.
        </p>
      </PageHead>
      <Band>
        <div className="bulletin">{blocks.map(block)}</div>
      </Band>
    </main>
  );
}
