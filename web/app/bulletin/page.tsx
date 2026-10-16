import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Band, PageHead } from "../../components/site/Band";

// `docs/bulletin.md`, one directory up from `web/` (`tracklab publish quality`
// writes it there from the CSVs), read at build time like `quality.json` in
// `lib/quality.ts`. Served as its own page rather than linked on GitHub: a
// `blob/<branch>` link would have to name a branch, and `docs/bulletin.md`
// does not exist on `main` until this one merges, so a page that reads the
// file locally is the link that works both before and after that merge.
const BULLETIN_PATH = join(process.cwd(), "..", "docs", "bulletin.md");

export default function BulletinPage() {
  const bulletin = readFileSync(BULLETIN_PATH, "utf-8");
  // The file's own title line is the page's heading; the rest is shown as written.
  const [first, ...rest] = bulletin.split("\n");
  const title = first.startsWith("# ") ? first.slice(2) : null;
  return (
    <main className="page">
      <PageHead eyebrow="Data quality">{title ? <h1>{title}</h1> : null}</PageHead>
      <Band>
        <pre className="bulletin">{title ? rest.join("\n").trimStart() : bulletin}</pre>
      </Band>
    </main>
  );
}
