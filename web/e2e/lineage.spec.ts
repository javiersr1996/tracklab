import { expect, test } from "@playwright/test";

// `components/platform/Lineage.tsx` (task 36): a hand-written SVG graph plus
// two server-rendered tables on `/engineering`. The closure test below computes
// ancestors/descendants of its own, straight from `lineage.json`'s edges,
// rather than importing the app's `lib/lineage-graph.ts` -- so a mutation to
// that module (e.g. swapping `from`/`to` in `ancestors()`) is still visible
// here: the two implementations would then disagree.

interface LineageNode {
  key: string;
  group: string;
  description: string;
  schema: string;
  dbt_tests?: number;
  dbt_columns?: string[];
}
interface LineageEdge {
  from: string;
  to: string;
}
interface LineageJson {
  groups: string[];
  nodes: LineageNode[];
  edges: LineageEdge[];
}

interface PlatformMatch {
  sport: string;
  match_id: number;
  raw_bytes: number;
  raw_bytes_read: number;
  bronze_tracking_rows: number;
  silver_frames_rows: number;
  silver_events_rows: number;
  published_possessions: number;
  published_bytes: number;
}
interface PlatformJson {
  layers: { layer: string; bytes_pinned?: number }[];
  matches: PlatformMatch[];
  season_files: { bytes: number };
}

// Independent BFS, upward: every node with a directed path of edges into
// `key` (`edge.from` is upstream), never `key` itself.
function ancestorsOf(edges: LineageEdge[], key: string): Set<string> {
  const parentsOf = new Map<string, string[]>();
  for (const e of edges) parentsOf.set(e.to, [...(parentsOf.get(e.to) ?? []), e.from]);
  const seen = new Set<string>();
  const stack = [...(parentsOf.get(key) ?? [])];
  while (stack.length > 0) {
    const n = stack.pop() as string;
    if (seen.has(n)) continue;
    seen.add(n);
    stack.push(...(parentsOf.get(n) ?? []));
  }
  return seen;
}

// The mirror, downward.
function descendantsOf(edges: LineageEdge[], key: string): Set<string> {
  const childrenOf = new Map<string, string[]>();
  for (const e of edges) childrenOf.set(e.from, [...(childrenOf.get(e.from) ?? []), e.to]);
  const seen = new Set<string>();
  const stack = [...(childrenOf.get(key) ?? [])];
  while (stack.length > 0) {
    const n = stack.pop() as string;
    if (seen.has(n)) continue;
    seen.add(n);
    stack.push(...(childrenOf.get(n) ?? []));
  }
  return seen;
}

test("as many [data-node] and [data-edge] as lineage.json has nodes and edges", async ({ page }) => {
  const lineage = (await (await page.request.get("/data/lineage.json")).json()) as LineageJson;

  await page.goto("/engineering");

  await expect(page.locator("[data-node]")).toHaveCount(lineage.nodes.length);
  await expect(page.locator("[data-edge]")).toHaveCount(lineage.edges.length);
});

test("clicking silver_frames lights exactly its ancestor and descendant closures", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));

  const lineage = (await (await page.request.get("/data/lineage.json")).json()) as LineageJson;
  const up = ancestorsOf(lineage.edges, "silver_frames");
  const down = descendantsOf(lineage.edges, "silver_frames");
  // Sanity on the fixture itself: silver_frames has real dependencies both
  // ways, so this test is not passing by construction on an edge case.
  expect(up.size).toBeGreaterThan(0);
  expect(down.size).toBeGreaterThan(0);

  await page.goto("/engineering");
  await page.locator('[data-node="silver_frames"]').click();

  // Scoped to `[data-node]`: edges carry the same `data-lit` values on their
  // own `<path>` (task 36's "Qué" only asks for it on nodes to be exact).
  await expect(page.locator('[data-node][data-selected="true"]')).toHaveCount(1);
  await expect(page.locator('[data-node][data-selected="true"]')).toHaveAttribute(
    "data-node",
    "silver_frames",
  );

  const litAncestorKeys = await page
    .locator('[data-node][data-lit="ancestor"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-node")));
  const litDescendantKeys = await page
    .locator('[data-node][data-lit="descendant"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-node")));

  expect(new Set(litAncestorKeys)).toEqual(up);
  expect(new Set(litDescendantKeys)).toEqual(down);

  expect(errors).toEqual([]);
});

test("the per-match table matches platform.json's matches[] cell for cell", async ({ page }) => {
  const platform = (await (await page.request.get("/data/platform.json")).json()) as PlatformJson;

  await page.goto("/engineering");

  const cells = page.locator("td[data-match][data-field]");
  const count = await cells.count();
  expect(count).toBe(platform.matches.length * 9);

  let compared = 0;
  for (let i = 0; i < count; i++) {
    const cell = cells.nth(i);
    const matchId = Number(await cell.getAttribute("data-match"));
    const field = (await cell.getAttribute("data-field")) as keyof PlatformMatch;
    const match = platform.matches.find((m) => m.match_id === matchId);
    expect(match, `no match ${matchId} in platform.json`).toBeTruthy();
    const text = ((await cell.textContent()) ?? "").trim().replace(/,/g, "");
    expect(text, `match ${matchId} ${field}`).toBe(String(match?.[field]));
    compared++;
  }
  console.log(`/engineering: ${compared} per-match cells checked against platform.json`);
  expect(compared).toBe(count);
});

test("raw_bytes in the DOM plus season_files.bytes equals layers.raw.bytes_pinned", async ({
  page,
}) => {
  const platform = (await (await page.request.get("/data/platform.json")).json()) as PlatformJson;
  const bytesPinned = platform.layers.find((l) => l.layer === "raw")?.bytes_pinned;
  expect(bytesPinned).toBeGreaterThan(0);

  await page.goto("/engineering");

  const rawBytesCells = page.locator('td[data-field="raw_bytes"]');
  const count = await rawBytesCells.count();
  expect(count).toBe(platform.matches.length);

  let sum = 0;
  for (let i = 0; i < count; i++) {
    const text = ((await rawBytesCells.nth(i).textContent()) ?? "").replace(/,/g, "");
    sum += Number(text);
  }
  console.log(
    `/engineering: sum(matches raw_bytes)=${sum} + season_files.bytes=${platform.season_files.bytes} = ${sum + platform.season_files.bytes}, layers.raw.bytes_pinned=${bytesPinned}`,
  );
  expect(sum + platform.season_files.bytes).toBe(bytesPinned);
});

test("no horizontal page scroll at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/engineering");
  await page.waitForLoadState("networkidle");

  const overflowing = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflowing).toBe(false);
});

test("the node panel renders code spans without backticks and fits at 390 px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const lineage = (await (await page.request.get("/data/lineage.json")).json()) as LineageJson;
  const withTicks = lineage.nodes.find((n) => n.description.includes("`"))!;
  await page.goto("/engineering");
  await page.locator(`[data-node="${withTicks.key}"]`).focus();
  const panel = page.locator("[data-lineage-detail]");
  await expect(panel).toContainText(withTicks.key);
  expect(await panel.innerText()).not.toContain("`");
  await expect(panel.locator("code")).toHaveCount(1 + (withTicks.description.split("`").length - 1) / 2);
  const [client, scroll] = await panel.evaluate((e) => [e.clientWidth, e.scrollWidth]);
  expect(scroll).toBeLessThanOrEqual(client);
});
