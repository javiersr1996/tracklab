import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import type { ReactNode } from "react";
import "./globals.css";

// The one webfont: headings, eyebrows, buttons and the big figures. next/font downloads it at
// build time and serves it from this site, so no page asks a font CDN; the Latin subset of the
// variable file is 22,288 B, measured against the 400,000 B page budgets. Body text stays on the
// system stack.
const display = Space_Grotesk({ subsets: ["latin"], variable: "--font-display-face", display: "swap" });

export const metadata: Metadata = {
  title: "Track Lab",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={display.variable}>
      <body>{children}</body>
    </html>
  );
}
