"use client";

import { useEffect, useRef, useState } from "react";
import { formatBytes } from "../../lib/format";
import { usePrefersReducedMotion } from "../../lib/motion";

// A figure of the home (task 106) that counts up from 0 to `value` the first time it scrolls
// into view, with an ease-out, and lands on the exact number. It is rendered with that number
// (the server, a page without JS and `prefers-reduced-motion` all show it and nothing moves),
// so the figure on the page is always the JSON's. `data-count` says where it is: still (reduced
// motion), idle (not seen yet), counting, done; the e2e read it.
const DURATION_MS = 1800;

type Phase = "idle" | "counting" | "done";

export function Count({ value, kind }: { value: number; kind: "int" | "bytes" }) {
  const reduceMotion = usePrefersReducedMotion();
  const el = useRef<HTMLSpanElement>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [shown, setShown] = useState(value);

  useEffect(() => {
    if (reduceMotion || !el.current) return;
    let raf = 0;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        setPhase("counting");
        const start = performance.now();
        const step = (now: number) => {
          const t = Math.min((now - start) / DURATION_MS, 1);
          setShown(Math.round(value * (1 - (1 - t) ** 3)));
          if (t < 1) raf = requestAnimationFrame(step);
          else setPhase("done");
        };
        raf = requestAnimationFrame(step);
      },
      { threshold: 0.4 },
    );
    observer.observe(el.current);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [reduceMotion, value]);

  return (
    <span ref={el} data-count={reduceMotion ? "still" : phase}>
      {kind === "bytes" ? formatBytes(shown) : shown.toLocaleString("en-US")}
    </span>
  );
}
