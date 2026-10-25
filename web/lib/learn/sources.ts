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
  // Lesson 7.
  "skillcorner-pass-start": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/passes.md, line 15",
    short: "SkillCorner, passes.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/passes.md#L15",
    read: "2026-10-24",
    quote: "Frame (at 25fps) since the start of the video of the release of the pass.",
  },
  "skillcorner-pass-end": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/passes.md, line 16",
    short: "SkillCorner, passes.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/passes.md#L16",
    read: "2026-10-24",
    quote: "Frame (at 25fps) since the start of the video of the reception of the pass.",
  },
  "skillcorner-pass-passer-loc": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/passes.md, line 33",
    short: "SkillCorner, passes.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/passes.md#L33",
    read: "2026-10-24",
    quote: "x, y coordinate of the passer at the release of the pass.",
  },
  "skillcorner-pass-receiver-loc": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/passes.md, line 34",
    short: "SkillCorner, passes.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/passes.md#L34",
    read: "2026-10-24",
    quote: "x, y coordinate of the receiver at the release of the pass.",
  },
  "skillcorner-pass-distance": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/passes.md, line 37",
    short: "SkillCorner, passes.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/passes.md#L37",
    read: "2026-10-24",
    quote: "Distance in feet between passerLoc and receiverLoc",
  },
  "mathworld-chord": {
    label: "Weisstein, Chord, MathWorld",
    short: "MathWorld, Chord",
    url: "https://mathworld.wolfram.com/Chord.html",
    read: "2026-10-24",
    quote: "In plane geometry, a chord is the line segment joining two points on a curve.",
  },
  "mathworld-arc-length": {
    label: "Weisstein, Arc Length, MathWorld",
    short: "MathWorld, Arc Length",
    url: "https://mathworld.wolfram.com/ArcLength.html",
    read: "2026-10-24",
    quote: "Arc length is defined as the length along a curve",
  },
  // Lesson 8.
  "skillcorner-shot-start": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/shots.md, line 15",
    short: "SkillCorner, shots.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/shots.md#L15",
    read: "2026-10-24",
    quote: "Frame (at 25fps) since the start of video of the release of the shot.",
  },
  "skillcorner-shot-outcome": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/shots.md, line 28",
    short: "SkillCorner, shots.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/shots.md#L28",
    read: "2026-10-24",
    quote: "true if the shot is scored, false if it's missed.",
  },
  "skillcorner-ball-z": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/tracking_data.md, line 40",
    short: "SkillCorner, tracking_data.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/tracking_data.md#L40",
    read: "2026-10-24",
    quote: "z (height) is a real height and can go slightly negative near the floor (calibration noise), not always positive.",
  },
  "fiba-ring": {
    label: "FIBA, Official Basketball Rules 2026, Basketball Equipment, version 1.0 (July 2026), rule 1.2.4, page 9",
    short: "FIBA, Basketball Equipment 2026",
    url: "https://assets.fiba.basketball/image/upload/documents-corporate-fiba-official-rules-2026-equipment-v1-0.pdf#page=9",
    read: "2026-10-24",
    quote: "The top edge of each ring shall be positioned horizontally, 3,050 mm (± a maximum of 6 mm) above the floor",
  },
  "nasa-ballistic": {
    label: "NASA Glenn Research Center, Beginner's Guide to Aeronautics, Ballistic Flight Equations",
    short: "NASA Glenn, Ballistic Flight Equations",
    url: "https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/ballistic-flight-equations/",
    read: "2026-10-24",
    quote: "The horizontal motion is uniform because there is no external force in the horizontal direction.",
  },
  // Lesson 9.
  "skillcorner-dribbles": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/dribbles.md, line 3",
    short: "SkillCorner, dribbles.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/dribbles.md#L3",
    read: "2026-10-24",
    quote: "Individual dribble events, one row per dribble, nested inside a `touches` row.",
  },
  "skillcorner-dribble-frame": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/dribbles.md, line 16",
    short: "SkillCorner, dribbles.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/dribbles.md#L16",
    read: "2026-10-24",
    quote: "Frame (at 25fps) of the dribble",
  },
  "skillcorner-touch": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/touches.md, line 3",
    short: "SkillCorner, touches.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/touches.md#L3",
    read: "2026-10-24",
    quote: "Every continuous ball possession by a single player (from gaining control to losing it)",
  },
  // Lesson 10.
  "skillcorner-possessions": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/possessions.md, line 3",
    short: "SkillCorner, possessions.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/possessions.md#L3",
    read: "2026-10-24",
    quote: "A possession is the full continuous span of team control of the ball, from the moment a team gains it to the moment the other team gains it",
  },
  "skillcorner-possession-start": {
    label: "SkillCorner, opendata-basketball at 4bbed2e, docs/data_dictionary/possessions.md, line 13",
    short: "SkillCorner, possessions.md",
    url: "https://github.com/SkillCorner/opendata-basketball/blob/4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66/docs/data_dictionary/possessions.md#L13",
    read: "2026-10-24",
    quote: "Frame (at 25fps) since the start of the video of the start of the possession.",
  },
  "skillcorner-fb-phases": {
    label: "SkillCorner, opendata at 4340d27, README.md, line 128",
    short: "SkillCorner, opendata README",
    url: "https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md#L128",
    read: "2026-10-24",
    quote: "Each row corresponds to the start and end frames of a given phase",
  },
  "skillcorner-fb-phases-in-play": {
    label: "SkillCorner, opendata at 4340d27, README.md, line 131",
    short: "SkillCorner, opendata README",
    url: "https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md#L131",
    read: "2026-10-24",
    quote: "Phases of play are only defined when the ball is in play. When the ball is out of play there is no phase of play",
  },
  "skillcorner-fb-frame": {
    label: "SkillCorner, opendata at 4340d27, README.md, line 45",
    short: "SkillCorner, opendata README",
    url: "https://github.com/SkillCorner/opendata/blob/4340d274572876239c154c90bc507a9b3250a656/README.md#L45",
    read: "2026-10-24",
    quote: "frame: the frame of the video the data comes from at 10 fps.",
  },
  "nist-survival": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 8.1.2.2 Reliability or survival function",
    short: "NIST handbook, 8.1.2.2",
    url: "https://www.itl.nist.gov/div898/handbook/apr/section1/apr122.htm",
    read: "2026-10-25",
    quote: "the probability a unit survives beyond time",
  },
  "nist-exponential": {
    label: "NIST/SEMATECH e-Handbook of Statistical Methods, 1.3.6.6.7 Exponential Distribution",
    short: "NIST handbook, 1.3.6.6.7",
    url: "https://www.itl.nist.gov/div898/handbook/eda/section3/eda3667.htm",
    read: "2026-10-25",
    quote: "is used to model data with a constant failure rate (indicated by the hazard plot which is simply equal to a constant)",
  },
  // Lesson 11.
  "skillcorner-bodypose-joints": {
    label: "SkillCorner, opendata-bodypose at a62e1ec, README.md, line 87",
    short: "SkillCorner, opendata-bodypose README",
    url: "https://huggingface.co/datasets/SkillCorner/opendata-bodypose/blob/a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a/README.md",
    read: "2026-10-25",
    quote: "`nose`, `neck`, `lEye`, `rEye`, `lEar`, `rEar`, `lShoulder`, `rShoulder`,",
  },
  "skillcorner-bodypose-interpolated": {
    label: "SkillCorner, opendata-bodypose at a62e1ec, README.md, lines 82 and 83",
    short: "SkillCorner, opendata-bodypose README",
    url: "https://huggingface.co/datasets/SkillCorner/opendata-bodypose/blob/a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a/README.md",
    read: "2026-10-25",
    quote: "The 2D `x`/`y` positions in this file are the standard tracking positions interpolated up to 25 fps, not native 25 fps measurements.",
  },
  "skillcorner-bodypose-separate": {
    label: "SkillCorner, opendata-bodypose at a62e1ec, README.md, lines 143 to 145",
    short: "SkillCorner, opendata-bodypose README",
    url: "https://huggingface.co/datasets/SkillCorner/opendata-bodypose/blob/a62e1ec1e3b82952042a7f7fa9dafd77c0e0822a/README.md",
    read: "2026-10-25",
    quote: "XY Tracking data and Body Pose are generated separately. This can cause minor misalignments between the XY attributes (positions, `is_detected` flag) and the Body Pose joints.",
  },
  "scipy-circmean": {
    label: "SciPy 1.14.1 reference, scipy.stats.circmean",
    short: "SciPy, circmean",
    url: "https://docs.scipy.org/doc/scipy-1.14.1/reference/generated/scipy.stats.circmean.html",
    read: "2026-10-25",
    quote: "Compute the circular mean of a sample of angle observations.",
  },
  "scipy-circvar": {
    label: "SciPy 1.14.1 reference, scipy.stats.circvar",
    short: "SciPy, circvar",
    url: "https://docs.scipy.org/doc/scipy-1.14.1/reference/generated/scipy.stats.circvar.html",
    read: "2026-10-25",
    quote: "is known as the mean resultant length",
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
