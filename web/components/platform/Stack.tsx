import { PLATFORM } from "../../lib/platform";
import pgJson from "../../public/data/warehouse_pg.json";

// The stack strip: each tool of the run with the version `platform.json` recorded, Parquet, and
// the Postgres version `warehouse_pg.json` measured. /engineering and /about print the same one.
export function Stack() {
  return (
    <ul className="platform-stack" data-stack>
      {Object.entries(PLATFORM.run.versions).map(([tool, version]) => (
        <li key={tool} data-tool={tool}>
          {tool} <span>{version}</span>
        </li>
      ))}
      <li>Parquet</li>
      <li data-tool="postgres">
        Postgres <span>{pgJson.source.version}</span>
      </li>
    </ul>
  );
}
