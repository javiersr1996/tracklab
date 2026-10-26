import { sqlIndexImage } from "../../lib/sql/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Track Lab: Learn SQL on the warehouse";

export default function Image() {
  return sqlIndexImage();
}
