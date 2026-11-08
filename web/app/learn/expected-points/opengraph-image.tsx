import { lessonImage } from "../../../lib/learn/og";

// Generic, like every lesson's card: the question and the mark, no figure (spec P14).
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Track Lab lesson";

export default function Image() {
  return lessonImage("expected-points");
}
