"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { formatBytes } from "../../lib/format";
import { counterKey, layerDurations, type PlatformLayer } from "../../lib/platform";

// Five layers, one packet moving through them: each layer's counters climb
// from 0 to the exact figure in `platform.json` over a time proportional to
// its own slowest step (`layerDurations`), the layer's time bar fills to
// match, and the cycle loops. State lives on `figure.platform`'s own
// attributes (`data-state`, `data-layer`, `data-cycle`), the same pattern as
// `figure.hook` in `components/quality/Hook.tsx`, so Playwright can drive the
// sequence instead of watching a capture.
const CYCLE_S = 8;
const MIN_LAYER_S = 0.6;
const DONE_HOLD_MS = 700;

type MotionState = "idle" | "playing" | "done";

function formatCount(n: number): string {
  return n.toLocaleString("en-US");
}

function valueAt(final: number, t: number): number {
  return Math.round(final * t);
}

// `prefers-reduced-motion` read through `useSyncExternalStore` instead of a
// `useEffect` + `setState`: the value is available during render itself (SSR
// gets `false` from `getServerSnapshot`, the client's real value replaces it
// before paint), so the reduced-motion display below is derived, never set,
// and the animation effect only has to decide whether to start.
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

function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReducedMotion,
    getReducedMotionSnapshot,
    getReducedMotionServerSnapshot,
  );
}

export function Flow({ layers }: { layers: PlatformLayer[] }) {
  const reduceMotion = usePrefersReducedMotion();
  const [motionState, setMotionState] = useState<MotionState>("idle");
  const [cycle, setCycle] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [t, setT] = useState(0);

  useEffect(() => {
    if (reduceMotion) return;

    let raf = 0;
    let holdTimer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

    const durationsMs = layerDurations(
      layers.map((l) => l.seconds),
      CYCLE_S,
      MIN_LAYER_S,
    ).map((s) => s * 1000);

    function playLayer(index: number, cycleNumber: number) {
      if (cancelled) return;
      setActiveIndex(index);
      setT(0);
      const start = performance.now();
      const duration = durationsMs[index];

      const frame = (now: number) => {
        if (cancelled) return;
        const progress = duration > 0 ? Math.min((now - start) / duration, 1) : 1;
        setT(progress);
        if (progress < 1) {
          raf = requestAnimationFrame(frame);
          return;
        }
        const next = index + 1;
        if (next < layers.length) {
          playLayer(next, cycleNumber);
        } else {
          setMotionState("done");
          holdTimer = setTimeout(() => {
            if (!cancelled) startCycle(cycleNumber + 1);
          }, DONE_HOLD_MS);
        }
      };
      raf = requestAnimationFrame(frame);
    }

    function startCycle(cycleNumber: number) {
      if (cancelled) return;
      setCycle(cycleNumber);
      setMotionState("playing");
      playLayer(0, cycleNumber);
    }

    startCycle(1);

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      if (holdTimer) clearTimeout(holdTimer);
    };
  }, [reduceMotion, layers]);

  // Reduced motion never runs the effect above, so it is never state to set:
  // the figure just renders as if the cycle had already finished.
  const effectiveState: MotionState = reduceMotion ? "done" : motionState;
  const effectiveIndex = reduceMotion ? layers.length - 1 : activeIndex;
  const effectiveCycle = reduceMotion ? 1 : cycle;

  const activeLayerName = layers[Math.min(effectiveIndex, layers.length - 1)].layer;

  return (
    <figure
      className="platform"
      data-state={effectiveState}
      // No layer while idle: nothing is playing yet, and a "raw" here would read
      // as the first step of a sequence that has not started.
      data-layer={effectiveState === "idle" ? undefined : activeLayerName}
      data-cycle={effectiveCycle}
    >
      <div className="platform-layers">
        {layers.map((layer, index) => {
          const phase =
            effectiveState === "done" || index < effectiveIndex
              ? "finished"
              : effectiveState === "playing" && index === effectiveIndex
                ? "active"
                : "pending";
          const localT = phase === "finished" ? 1 : phase === "active" ? t : 0;
          const bytes = valueAt(layer.bytes, localT);

          return (
            <div className="platform-layer" key={layer.layer} data-phase={phase}>
              <h3>{layer.layer}</h3>
              <div className="platform-bar">
                <div className="platform-bar-fill" style={{ width: `${Math.round(localT * 100)}%` }} />
              </div>
              <dl className="platform-counters">
                <div>
                  <dt>files</dt>
                  <dd data-counter={counterKey(layer.layer, "files")}>
                    {formatCount(valueAt(layer.files, localT))}
                  </dd>
                </div>
                {layer.rows !== null && (
                  <div>
                    <dt>rows</dt>
                    <dd data-counter={counterKey(layer.layer, "rows")}>
                      {formatCount(valueAt(layer.rows, localT))}
                    </dd>
                  </div>
                )}
                <div>
                  <dt>bytes</dt>
                  <dd data-counter={counterKey(layer.layer, "bytes")}>{formatCount(bytes)}</dd>
                  <span className="platform-bytes-human">({formatBytes(bytes)})</span>
                </div>
                <div>
                  <dt>seconds (longest step)</dt>
                  <dd data-counter={counterKey(layer.layer, "seconds")}>
                    {(layer.seconds * localT).toFixed(1)}
                  </dd>
                </div>
              </dl>
              {layer.note && <p className="platform-note">{layer.note}</p>}
            </div>
          );
        })}
      </div>
    </figure>
  );
}
