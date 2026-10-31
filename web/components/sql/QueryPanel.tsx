"use client";

import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../../lib/motion";

// The head panel of a /sql lesson (task 112): the lesson's worked example typed out behind a caret
// the first time it comes into view, then its answer. The server, a page without JS and
// `prefers-reduced-motion` show the whole query and the answer, and nothing moves. `data-type`
// says where it is, like the home's `data-count`: still, idle, typing, done.
const MS_PER_CHAR = 24;
const MAX_MS = 3000;

type Phase = "idle" | "typing" | "done";
type Run = { text: string; comment: boolean };

// The query as runs of lines, the `--` comments apart so they print muted.
const runsOf = (sql: string): Run[] => sql.split(/(?<=\n)/).map((text) => ({ text, comment: text.trimStart().startsWith("--") }));

// The runs between character `from` and character `to` of the query.
function cut(runs: Run[], from: number, to: number): Run[] {
  const out: Run[] = [];
  let at = 0;
  for (const r of runs) {
    const a = Math.max(from, at);
    const b = Math.min(to, at + r.text.length);
    if (b > a) out.push({ text: r.text.slice(a - at, b - at), comment: r.comment });
    at += r.text.length;
  }
  return out;
}

const print = (runs: Run[]) =>
  runs.map((r, i) => (
    <span key={i} className={r.comment ? "head-sql-comment" : undefined}>
      {r.text}
    </span>
  ));

export function QueryPanel({ sql, answer, note }: { sql: string; answer: string; note: string }) {
  const reduceMotion = usePrefersReducedMotion();
  const pre = useRef<HTMLPreElement>(null);
  const caret = useRef<HTMLSpanElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [typed, setTyped] = useState(sql.length);

  useEffect(() => {
    if (reduceMotion || !pre.current) return;
    const box = pre.current;
    let raf = 0;
    const perChar = Math.min(MS_PER_CHAR, MAX_MS / sql.length);
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        setPhase("typing");
        setTyped(0);
        box.scrollTop = 0;
        const start = performance.now();
        const step = (now: number) => {
          const k = Math.min(sql.length, Math.floor((now - start) / perChar));
          setTyped(k);
          // Keep the caret in the box's view without scrolling the page.
          const c = caret.current;
          if (c && c.offsetTop + c.offsetHeight > box.scrollTop + box.clientHeight) {
            box.scrollTop = c.offsetTop + c.offsetHeight - box.clientHeight;
          }
          if (k < sql.length) raf = requestAnimationFrame(step);
          else setPhase("done");
        };
        raf = requestAnimationFrame(step);
      },
      { threshold: 0.4 },
    );
    observer.observe(box);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [reduceMotion, sql]);

  const typing = !reduceMotion && phase === "typing";
  const k = typing ? typed : sql.length;
  const runs = runsOf(sql);
  return (
    <figure className="head-panel head-panel-sql" data-head-panel="query" data-type={reduceMotion ? "still" : phase}>
      <figcaption className="head-panel-label">Worked example</figcaption>
      {/* Scrollable when the query is longer than the box, so it takes the focus like any scroller. */}
      <pre ref={pre} className="head-sql" tabIndex={0}>
        <code data-head-sql>
          {print(cut(runs, 0, k))}
          <span ref={caret} className="head-caret" aria-hidden="true" />
          <span className="head-sql-rest">{print(cut(runs, k, sql.length))}</span>
        </code>
      </pre>
      <p className={typing ? "head-answer head-answer-waiting" : "head-answer"}>
        <span className="head-answer-arrow" aria-hidden="true">
          →{" "}
        </span>
        <span data-head-answer>{answer}</span>
      </p>
      <p className="head-answer-note">{note}</p>
    </figure>
  );
}
