import type { Metadata } from "next";
import { Space_Grotesk } from "next/font/google";
import Link from "next/link";
import type { ReactNode } from "react";
import { Nav } from "../components/site/Nav";
import { DATA_SOURCES, REPO } from "../lib/sections";
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
      <body>
        <header className="site-header surface-dark">
          <div className="wrap site-header-row">
            <Link href="/" className="wordmark">
              track<span>lab</span>
            </Link>
            <Nav />
          </div>
        </header>
        {children}
        <footer className="site-footer surface-dark">
          <div className="wrap site-footer-grid">
            <p className="wordmark">
              track<span>lab</span>
            </p>
            <div>
              <p>
                Data: SkillCorner&apos;s open data, published under the MIT license in{" "}
                {DATA_SOURCES.map((s, i) => (
                  <span key={s.href}>
                    {i === 0 ? "" : i === DATA_SOURCES.length - 1 ? " and " : ", "}
                    <a href={s.href}>{s.name}</a> ({s.what})
                  </span>
                ))}
                . Credit for the tracking, event and body pose data goes to SkillCorner.
              </p>
              <p className="site-footer-note">Not affiliated with SkillCorner.</p>
            </div>
            <ul className="site-footer-links">
              <li>
                <a href={REPO}>Repository</a>
              </li>
              <li>
                <a href={`${REPO}/blob/main/docs/schema.md`}>Schema</a>
              </li>
              <li>Code under the MIT license</li>
            </ul>
          </div>
        </footer>
      </body>
    </html>
  );
}
