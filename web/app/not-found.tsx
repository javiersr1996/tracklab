import type { Metadata } from "next";
import Link from "next/link";
import { PageHead } from "../components/site/Band";

export const metadata: Metadata = { title: "Page not found | Track Lab" };

// The 404 (P19, task 151): the shared header and footer come from the root layout; the way back
// reuses the home page's two actions.
export default function NotFound() {
  return (
    <main id="main" className="page">
      <PageHead eyebrow="404">
        <h1>This page does not exist</h1>
        <p className="lede">The address may be mistyped, or the page may have moved.</p>
        <p className="hero-actions">
          <Link href="/" className="hero-action hero-action-primary">
            Home
          </Link>
          <Link href="/learn" className="hero-action">
            Learn
          </Link>
          <Link href="/sql" className="hero-action">
            SQL
          </Link>
        </p>
      </PageHead>
    </main>
  );
}
