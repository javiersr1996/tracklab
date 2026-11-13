import type { Metadata } from "next";
import { Band, PageHead } from "../../components/site/Band";
import { SectionCards } from "../../components/site/SectionCards";
import { SECTIONS } from "../../lib/sections";

export const metadata: Metadata = {
  title: "Tracking | Track Lab",
  description:
    "The tracking data itself, drawn in your browser: replay a possession, see the run that moves nobody, follow each player's body pose, see where each football position plays.",
};

// The hub of the tracking itself (P15, task 121): the pages under it (the occupancy map since P23),
// as the home page's cards, with no figure of its own.
const PAGES = SECTIONS.filter((s) => s.href.startsWith("/tracking/"));

export default function TrackingPage() {
  return (
    <main id="main" className="page">
      <PageHead eyebrow="Open tracking data">
        <h1>Tracking</h1>
        <p className="lede">
          The tracking data itself, drawn in your browser: replay a possession, see the run that
          moves nobody, follow each player&apos;s body pose, see where each football position plays.
        </p>
      </PageHead>
      <Band>
        <h2 className="eyebrow">Pages</h2>
        <SectionCards sections={PAGES} />
      </Band>
    </main>
  );
}
