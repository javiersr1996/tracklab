import { readFileSync } from "node:fs";
import { join } from "node:path";

// `docs/bulletin.md`, one directory up from `web/` (`tracklab publish quality`
// writes it there from the CSVs), read at build time like `quality.json` in
// `lib/quality.ts`. Served as its own page rather than linked on GitHub: a
// `blob/<branch>` link would have to name a branch, and `docs/bulletin.md`
// does not exist on `main` until this one merges, so a page that reads the
// file locally is the link that works both before and after that merge.
const BULLETIN_PATH = join(process.cwd(), "..", "docs", "bulletin.md");

export default function BulletinPage() {
  const bulletin = readFileSync(BULLETIN_PATH, "utf-8");
  return (
    <main className="page">
      <pre className="bulletin">{bulletin}</pre>
    </main>
  );
}
