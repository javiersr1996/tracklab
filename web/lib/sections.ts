// The nine sections, in the order the home page lists them. `title` is the link text the home page
// has always carried (the e2e find those links by name), `about` a line from the section's own page
// or the README, not new copy.
export const SECTIONS = [
  {
    href: "/tracking/replay",
    title: "Replay any possession",
    about: "Curated possessions that a single Canvas renderer replays in the browser.",
  },
  {
    href: "/engineering",
    title: "How this was built",
    about:
      "The pipeline as a product: the Dagster asset graph and the layers, raw to publish, with the numbers the latest tracklab build actually produced.",
  },
  {
    href: "/engineering/quality",
    title: "Data quality",
    about: "A calibration kit for anyone building on the two bundles.",
  },
  {
    href: "/warehouse",
    title: "Warehouse",
    about:
      "SQL over the season aggregates of both bundles, run by DuckDB in this browser on Parquet files that are read by HTTP range.",
  },
  {
    href: "/tracking/runs",
    title: "The run that moves nobody",
    about: "The project that died, published dead.",
  },
  {
    href: "/tracking/pose",
    title: "Body pose",
    about: "The joints of the players SkillCorner's Body Pose resolves in each frame, each with its predicted error.",
  },
  {
    href: "/learn",
    title: "Learn from the data",
    about: "Short lessons that start from a question about the tracking data and end with a query you can run.",
  },
  {
    // Its own section since P12 (until then a second link in the Learn card, task 101).
    href: "/sql",
    title: "Learn SQL on the warehouse",
    about: "Eight lessons that take you from your first SELECT to window functions and CTEs.",
  },
  {
    // P14: the first data that is not SkillCorner's, aggregates only.
    href: "/euroleague",
    title: "Where EuroLeague shoots from",
    about: "EuroLeague field goals binned into hexagons on a FIBA half court: the league, each team and its main shooters.",
  },
] as const;

// The header's six entries (P15, task 121, Javier's option 1 of 2026-11-01), and About (P20). Tracking,
// Engineering and Warehouse (P17) group pages, which a second row of the header lists on any page
// under them.
export type NavEntry = { href: string; nav: string; pages?: { href: string; nav: string }[] };
export const NAV: NavEntry[] = [
  {
    href: "/tracking",
    nav: "Tracking",
    pages: [
      { href: "/tracking/replay", nav: "Replay" },
      { href: "/tracking/runs", nav: "Runs" },
      { href: "/tracking/pose", nav: "Pose" },
    ],
  },
  {
    href: "/engineering",
    nav: "Engineering",
    pages: [
      { href: "/engineering", nav: "Platform" },
      { href: "/engineering/quality", nav: "Quality" },
      { href: "/engineering/bulletin", nav: "Bulletin" },
      { href: "/engineering/history", nav: "History" },
    ],
  },
  {
    href: "/warehouse",
    nav: "Warehouse",
    pages: [
      { href: "/warehouse", nav: "Console" },
      { href: "/warehouse/scouting", nav: "Scouting" },
    ],
  },
  { href: "/learn", nav: "Learn" },
  { href: "/sql", nav: "SQL" },
  { href: "/euroleague", nav: "EuroLeague" },
  // P20, task 171: who made the site, not a section of it.
  { href: "/about", nav: "About" },
];

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

// Who made the site and where the code is (P20, task 171): the footer, the home's byline and
// /about read these.
export const AUTHOR = {
  name: "Javier Sánchez Rueda",
  linkedin: "https://www.linkedin.com/in/javier-sanchez-rueda/",
  email: "javiersr1996@gmail.com",
} as const;
export const REPO = "https://github.com/javiersr1996/tracklab";
