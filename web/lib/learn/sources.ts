// Every outside source a lesson cites: where it was read, when, and the words it is quoted by.
// A lesson cites by id (`<Cite id>`), so a source has one place to be corrected.
export interface Source {
  label: string;
  short?: string; // how the text cites it inline; Further reading shows the label
  url: string;
  read: string; // ISO date the original was read
  quote?: string;
}

// A quote is the source's words as read; text between backticks is code in the original.
export const SOURCES: Readonly<Record<string, Source>> = {
  "cgpm-1901": {
    label: "BIPM, 3rd CGPM (1901), Declaration 2: conventional value of gn",
    short: "CGPM, 1901",
    url: "https://www.bipm.org/en/committees/cg/cgpm/3-1901/resolution-2",
    read: "2026-10-24",
    quote:
      "The value adopted in the International Service of Weights and Measures for the standard acceleration due to gravity is 980.665 cm/s², value already stated in the laws of some countries.",
  },
  "codata-gn": {
    label: "NIST, CODATA 2022 recommended values: standard acceleration of gravity",
    short: "CODATA 2022",
    url: "https://physics.nist.gov/cgi-bin/cuu/Value?gn",
    read: "2026-10-24",
    quote: "Numerical value 9.806 65 m s-2 Standard uncertainty (exact)",
  },
  "nist-linear-ls": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 4.1.4.1 Linear Least Squares Regression",
    short: "NIST handbook, 4.1.4.1",
    url: "https://www.itl.nist.gov/div898/handbook/pmd/section1/pmd141.htm",
    read: "2026-10-24",
    quote: "is linear in the statistical sense",
  },
  "nist-ls": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 4.4.3.1 Least Squares",
    short: "NIST handbook, 4.4.3.1",
    url: "https://www.itl.nist.gov/div898/handbook/pmd/section4/pmd431.htm",
    read: "2026-10-24",
    quote: "For linear models, the least squares minimization is usually done analytically using calculus.",
  },
  "webb-sign-test": {
    label: "Webb, Mostly Harmless Statistics, 13.2 Sign Test (LibreTexts)",
    short: "Webb, 13.2",
    url: "https://stats.libretexts.org/Bookshelves/Introductory_Statistics/Mostly_Harmless_Statistics_(Webb)/13:_Nonparametric_Tests/13.02:_Sign_Test",
    read: "2026-10-24",
    quote: "The sign test uses a Binomial Distribution and looks at the probability of a success as 50%.",
  },
  "skillcorner-tracking": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 42",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L42",
    read: "2026-10-24",
    quote: "`1.0` if the ball is on screen and detected by computer vision, `0.0` if the position is extrapolated.",
  },
};

export function sourceProblems(id: string, s: Source): string[] {
  const problems: string[] = [];
  if (s.label.trim() === "") problems.push(`${id}: no label`);
  if (!/^https:\/\/\S+$/.test(s.url)) problems.push(`${id}: url is not https`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s.read) || Number.isNaN(Date.parse(s.read))) problems.push(`${id}: read is not a date`);
  return problems;
}

export function source(id: string): Source {
  const s = SOURCES[id];
  if (!s) throw new Error(`unknown source "${id}"`);
  return s;
}
