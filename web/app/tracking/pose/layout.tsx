import type { ReactNode } from "react";
import { sectionMetadata } from "../../../lib/page-metadata";

// The page is a client component, which cannot export metadata: this layout does.
export const metadata = sectionMetadata("/tracking/pose");

export default function PoseLayout({ children }: { children: ReactNode }) {
  return children;
}
