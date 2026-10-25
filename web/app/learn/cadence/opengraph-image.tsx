import { lessonImage } from "../../../lib/learn/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Track Lab lesson";

export default function Image() {
  return lessonImage("cadence");
}
