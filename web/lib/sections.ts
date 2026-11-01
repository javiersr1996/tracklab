// The nine sections, in the order the header and the home page list them. `title` is the link text
// the home page has always carried (the e2e find those links by name, so the header uses the short
// `nav` instead), `about` a line from the section's own page or the README, not new copy.
export const SECTIONS = [
  {
    href: "/tracking/replay",
    nav: "Replay",
    title: "Replay any possession",
    about: "Curated possessions that a single Canvas renderer replays in the browser.",
  },
  {
    href: "/engineering",
    nav: "Platform",
    title: "How this was built",
    about:
      "The pipeline as a product: the Dagster asset graph and the layers, raw to publish, with the numbers the latest tracklab build actually produced.",
  },
  {
    href: "/engineering/quality",
    nav: "Quality",
    title: "Data quality",
    about: "A calibration kit for anyone building on the two bundles.",
  },
  {
    href: "/warehouse",
    nav: "Warehouse",
    title: "Warehouse",
    about:
      "SQL over the season aggregates of both bundles, run by DuckDB in this browser on Parquet files that are read by HTTP range.",
  },
  {
    href: "/tracking/runs",
    nav: "Runs",
    title: "The run that moves nobody",
    about: "The project that died, published dead.",
  },
  {
    href: "/tracking/pose",
    nav: "Pose",
    title: "Body pose",
    about: "The joints of the players SkillCorner's Body Pose resolves in each frame, each with its predicted error.",
  },
  {
    href: "/learn",
    nav: "Learn",
    title: "Learn from the data",
    about: "Short lessons that start from a question about the tracking data and end with a query you can run.",
  },
  {
    // Its own section since P12 (until then a second link in the Learn card, task 101).
    href: "/sql",
    nav: "SQL",
    title: "Learn SQL on the warehouse",
    about: "Eight lessons that take you from your first SELECT to window functions and CTEs.",
  },
  {
    // P14: the first data that is not SkillCorner's, aggregates only.
    href: "/euroleague",
    nav: "EuroLeague",
    title: "Where EuroLeague shoots from",
    about: "EuroLeague field goals binned into hexagons on a FIBA half court: the league, each team and its main shooters.",
  },
] as const;

// The header marks a section current on its own page and on every page under it.
export const isCurrent = (path: string, href: string) => path === href || path.startsWith(`${href}/`);

// Where the site is served, so a relative og:image becomes the absolute URL a link preview needs.
export const SITE = "https://tracklab-sable.vercel.app";

// Where the data comes from. SkillCorner's three, as `pipeline/manifest/sources.json` pins them,
// are MIT; EuroLeague's is not under any open license, so the footer gives it its own note and
// the site publishes only aggregates of it (P14).
export const DATA_SOURCES = [
  { name: "SkillCorner/opendata", href: "https://github.com/SkillCorner/opendata", what: "football", license: "MIT" },
  {
    name: "SkillCorner/opendata-basketball",
    href: "https://github.com/SkillCorner/opendata-basketball",
    what: "basketball",
    license: "MIT",
  },
  {
    name: "SkillCorner/opendata-bodypose",
    href: "https://huggingface.co/datasets/SkillCorner/opendata-bodypose",
    what: "body pose",
    license: "MIT",
  },
  {
    name: "EuroLeague",
    href: "https://www.euroleaguebasketball.net/euroleague/",
    what: "basketball shots",
    license: null,
  },
] as const;

// EuroLeague's game feed, the host the aggregates are computed from (league.json's `source`).
export const EUROLEAGUE = DATA_SOURCES.find((s) => s.name === "EuroLeague")!;

// Where a removal request for the EuroLeague aggregates goes (Javier's choice at CP14a, 2026-11-01);
// if it is ever emptied the page says the contact is pending.
export const TAKEDOWN_CONTACT: string = "javiersr1996+tracklab@gmail.com";
