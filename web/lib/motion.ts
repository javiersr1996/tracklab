import { type RefObject, useEffect, useState, useSyncExternalStore } from "react";

// `prefers-reduced-motion` read through `useSyncExternalStore` instead of a
// `useEffect` + `setState`: the value is available during render itself (SSR
// gets `false` from `getServerSnapshot`, the client's real value replaces it
// before paint), so a reduced-motion display is derived, never set, and an
// animation effect only has to decide whether to start. Shared by the platform
// flow, the home's hero, its counters and its cards (P12).
function subscribeReducedMotion(onChange: () => void): () => void {
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function getReducedMotionSnapshot(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function getReducedMotionServerSnapshot(): boolean {
  return false;
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    getReducedMotionSnapshot,
    getReducedMotionServerSnapshot,
  );
}

// How long a figure takes to count up (P20, task 174): every counter that uses `useCountUp` lands
// on its number this long after it comes into view.
export const COUNT_MS = 1200;

export type CountPhase = "still" | "idle" | "counting" | "done";

// A figure's count from 0 to its number, once, the first time `ref` comes into view, with an
// ease-out: `t` is the share of the number to show, 1 except while counting, so the server, a page
// without JS and a screenshot taken before the figure is seen all show the number itself.
// `phase` says where it is for the e2e: still (reduced motion, which never counts), idle (not seen
// yet), counting, done.
export function useCountUp(
  ref: RefObject<Element | null>,
  threshold = 0,
  rootMargin = "0px",
): { phase: CountPhase; t: number } {
  const reduceMotion = usePrefersReducedMotion();
  const [phase, setPhase] = useState<"idle" | "counting" | "done">("idle");
  const [t, setT] = useState(1);

  useEffect(() => {
    if (reduceMotion || !ref.current) return;
    let raf = 0;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        setPhase("counting");
        setT(0);
        const start = performance.now();
        const step = (now: number) => {
          const p = Math.min((now - start) / COUNT_MS, 1);
          setT(1 - (1 - p) ** 3);
          if (p < 1) raf = requestAnimationFrame(step);
          else setPhase("done");
        };
        raf = requestAnimationFrame(step);
      },
      { threshold, rootMargin },
    );
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [reduceMotion, ref, threshold, rootMargin]);

  // A reduced-motion switch mid-count lands the number at once.
  if (reduceMotion) return { phase: "still", t: 1 };
  return { phase, t: phase === "counting" ? t : 1 };
}
