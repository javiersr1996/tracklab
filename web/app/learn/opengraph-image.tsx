import { learnImage } from "../../lib/learn/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Pitch & Parquet: Learn from the tracking data";

export default function Image() {
  return learnImage();
}
