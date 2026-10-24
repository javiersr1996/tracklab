import type { ReactNode } from "react";
import type { Level } from "../../lib/learn/series";
import { PageHead } from "../site/Band";

// The head of a lesson: its place in the series, the question as the h1, then the lede.
export function LessonHead({ n, title, level, children }: { n: number; title: string; level: Level; children?: ReactNode }) {
  return (
    <PageHead eyebrow="Learn">
      <p className="lesson-meta">
        Lesson <span data-series-n={n}>{n}</span> · {level}
      </p>
      <h1>{title}</h1>
      {children}
    </PageHead>
  );
}
