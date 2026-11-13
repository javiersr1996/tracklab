import { lessonImage } from "../../../lib/learn/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Pitch & Parquet lesson";

export default function Image() {
  return lessonImage("speed");
}
