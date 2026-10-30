import { useSyncExternalStore } from "react";

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
