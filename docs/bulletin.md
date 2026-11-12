# Track Lab data quality bulletin

A calibration kit for anyone building on the two Track Lab bundles, not a verdict on SkillCorner: six checks, each one number (or its range) per match, read straight off `pipeline/reports/quality_*.csv`. `web/public/data/quality.json` carries the same figures for the `/engineering/quality` page, and every number below is one or the other.

## Detection

What it measures: how often the provider marks a tracked object as actually seen (`is_detected`), against extrapolated. Method: share of silver `frames` rows with `is_detected` true, by sport and entity kind.

Basketball ball: `0.0`% across all 10 matches. Basketball player: 76.2 to 82.8%. Football ball: 75.5 to 85.4%. Football player: 49.1 to 65.8%.

For a consumer: `is_detected` is false for the basketball ball in all matches (0.0%), so a pipeline that filters on it for the ball keeps nothing in basketball. Football detection is partial in both entity kinds and should be read per match, not assumed constant.

## Gravity

What it measures: the apparent gravity a ball's own vertical curve implies during free flight. Method: a parabola fit over the samples around each flight's apex (basketball: shots, +-10 frames around it; football: flights found in tracking, windows fully detected and clear of a player touch, +-6 frames around it), g = -2 times the fit's quadratic term.

Basketball calibration (5 matches): median g of 8.08 to 8.36 m/s², 14.7 to 17.6% below the standard 9.80665 m/s². Basketball control (5 matches, scored with thresholds fixed on the calibration matches before this control group was measured): 7.91 to 8.25 m/s², 15.9 to 19.3% below standard, confirming the calibration split rather than a filter tuned to it. Football: the number only, no verdict (its `z_ball_status` is `unverified`): 7.27 to 8.67 m/s², 11.6 to 25.8% away from standard.

For a consumer: any quantity derived from raw z during a basketball flight (release speed, hang time, apex height from timing alone) should expect a systematic low bias of the size above, not a random error. Football carries the same measurement with no calibration reference to grade it against.

## Entry angle

What it measures: a made shot's arrival angle at the rim from the bundle's own z curvature, against the angle true gravity requires given that same flight's horizontal speed and the bundle's own release height. Method: horizontal speed from the first samples after release, flight time from speed and distance to the rim (the only step of the two that does not use z), required vertical speed from projectile motion using the bundle's own release height, both angles compared at the same arrival frame.

Gap (required minus reported), median per match: 12.1 to 16.4 degrees. Share of shot pairs the two angles order differently: 10.5 to 34.7%.

For a consumer: the bundle's own entry angle is not just offset, it reorders shots against a geometry-only measure often enough that ranking shots by it (flat vs steep) will disagree with ranking them by the flight itself.

## Noise

What it measures: frame-to-frame jitter of the ball's horizontal position against a detected player's, while both are moving. Method: the second difference of x, y (a discrete acceleration), pooled per match, ball versus detected players, and their ratio.

Ball-to-player jitter ratio: basketball 3.0 to 5.0×, football 5.1 to 5.7×. Football's ratio is bounded by how its coordinates are stored, not by ball motion: 100.0% of detected players' x, y sit exactly on a 1 cm grid.

For a consumer: smoothing tuned on player tracks (window size, cutoff frequency) will under-smooth the basketball ball by roughly that factor if applied unchanged; the football ratio should not be used the same way, since it is capped by coordinate quantization rather than measuring motion.

## Clock

What it measures: whether the frame clock advances at the sport's declared rate, and, in basketball, whether the declared `speed` field matches a finite difference of consecutive positions. Method: exact-step share between native-frame-adjacent rows; for speed, the median of the per-pair ratio declared-over-measured.

Exact clock step: basketball 100.0%, football 100.0% (football has no independent millisecond field, so its number is contiguity, not a cross-check). Basketball declared speed against measured: 0.15 to 0.18% median mismatch.

For a consumer: the clock step above is a real cross-check in basketball (against `wallClock`) and a contiguity count in football, where no independent field exists to check against. The declared `speed` field and a finite difference of positions differ by the median mismatch above; this bulletin makes no claim about which of the two is correct.

## Partitions

What it measures: four structural splits that run through the matches of one bundle without a single field of either bundle declaring them. None of the four is documented; each is read off an artefact this pipeline already built.

Football tracking layout: 5 of 20 matches carry footage outside their periods well beyond a normal kickoff pause. Basketball frame loss: 5 of 10 matches drop native frames at a rate an order of magnitude above the rest. Football `players[]` shape and event-coordinate precision: 10 of 20 matches on the modified side of each path, and the two paths agree on all 20 of them.

For a consumer: code that assumes one shape across a whole bundle will silently mishandle whichever partition it did not see first; branch on the measured split above, not on a hand-picked list of match ids.

## The hook shot

`/engineering/quality` replays one basketball shot (`bb:114086`, native frame `26867`) chosen by rule: of every accepted calibration flight, the one whose fitted g sits closest to the calibration's own median. Its g is 8.15 m/s² against a calibration median of 8.15 m/s²; the page falls a second ball from the same position and velocity the data's own fit has at that instant, but at 9.80665 m/s², the standard value, so the two are visibly not the same flight.

## On the body pose bundle's own z axis

Body pose is not part of this bulletin, and its z is a different quantity from the one measured above (a joint's position relative to the player's own centroid, not a ball or player position on tracking). Its dataset card documents that axis as a known weak point in that other product; cited here as honest context, not as support for this bulletin's own gravity bias:

> `z` is not a height above the pitch. It is accurate relative to the player's centroid, but not necessarily in the pitch coordinate system, so it can be negative. Treat it as pose geometry rather than elevation. This will improve with future Body Pose enhancements.

Source: [`SkillCorner/opendata-bodypose`](https://huggingface.co/datasets/SkillCorner/opendata-bodypose) dataset card, consulted 2026-09-24.

