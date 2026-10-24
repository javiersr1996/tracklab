// The seven sections, in the order the header and the home page list them. `title` is the link text
// the home page has always carried (the e2e find those links by name, so the header uses the short
// `nav` instead), `about` a line from the section's own page or the README, not new copy.
export const SECTIONS = [
  {
    href: "/replay",
    nav: "Replay",
    title: "Replay any possession",
    about: "Curated possessions that a single Canvas renderer replays in the browser.",
  },
  {
    href: "/platform",
    nav: "Platform",
    title: "How this was built",
    about:
      "The pipeline as a product: the Dagster asset graph and the layers, raw to publish, with the numbers the latest tracklab build actually produced.",
  },
  {
    href: "/quality",
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
    href: "/runs",
    nav: "Runs",
    title: "The run that moves nobody",
    about: "The project that died, published dead.",
  },
  {
    href: "/pose",
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
] as const;

// The header marks a section current on its own page and on every page under it.
export const isCurrent = (path: string, href: string) => path === href || path.startsWith(`${href}/`);

export const REPO = "https://github.com/javiersr1996/tracklab";

// Where the data comes from, as `pipeline/manifest/sources.json` pins it (all three MIT).
export const DATA_SOURCES = [
  { name: "SkillCorner/opendata", href: "https://github.com/SkillCorner/opendata", what: "football" },
  {
    name: "SkillCorner/opendata-basketball",
    href: "https://github.com/SkillCorner/opendata-basketball",
    what: "basketball",
  },
  {
    name: "SkillCorner/opendata-bodypose",
    href: "https://huggingface.co/datasets/SkillCorner/opendata-bodypose",
    what: "body pose",
  },
] as const;
