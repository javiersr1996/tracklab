import Link from "next/link";
import { Alternating } from "../components/replay/Alternating";
import { POSSESSIONS, rowsOf, SPORTS } from "../lib/data";

const REPO = "https://github.com/javiersr1996/tracklab";

// One possession of each sport, alternating: the first published of each.
const SHOWCASE = SPORTS.map((sport) => POSSESSIONS.find((p) => p.sport === sport)!);

export default function HomePage() {
  return (
    <main className="page">
      <h1>One schema, two sports, one renderer</h1>
      <Alternating entries={SHOWCASE} />
      <p>
        {SHOWCASE.map((p) => `${p.sport} at ${p.sample_rate_hz} fps`).join(" and ")}, read
        from the same table by the same query:
      </p>
      <pre>
        <code>SELECT * FROM frames WHERE sport = ?</code>
      </pre>
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
      <p>
        <Link href="/replay">Replay any possession</Link> ·{" "}
        <Link href="/platform">How this was built</Link> ·{" "}
        <Link href="/quality">Data quality</Link> · <Link href="/warehouse">Warehouse</Link> ·{" "}
        <Link href="/runs">The run that moves nobody</Link> ·{" "}
        <a href={REPO}>Repository</a> ·{" "}
        <a href={`${REPO}/blob/main/docs/schema.md`}>Schema</a>
      </p>
    </main>
  );
}
