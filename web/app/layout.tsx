import type { Metadata } from "next";
import localFont from "next/font/local";
import Link from "next/link";
import type { ReactNode } from "react";
import { Nav } from "../components/site/Nav";
import { DATA_SOURCES, SITE } from "../lib/sections";
import "./globals.css";

// Two webfonts, both the Latin subset of a variable file (OFL, see fonts/OFL*.txt) committed in
// this repo, so the build needs no network and no page asks a font CDN; both are preloaded and
// count against the 400,000 B page budgets. Space Grotesk: the headings, eyebrows, buttons and big
// figures of the inner pages, whose body text stays on the system stack. JetBrains Mono: every
// neon surface (the header, the footer and the home, P12), text and headings alike.
const display = localFont({
  src: "./fonts/SpaceGrotesk-latin-variable.woff2",
  weight: "300 700",
  variable: "--font-display-face",
  display: "swap",
});

const mono = localFont({
  src: "./fonts/JetBrainsMono-latin-variable.woff2",
  weight: "100 800",
  variable: "--font-mono-face",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: "Track Lab",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>
        <header className="site-header surface-neon">
          <div className="wrap site-header-row">
            <Link href="/" className="wordmark">
              track<span>lab</span>
              <span className="wordmark-caret" aria-hidden="true">
                _
              </span>
            </Link>
            <Nav />
          </div>
        </header>
        {children}
        <footer className="site-footer surface-neon">
          <div className="wrap site-footer-grid">
            <p className="wordmark">
              track<span>lab</span>
            </p>
            <div>
              <p className="site-footer-label">data</p>
              <p>
                SkillCorner&apos;s open data, published under the MIT license in{" "}
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
            <div>
              <p className="site-footer-label">code</p>
              <ul className="site-footer-links">
                <li>Code under the MIT license</li>
              </ul>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
