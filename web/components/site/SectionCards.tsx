import Link from "next/link";
import { Preview } from "../home/Preview";

// The sections as cards, each with its sketch (task 107): the home page lists every one, a hub
// (`/tracking`, P15) the pages under it. The whole card is the link's target.
export function SectionCards({ sections }: { sections: readonly { href: string; title: string; about: string }[] }) {
  return (
    <ul className="cards">
      {sections.map((s) => (
        <li key={s.href} className="card" data-section={s.href}>
          <Preview href={s.href} />
          <p className="card-tag">{s.href}</p>
          <h3>
            <Link href={s.href}>{s.title}</Link>
          </h3>
          <p className="card-about">{s.about}</p>
          <span className="card-arrow" aria-hidden="true">
            →
          </span>
        </li>
      ))}
    </ul>
  );
}
