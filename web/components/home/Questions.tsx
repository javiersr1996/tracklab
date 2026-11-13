import Link from "next/link";
import { LESSONS, lessonHref } from "../../lib/learn/series";
import { Thumb } from "../learn/Thumb";

// The lessons on the home (P23): every published one with the drawing /learn shows beside it, its
// number, its sport and its question, the whole card the link. A rail that scrolls inside itself on
// a phone, a grid from 1000 px. The links do not prefetch, so the home's bytes stay its own.
export const HOME_LESSONS = LESSONS.filter((l) => l.status === "published");

export function Questions() {
  return (
    <ol className="questions" aria-label="Lessons">
      {HOME_LESSONS.map((l) => (
        <li key={l.slug} className="question" data-lesson={l.slug}>
          <Thumb slug={l.slug} />
          <p className="lesson-meta">
            Lesson {l.n} · {l.sport}
          </p>
          <h3>
            <Link href={lessonHref(l)} prefetch={false}>
              {l.title}
            </Link>
          </h3>
        </li>
      ))}
    </ol>
  );
}
