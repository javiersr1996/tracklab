import { card } from "../../lib/learn/og";

// Generic, like the lessons' cards: words and the mark, no figure and no shot (spec P14).
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Track Lab: Where EuroLeague shoots from";

export default function Image() {
  return card("EuroLeague · shot atlas", "Where EuroLeague shoots from");
}
