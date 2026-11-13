"use client";

import Link from "next/link";
import { type ReactNode, useState } from "react";
import { type IndexEntry, replayHref } from "../../lib/data";
import { Alternating } from "../replay/Alternating";

// The home's first screen (P12, task 108): the alternating replay as the background, the
// headline the page passes as children over its foot, and two actions under it. Since P23 the
// first opens the lessons; the second opens the possession playing right now on
// /tracking/replay, so it follows the alternation.
export function Hero({ entries, children }: { entries: IndexEntry[]; children: ReactNode }) {
  const [current, setCurrent] = useState(entries[0]);
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-stage">
        <Alternating entries={entries} hero onEntry={setCurrent} />
      </div>
      <div className="wrap hero-copy">
        {children}
        <p className="hero-actions">
          <Link href="/learn" className="hero-action hero-action-primary">
            Browse the lessons
          </Link>
          <Link href={replayHref(current)} className="hero-action">
            Open replay
          </Link>
        </p>
      </div>
    </section>
  );
}
