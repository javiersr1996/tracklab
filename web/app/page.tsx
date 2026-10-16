import Link from "next/link";
import { Alternating } from "../components/replay/Alternating";
import { Band } from "../components/site/Band";
import { POSSESSIONS, rowsOf, SPORTS } from "../lib/data";
import { SECTIONS } from "../lib/sections";

// One possession of each sport, alternating: the first published of each.
const SHOWCASE = SPORTS.map((sport) => POSSESSIONS.find((p) => p.sport === sport)!);

export default function HomePage() {
  return (
    <main className="home">
      <Band dark className="hero">
        <div className="hero-grid">
          <div>
            <p className="eyebrow">Open tracking data</p>
            <h1>
              One schema, two sports, <span className="accent">one renderer</span>
            </h1>
            <p className="lede">
              Track Lab takes SkillCorner&apos;s open tracking and event data for basketball and
              football and conforms both sports into one silver schema with DuckDB and dbt.
            </p>
          </div>
          <div className="hero-media">
            <Alternating entries={SHOWCASE} />
          </div>
        </div>
      </Band>

      <Band>
        <div className="split">
          <div>
            <p>
              {SHOWCASE.map((p) => `${p.sport} at ${p.sample_rate_hz} fps`).join(" and ")}, read
              from the same table by the same query:
            </p>
            <pre>
              <code>SELECT * FROM frames WHERE sport = ?</code>
            </pre>
          </div>
          <table>
            <thead>
              <tr>
                <th scope="col">sport</th>
                <th scope="col">rows in frames</th>
              </tr>
            </thead>
            <tbody>
              {SPORTS.map((sport) => (
                <tr key={sport}>
                  <td>{sport}</td>
                  <td data-rows={sport}>{rowsOf("frames", sport).toLocaleString("en-US")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Band>

      <Band>
        <h2 className="eyebrow">Sections</h2>
        <ul className="cards">
          {SECTIONS.map((s) => (
            <li key={s.href} className="card surface-dark">
              <p className="card-tag">{s.href}</p>
              <h3>
                <Link href={s.href}>{s.title}</Link>
              </h3>
              <p>{s.about}</p>
              <span className="card-arrow" aria-hidden="true">
                →
              </span>
            </li>
          ))}
        </ul>
      </Band>
    </main>
  );
}
