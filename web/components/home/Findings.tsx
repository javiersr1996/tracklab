import Link from "next/link";
import type { ReactNode } from "react";
import { GRAVITY_HOOK } from "../../lib/learn/gravity-data";
import { PLATFORM } from "../../lib/platform";
import { readRuns } from "../../lib/runs/data";
import { STAGE_NAMES } from "../../lib/runs/types";

// What the site found (P20, task 175): one claim per card, its figure large, in the words of the
// page the card opens, never stronger. Every figure is read here at build time through the loaders
// those pages use (quality.json's hook, platform.json, runs.json); none is typed.
// `data-finding` names the card for the e2e, which compare each figure with its file.

interface Finding {
  key: string;
  href: string;
  value: ReactNode;
  vs: ReactNode;
  title: string;
  about: ReactNode;
}

function findings(): Finding[] {
  const runs = readRuns();
  // The card says "dead at" a stage with no candidates left; if the file ever says otherwise, the
  // claim has expired and the build stops here rather than print it.
  const died = runs.status === "dead" ? runs.dead_at : null;
  const candidates = died ? runs.stages[died].figures.candidates : undefined;
  if (!died || typeof candidates !== "number") throw new Error("runs.json: no stage with its candidates to quote");

  return [
    {
      key: "gravity",
      href: "/learn/gravity",
      value: (
        <>
          <span data-fig="g_data">{GRAVITY_HOOK.g_data}</span>
          <span className="finding-unit">m/s²</span>
        </>
      ),
      vs: (
        <>
          standard gravity <span data-fig="g_real">{GRAVITY_HOOK.g_real}</span> m/s²
        </>
      ),
      title: "The ball falls as if the Earth were lighter",
      about: "The g of the lesson's shot: a parabola fitted to a basketball's height in flight, in SkillCorner's open basketball tracking.",
    },
    {
      key: "bytes",
      href: "/engineering",
      value: (
        <span data-fig="title" data-platform-title>
          {PLATFORM.title}
        </span>
      ),
      vs: <span data-fig="subtitle">{PLATFORM.subtitle}</span>,
      title: `One pipeline run, ${PLATFORM.layers.length} layers`,
      about: "What the latest build read from SkillCorner and what it published from it, as the build itself measured them.",
    },
    {
      key: "runs",
      href: "/tracking/runs",
      value: (
        <>
          <span data-fig="candidates">{candidates}</span>
          <span className="finding-unit">candidates</span>
        </>
      ),
      vs: (
        <>
          dead at{" "}
          <span data-fig="dead_at" data-stage={died}>
            {STAGE_NAMES[died]}
          </span>
        </>
      ),
      title: "The project that died, published dead",
      about: (
        <>
          The run that moves nobody: the negative is published under the same title. The held-out half (
          <span data-fig="held_out">{runs.never_opened.match_ids.length}</span> matches) was never opened.
        </>
      ),
    },
  ];
}

export function Findings() {
  return (
    <ul className="findings">
      {findings().map((f) => (
        <li key={f.key} className="finding" data-finding={f.key}>
          <p className="finding-value">{f.value}</p>
          <p className="finding-vs">{f.vs}</p>
          <h3>
            <Link href={f.href} prefetch={false}>
              {f.title}
            </Link>
          </h3>
          <p className="finding-about">{f.about}</p>
          <p className="finding-tag" aria-hidden="true">
            {f.href} →
          </p>
        </li>
      ))}
    </ul>
  );
}
