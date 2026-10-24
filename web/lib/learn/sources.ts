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
  "skillcorner-speed": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 30",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L30",
    read: "2026-10-24",
    quote: "Player speed in feet per second.",
  },
  "dlmf-differentiation": {
    label: "NIST Digital Library of Mathematical Functions, 3.4(i) Differentiation, Equally-Spaced Nodes",
    short: "DLMF, 3.4(i)",
    url: "https://dlmf.nist.gov/3.4.i",
    read: "2026-10-24",
  },
  "scipy-savgol": {
    label: "SciPy 1.14.1 reference, scipy.signal.savgol_filter",
    short: "SciPy, savgol_filter",
    url: "https://docs.scipy.org/doc/scipy-1.14.1/reference/generated/scipy.signal.savgol_filter.html",
    read: "2026-10-24",
    quote: "The order of the polynomial used to fit the samples.",
  },
  "shaw-velocities": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_Velocities.py, line 16",
    short: "Shaw, Metrica_Velocities.py",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_Velocities.py#L16",
    read: "2026-10-24",
    quote: "`def calc_player_velocities(team, smoothing=True, filter_='Savitzky-Golay', window=7, polyorder=1, maxspeed = 12):`",
  },
  "shaw-difference": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_Velocities.py, line 50",
    short: "Shaw, line 50",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_Velocities.py#L50",
    read: "2026-10-24",
    quote: '`vx = team[player+"_x"].diff() / dt`',
  },
  "shaw-maxspeed": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_Velocities.py, line 28",
    short: "Shaw, line 28",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_Velocities.py#L28",
    read: "2026-10-24",
    quote: "the maximum speed that a player can realisitically [sic] achieve (in meters/second)",
  },
  // Lesson 3.
  "skillcorner-bb-coords": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 7",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L7",
    read: "2026-10-24",
    quote: "all `xyz` coordinates are in feet, origin `(0, 0)` at the center of the court.",
  },
  "skillcorner-bb-lefthoop": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/possessions.md, line 30",
    short: "SkillCorner, possessions.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/possessions.md#L30",
    read: "2026-10-24",
    quote: "True if the offensive team is shooting at the left broadcast hoop",
  },
  "skillcorner-fb-coords": {
    label: "SkillCorner, opendata at 4340d27, README.md, line 61",
    short: "SkillCorner, opendata README",
    url: "https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md#L61",
    read: "2026-10-24",
    quote: "For the spatial coordinates, the unit of the field modelization is the meter, the center of the coordinates is at the center of the pitch.",
  },
  "skillcorner-fb-bodypose": {
    label: "SkillCorner, opendata at 4340d27, README.md, line 112",
    short: "SkillCorner, opendata README",
    url: "https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md#L112",
    read: "2026-10-24",
    quote: "The file is at 25 FPS, with the standard 2D XY positions interpolated to fit in the same frame rate.",
  },
  "nist-811-b8": {
    label: "NIST Guide to the SI, Appendix B.8: Factors for Units Listed Alphabetically",
    short: "NIST Guide to the SI, B.8",
    url: "https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b-conversion-factors/nist-guide-si-appendix-b8",
    read: "2026-10-24",
    quote: "Factors in boldface are exact",
  },
  "mathworld-affine": {
    label: "Weisstein, Affine Transformation, MathWorld",
    short: "MathWorld, Affine Transformation",
    url: "https://mathworld.wolfram.com/AffineTransformation.html",
    read: "2026-10-24",
    quote: "An affine transformation is a transformation that preserves affine combinations of points.",
  },
  "mathworld-rotation": {
    label: "Weisstein, Rotation Matrix, MathWorld",
    short: "MathWorld, Rotation Matrix",
    url: "https://mathworld.wolfram.com/RotationMatrix.html",
    read: "2026-10-24",
    quote: "proper (corresponding to pure rotation)",
  },
  // Lesson 4. The conference's own link to Spearman's paper (sloansportsconference.com/wp-content/
  // uploads/2018/02/2002.pdf, the one Shaw's code gives) answered 404 on 2026-10-24; the copy read
  // is the PDF its author uploaded to ResearchGate on 21 Aug 2018, served from a third party's
  // public repository at a fixed commit.
  "spearman-2018": {
    label: "Spearman, Beyond Expected Goals, MIT Sloan Sports Analytics Conference 2018, section 3.1.1, page 6 (the PDF its author uploaded to ResearchGate, 21 Aug 2018, read from a third-party copy in eddwebster/football_analytics at 3df8b32 because the Sloan URL gives 404)",
    short: "Spearman, 2018",
    url: "https://github.com/eddwebster/football_analytics/blob/3df8b32f02f33382004d06bb5c15a2b08d79af0e/research/papers/%5B2018%5D%20Beyond%20Expected%20Goals%20-%20William%20Spearman.pdf#page=7",
    read: "2026-10-24",
    quote: "we choose the logistic over the normal because of its heavier tails",
  },
  "spearman-2018-table": {
    label: "Spearman, Beyond Expected Goals, MIT Sloan Sports Analytics Conference 2018, Table 1, page 10 (same ResearchGate PDF, same third-party copy)",
    short: "Spearman, 2018, Table 1",
    url: "https://github.com/eddwebster/football_analytics/blob/3df8b32f02f33382004d06bb5c15a2b08d79af0e/research/papers/%5B2018%5D%20Beyond%20Expected%20Goals%20-%20William%20Spearman.pdf#page=11",
    read: "2026-10-24",
    quote: "Temporal uncertainty on player-ball intercept time.",
  },
  "shaw-sigma": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_PitchControl.py, line 191",
    short: "Shaw, line 191",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_PitchControl.py#L191",
    read: "2026-10-24",
    quote: "params['tti_sigma'] = 0.45",
  },
  "shaw-tti": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_PitchControl.py, lines 155 to 158",
    short: "Shaw, Metrica_PitchControl.py",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_PitchControl.py#L155-L158",
    read: "2026-10-24",
    quote: "Time to intercept assumes that the player continues moving at current velocity for 'reaction_time' seconds",
  },
  "shaw-reaction": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_PitchControl.py, line 190",
    short: "Shaw, line 190",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_PitchControl.py#L190",
    read: "2026-10-24",
    quote: "`params['reaction_time'] = 0.7 # seconds, time taken for player to react and change trajectory. Roughly determined as vmax/amax`",
  },
  "shaw-top-speed": {
    label: "Shaw, LaurieOnTracking at 7ed3ff8, Metrica_PitchControl.py, line 189",
    short: "Shaw, line 189",
    url: "https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking/blob/7ed3ff857940d3f4611be55f3c08c79525c32171/Metrica_PitchControl.py#L189",
    read: "2026-10-24",
    quote: "`params['max_player_speed'] = 5. # maximum player speed m/s`",
  },
  "skillcorner-rebound-location": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/rebounds.md, line 24",
    short: "SkillCorner, rebounds.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/rebounds.md#L24",
    read: "2026-10-24",
    quote: "x, y coordinate of the rebounder.",
  },
  "skillcorner-shot-end": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/shots.md, line 18",
    short: "SkillCorner, shots.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/shots.md#L18",
    read: "2026-10-24",
    quote: "Frame (at 25fps) since the start of the video of the end of the shot.",
  },
  // Lesson 5.
  "skillcorner-bodypose": {
    label: "SkillCorner, opendata-bodypose at a62e1ec, README.md, lines 94 and 95",
    short: "SkillCorner, opendata-bodypose README",
    url: "https://huggingface.co/datasets/SkillCorner/opendata-bodypose/blob/a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a/README.md",
    read: "2026-10-24",
    quote: "Every joint carries its own accuracy estimate: the 90th-percentile mean absolute error in centimetres.",
  },
  "nist-autocorrelation": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 1.3.3.1 Autocorrelation Plot",
    short: "NIST handbook, 1.3.3.1",
    url: "https://www.itl.nist.gov/div898/handbook/eda/section3/autocopl.htm",
    read: "2026-10-24",
    quote: "If random, such autocorrelations should be near zero for any and all time-lag separations.",
  },
  "smith-parabola": {
    label: "J. O. Smith III, Spectral Audio Signal Processing, Quadratic Interpolation of Spectral Peaks (CCRMA, Stanford)",
    short: "Smith, Quadratic Interpolation of Spectral Peaks",
    url: "https://ccrma.stanford.edu/~jos/sasp/Quadratic_Interpolation_Spectral_Peaks.html",
    read: "2026-10-24",
    quote: "the higher order terms in a Taylor series expansion about the peak converge to zero as the peak is approached",
  },
  "nist-propagation": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 2.5.5 Propagation of error considerations",
    short: "NIST handbook, 2.5.5",
    url: "https://www.itl.nist.gov/div898/handbook/mpc/section5/mpc55.htm",
    read: "2026-10-24",
    quote: "Sometimes the measurement of interest cannot be replicated directly and it is necessary to estimate its uncertainty via propagation of error formulas",
  },
  "jcgm-101": {
    label: "JCGM 101:2008, Supplement 1 to the GUM: Propagation of distributions using a Monte Carlo method (BIPM), Introduction",
    short: "JCGM 101:2008",
    url: "https://www.bipm.org/documents/20126/2071204/JCGM_101_2008_E.pdf",
    read: "2026-10-24",
    quote: "linearization of the model provides an inadequate representation",
  },
  // Lesson 6.
  "skillcorner-wallclock": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 16",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L16",
    read: "2026-10-24",
    quote: "Time in ms since the start of the video.",
  },
  "skillcorner-gameclock": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 17",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L17",
    read: "2026-10-24",
    quote: "Game clock in seconds. 0 means the period is finished.",
  },
  "skillcorner-gameclock-stopped": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 18",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L18",
    read: "2026-10-24",
    quote: "`true` if the game clock is stopped, `false` if the game clock is running.",
  },
  "nist-residuals": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 4.4.4 How can I tell if a model fits my data?",
    short: "NIST handbook, 4.4.4",
    url: "https://www.itl.nist.gov/div898/handbook/pmd/section4/pmd44.htm",
    read: "2026-10-24",
    quote:
      "The residuals from a fitted model are the differences between the responses observed at each combination values of the explanatory variables and the corresponding prediction of the response computed using the regression function.",
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
