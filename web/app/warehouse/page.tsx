import Link from "next/link";
import { Warehouse } from "../../components/warehouse/Warehouse";

// Task 42 leaves the engine and a bare query box here; task 43 turns this page into the
// console (schemas from warehouse.json, example queries, the bytes panel, the scope line) and
// links it from the home page.
export default function WarehousePage() {
  return (
    <main className="page">
      <h1>Warehouse</h1>
      <p>
        SQL over the season aggregates, run by DuckDB in this browser on Parquet files read by
        HTTP range. Nothing of the engine is downloaded until you press Run.
      </p>
      <Warehouse />
      <p>
        <Link href="/">Track Lab</Link>
      </p>
    </main>
  );
}
