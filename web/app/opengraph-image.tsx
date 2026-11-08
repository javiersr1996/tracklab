import { card } from "../lib/learn/og";

// The card for every page that has no image of its own (P19, task 150): the lessons, /sql and
// /euroleague keep theirs. Words and the mark, no figure, like theirs.
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Track Lab: open tracking data";

export default function Image() {
  return card("Open tracking data", "One schema, two sports, one renderer");
}
