"use client";

import { useRef } from "react";
import { useCountUp } from "../../lib/motion";

// A figure of the home (task 106) that counts up from 0 to `value` the first time it scrolls
// into view, with an ease-out, and lands on the exact number (`useCountUp`, the same count as the
// /engineering layers since P20). It is rendered with that number (the server, a page without JS
// and `prefers-reduced-motion` all show it and nothing moves), so the figure on the page is always
// the JSON's. `data-count` says where it is: still (reduced motion), idle (not seen yet), counting,
// done; the e2e read it. A "num" (task 112) is printed as `String(value)`, the way a lesson prints
// its figures, and counts with that many decimals.
const decimals = (value: number) => (String(value).split(".")[1] ?? "").length;

type Kind = "int" | "num";

function format(n: number, value: number, kind: Kind, final: boolean): string {
  if (kind === "num") return final ? String(value) : n.toFixed(decimals(value));
  return Math.round(n).toLocaleString("en-US");
}

export function Count({ value, kind }: { value: number; kind: Kind }) {
  const el = useRef<HTMLSpanElement>(null);
  const { phase, t } = useCountUp(el, 0.4);
  const final = phase !== "counting";
  return (
    <span ref={el} data-count={phase}>
      {format(final ? value : value * t, value, kind, final)}
    </span>
  );
}
