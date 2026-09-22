# Basketball bundle format (SkillCorner opendata-basketball)

Tracking section written with task 5 (bronze tracking). Every figure below is read from the bronze Parquet built by `tracklab bronze basketball --tables tracking` and from `pytest -s tests/contracts/test_basketball_tracking_bronze.py`, on the 10 matches of the frozen bundle, on 2026-09-21. The `game_data.json` and `dynamic_events.json` sections land with task 6.

## Read this first

Five things in the tracking mislead without ever raising an error:

1. **`frameIdx` is not the line number.** Breaks (time-outs, quarter ends) remove frames from the file: `max(frameIdx) + 1 - lines` is 3 to 5844 per match. Line N is not frame N, and a frame absent from the file is not the same as a frame delivered empty. Never join tracking against `range()`: bronze keeps `source_row` next to `frameIdx` and fills nothing. [Measured](#frames-full-empty-and-absent).
2. **A frame is full or empty, never partial.** 10 players and the ball, or nothing (`[]`, `[]`, `{}`): 0 partial frames in 1,472,932. Empty frames are 26.1 to 54.6% of the lines depending on the match, so never average coverage across matches. [Measured](#frames-full-empty-and-absent).
3. **The players' `z` is a filler, not a measurement.** 0.0 in all 8,297,040 player observations. Bronze stores it as delivered; silver sends it to NULL. The ball's `z` is a measurement (median 3.48 to 3.63 ft) with 4.5 to 7.7% negative values (minimum -6.42 ft), also stored as delivered. [Measured](#objects).
4. **`isDetected` arrives in two encodings, `shotClock` in three.** Players deliver `isDetected` as int 0/1, the ball as float 0.0/1.0; `shotClock` is null, a float or a whole-second int. Bronze casts them to BOOLEAN and nullable DOUBLE, the only casts it applies. [Cast rules](#casts).
5. **`wallClock == frameIdx * 40` holds in 100% of the frames of the 10 matches** (25 fps, 40 ms). It is the video clock; `gameClock` counts down and is stopped in 49.0 to 65.2% of the frames. [Measured](#clocks).

## Source

- Repository `SkillCorner/opendata-basketball`, ref `main`, **commit `4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66`** (pinned in `pipeline/manifest/sources.json`).
- 35 files: 10 matches x (tracking JSONL gz, game_data.json, dynamic_events.json), 3 season aggregates, `matches.json` and `player_id_aliases.csv`.
- The raw bytes live in an outside clone verified in place (`tracklab ingest opendata-basketball --from-existing`); `data/raw/opendata-basketball/_receipt.json` records where, and bronze reads that path.
- Tracking JSONL gz: 31.7 to 45.6 MB per match, 121,793 to 172,257 lines, one frame per line, 25 fps.

## Tracking JSONL

One JSON object per line with exactly the keys `frameIdx, wallClock, gameClock, gameClockStopped, period, homePlayers, awayPlayers, ball, shotClock`. `homePlayers` and `awayPlayers` are lists of `{xyz, speed, predError, jersey, isDetected, playerId}`; `ball` is `{xyz, speed, isDetected, predError}` or `{}`. `xyz` is a list of three floats in feet, origin at the centre of the court, x along the length (players observed between -59.9 and 60.0 in x and -32.8 and 36.9 in y: they step outside the 94 x 50 ft lines). The ball carries no id. The bronze build imposes this exact key set on every line and object of the 10 matches, so any other shape fails the run instead of being absorbed.

### Clocks

- `wallClock` is milliseconds of video: `wallClock = frameIdx * 40` in 100% of frames in every match (per-match table below).
- `gameClock` is the official clock in seconds, counting down; `gameClockStopped` is true in 49.0 to 65.2% of the frames.
- `shotClock` is null in 52.2 to 66.9% of the frames (every empty frame, plus in-play frames without a live shot clock), otherwise seconds as a float or, for whole seconds, an int.
- `period` runs 1 to 4, 1 to 5 in 178442 (one overtime).

### Frames: full, empty and absent

- A line carries 5 home + 5 away + ball (`full`) or `[]`, `[]`, `{}` (`empty`); `partial` is 0 in every match.
- `absent` is `max(frameIdx) + 1 - lines`: frames the provider never delivered. 3 to 5844 per match, 22 or less in 5 matches, thousands in the other 5. It is reported as a number, never as a boolean, and never filled.

| match_id | lines | full | empty | partial | absent | wallClock rule |
|---|---|---|---|---|---|---|
| 114086 | 124796 | 92188 | 32608 | 0 | 1760 | 100.00% |
| 114099 | 147892 | 75655 | 72237 | 0 | 3272 | 100.00% |
| 114169 | 172257 | 106176 | 66081 | 0 | 5844 | 100.00% |
| 114234 | 158923 | 72132 | 86791 | 0 | 2651 | 100.00% |
| 114243 | 146870 | 77023 | 69847 | 0 | 2668 | 100.00% |
| 178442 | 162479 | 89642 | 72837 | 0 | 22 | 100.00% |
| 179612 | 140856 | 83437 | 57419 | 0 | 18 | 100.00% |
| 184439 | 154021 | 77428 | 76593 | 0 | 93 | 100.00% |
| 188630 | 121793 | 73138 | 48655 | 0 | 3 | 100.00% |
| 191313 | 143045 | 82885 | 60160 | 0 | 11 | 100.00% |

Total: 1,472,932 lines, 829,704 full, 643,228 empty.

### Objects

| match_id | player obs | player z != 0 | ball z median | ball z min | ball z < 0 | predError < 0 | isDetected |
|---|---|---|---|---|---|---|---|
| 114086 | 921880 | 0 | 3.52 | -5.42 | 7.4% | 18994 | 73.3% |
| 114099 | 756550 | 0 | 3.58 | -4.99 | 5.3% | 10462 | 74.3% |
| 114169 | 1061760 | 0 | 3.59 | -4.81 | 7.6% | 17068 | 69.2% |
| 114234 | 721320 | 0 | 3.48 | -6.42 | 4.5% | 10176 | 75.2% |
| 114243 | 770230 | 0 | 3.52 | -5.97 | 4.5% | 9537 | 75.1% |
| 178442 | 896420 | 0 | 3.57 | -5.29 | 7.3% | 12713 | 73.0% |
| 179612 | 834370 | 0 | 3.63 | -4.94 | 5.7% | 12549 | 71.7% |
| 184439 | 774280 | 0 | 3.55 | -5.70 | 6.6% | 12947 | 74.1% |
| 188630 | 731380 | 0 | 3.48 | -5.65 | 5.5% | 9308 | 73.3% |
| 191313 | 828850 | 0 | 3.53 | -5.68 | 7.7% | 13300 | 72.1% |

`predError` is negative in 9,308 to 18,994 observations per match; bronze keeps the value. `isDetected` (players and ball together) is true in 69.2 to 75.2% of the objects; the rest are extrapolated positions.

## Bronze tables

Built by `tracklab bronze basketball --tables tracking`; 81.9 s for the 10 matches on this machine, 309 MB of Parquet.

### Layout and lineage, shared by every bronze table

- One file per match and table: `data/bronze/<sport>/<table>/<match_id>.parquet`. `match_id` is also a column of every row, so the path is never load-bearing and `read_parquet('.../<table>/*.parquet')` reads the sport with plain column filters (one match per file, so row-group statistics prune files).
- Every table starts with `sport VARCHAR`, `match_id BIGINT`, `source_file VARCHAR` (bundle-relative path of the raw file) and `source_row BIGINT` (0-based position of the record in that file: line of a JSONL, index in a JSON array, data row of a CSV). In tracking, `source_row != frameIdx` after the first break.
- Parquet key-value metadata carries `tracklab.source_file`, `tracklab.source_sha256` (the manifest's) and `tracklab.source_commit`.
- ZSTD, 100k-row row groups, atomic write (temp file then rename), schema declared in `pipeline/src/tracklab/bronze/basketball/tracking.py` and imposed: a key too many or too few, a value that does not cast, a null in a NOT NULL column, fail the run with the column's name and the line.

### tracking_frames (one row per line of the file)

| column | type | from |
|---|---|---|
| sport, match_id, source_file, source_row | lineage | |
| frameIdx | BIGINT NOT NULL | `frameIdx` |
| wallClock | BIGINT NOT NULL | `wallClock` (ms) |
| gameClock | DOUBLE NOT NULL | `gameClock` (s, counts down) |
| gameClockStopped | BOOLEAN NOT NULL | `gameClockStopped` |
| period | SMALLINT NOT NULL | `period` |
| shotClock | DOUBLE | `shotClock` (null, float or int) |
| n_home | SMALLINT NOT NULL | `len(homePlayers)` |
| n_away | SMALLINT NOT NULL | `len(awayPlayers)` |
| has_ball | BOOLEAN NOT NULL | `ball != {}` |

### tracking_objects (one row per player or ball entry)

| column | type | from |
|---|---|---|
| sport, match_id, source_file, source_row | lineage | `source_row` is the line of the frame |
| frameIdx | BIGINT NOT NULL | the frame's `frameIdx` |
| side | VARCHAR NOT NULL | `'home'`, `'away'` or `'ball'` |
| playerId | BIGINT | `playerId`; NULL for the ball |
| jersey | VARCHAR | `jersey`; NULL for the ball |
| x, y, z | DOUBLE NOT NULL | `xyz[0..2]`, feet, as delivered |
| speed | DOUBLE NOT NULL | `speed` |
| isDetected | BOOLEAN NOT NULL | `isDetected` (int for players, float for the ball) |
| predError | DOUBLE NOT NULL | `predError`, as delivered (negatives included) |

### Casts

The only transformations bronze applies, each declared in the schema:

- `xyz` (list of 3) becomes `x`, `y`, `z`: per-axis statistics and pushdown, silver reads without unnesting, and football delivers x and y as separate keys, so the two sports share one shape.
- `isDetected` int 0/1 (players) and float 0.0/1.0 (ball) become BOOLEAN. The cast accepts exactly 0 and 1 and fails on anything else: a 0.5 would be a change of meaning, not of encoding.
- `shotClock` null / float / int becomes nullable DOUBLE; int to double is exact.
- Nothing else. `z = 0.0` for players, negative `predError`, negative ball `z` are stored as they come; silver owns every correction (players' z to NULL, the ball's z labelled `biased`).

### Empty frames and absent frames

- An empty line (no players, `ball: {}`) is a row of `tracking_frames` with `n_home = n_away = 0`, `has_ball = false`, `shotClock` null, and no row in `tracking_objects`. The timeline the provider delivered lives complete in bronze; silver's `frames` drops them.
- A frame absent from the file stays absent. Bronze never generates the grid with `range()` and never interpolates: that would fabricate frames the provider never delivered. The `absent` column of the table above is the size of that hole per match.

### What the contract test asserts (`tests/contracts/test_basketball_tracking_bronze.py`)

- The schema of every file equals the declared one, both tables, 10 matches.
- `wallClock == frameIdx * 40` in 100% of the rows of every match, percentage printed per match.
- `partial` frames are 0 in every match; `absent` is printed per match as a number.
- For 114243, a gzip + json walk of the raw file with no pyarrow and no tracklab code counts 146,870 lines and 847,253 objects (`len(homePlayers) + len(awayPlayers) + (1 if ball)`), equal to the rows of `tracking_frames` and `tracking_objects` read back with DuckDB.

<!-- tracklab:freeze-schema-basketball:generated-below -->

Generated by `tracklab freeze-schema basketball` (task 6), on the same 10 matches and commit `4bbed2e35e8fdd2cf083e8c8b280b3e5381a2c66` as the tracking section above (tracking itself is documented separately, in `tasks/todo.md` task 5, not repeated here). The per-match rows live in `pipeline/reports/basketball_format.csv`; the family and aggregate tables are rendered from the frozen `*.schema.json` files under `pipeline/src/tracklab/bronze/schemas/basketball/`. 10 matches x (`dynamic_events.json`, `game_data.json`), 3 season aggregates, `matches.json` and `player_id_aliases.csv`.

## Event families

One Parquet per match and family (`events_<family>`), columns `sport, match_id, source_file, source_row` (see `bronze.common.LINEAGE_FIELDS`) plus the family's own columns in provider order. `n_keys` is fixed across the bundle: the freezer fails loudly the moment a match disagrees.

| family | n_keys | 114086 | 114099 | 114169 | 114234 | 114243 | 178442 | 179612 | 184439 | 188630 | 191313 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| chances | 30 | 195 | 208 | 214 | 209 | 216 | 221 | 201 | 204 | 182 | 205 |
| possessions | 22 | 151 | 157 | 152 | 166 | 157 | 173 | 153 | 159 | 143 | 153 |
| shots | 40 | 139 | 150 | 148 | 144 | 159 | 158 | 145 | 142 | 133 | 141 |
| rebounds | 19 | 63 | 87 | 87 | 77 | 95 | 77 | 72 | 69 | 66 | 75 |
| turnovers | 18 | 30 | 26 | 16 | 37 | 25 | 25 | 22 | 24 | 19 | 24 |
| free_throws | 15 | 32 | 27 | 44 | 55 | 36 | 44 | 44 | 58 | 42 | 48 |
| fouls | 24 | 37 | 39 | 49 | 47 | 40 | 42 | 46 | 54 | 40 | 49 |
| timeouts | 10 | 5 | 5 | 7 | 10 | 5 | 10 | 4 | 7 | 5 | 7 |
| passes | 30 | 510 | 469 | 460 | 461 | 525 | 475 | 533 | 448 | 472 | 433 |
| touches | 27 | 690 | 652 | 653 | 655 | 728 | 682 | 714 | 635 | 635 | 618 |
| dribbles | 15 | 1336 | 1347 | 1491 | 1483 | 1234 | 1467 | 1337 | 1462 | 1452 | 1353 |
| picks | 26 | 145 | 139 | 175 | 142 | 135 | 165 | 153 | 177 | 141 | 148 |
| isolations | 23 | 19 | 20 | 29 | 15 | 11 | 12 | 21 | 7 | 22 | 24 |
| handoffs | 25 | 49 | 26 | 38 | 46 | 56 | 44 | 47 | 45 | 37 | 29 |
| drives | 28 | 84 | 50 | 65 | 70 | 58 | 81 | 65 | 67 | 62 | 58 |
| posts | 25 | 12 | 9 | 9 | 5 | 15 | 12 | 7 | 8 | 24 | 4 |
| off_ball_screens | 27 | 115 | 100 | 99 | 104 | 136 | 122 | 101 | 127 | 112 | 87 |
| closeouts | 31 | 66 | 76 | 43 | 56 | 58 | 68 | 71 | 46 | 53 | 64 |
| chance_players | 14 | 1950 | 2080 | 2140 | 2090 | 2160 | 2200 | 2010 | 2040 | 1820 | 2050 |
| matchups | 15 | 1347 | 1507 | 1448 | 1547 | 1497 | 1529 | 1429 | 1366 | 1269 | 1477 |

## Family columns

### chances

`events_chances`, 30 keys, 2055 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| period | BIGINT | False | - |
| startFrame | BIGINT | False | - |
| endFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| startGameClock | DOUBLE | True | - |
| endGameClock | DOUBLE | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| startType | VARCHAR | False | - |
| outcome | VARCHAR | False | - |
| offPlayerIds | LIST<BIGINT> | False | - |
| defPlayerIds | LIST<BIGINT> | False | - |
| homeStartScore | BIGINT | False | - |
| awayStartScore | BIGINT | False | - |
| ptsScored | BIGINT | False | - |
| startShotClock | DOUBLE | True | - |
| endShotClock | DOUBLE | True | - |
| ballInPaint | BOOLEAN | False | - |
| endOfPossession | BOOLEAN | False | - |
| endLoc | POINT2D | True | - |
| frontcourtFrame | BIGINT | True | - |
| transition | BOOLEAN | False | - |
| lastChanceId | VARCHAR | True | - |
| qualityIndex | BIGINT | False | - |
| usable | BOOLEAN | False | - |

### possessions

`events_possessions`, 22 keys, 1564 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| period | BIGINT | False | - |
| startFrame | BIGINT | False | - |
| endFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| startGameClock | DOUBLE | True | - |
| endGameClock | DOUBLE | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| startType | VARCHAR | False | - |
| outcome | VARCHAR | False | - |
| offPlayerIds | LIST<BIGINT> | False | - |
| defPlayerIds | LIST<BIGINT> | False | - |
| homeStartScore | BIGINT | False | - |
| awayStartScore | BIGINT | False | - |
| ptsScored | BIGINT | False | - |
| ballInPaint | BOOLEAN | False | - |
| endLoc | POINT2D | True | - |
| leftHoop | BOOLEAN | False | - |

### shots

`events_shots`, 40 keys, 1459 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| period | BIGINT | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| startFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| startGameClock | DOUBLE | False | - |
| endFrame | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| endGameClock | DOUBLE | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| shotClock | DOUBLE | True | - |
| shooterId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| three | BOOLEAN | False | - |
| outcome | BOOLEAN | False | - |
| fouled | BOOLEAN | False | - |
| foulId | VARCHAR | True | - |
| assisted | BOOLEAN | False | - |
| assistOpp | BOOLEAN | False | - |
| passerId | BIGINT | True | - |
| blocked | BOOLEAN | False | - |
| blockerId | BIGINT | True | - |
| distance | DOUBLE | True | - |
| dribblesBefore | BIGINT | True | - |
| shotType | VARCHAR | True | - |
| complexShotType | VARCHAR | True | - |
| catchAndShoot | BOOLEAN | True | - |
| shotQuality | DOUBLE | True | - |
| createdFromPaint | BOOLEAN | False | - |
| contested | BOOLEAN | True | - |
| contestLevel | VARCHAR | True | - |
| releaseTime | DOUBLE | True | - |
| closestDefDist | DOUBLE | True | - |
| closestDefId | BIGINT | True | - |
| touchId | VARCHAR | True | - |

### rebounds

`events_rebounds`, 19 keys, 768 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| shotId | VARCHAR | True | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| teamId | BIGINT | False | - |
| rebounderId | BIGINT | True | - |
| fgReb | BOOLEAN | False | - |
| rebounded | BOOLEAN | False | - |
| defensive | BOOLEAN | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| nextChanceId | VARCHAR | False | - |
| touchId | VARCHAR | True | - |

### turnovers

`events_turnovers`, 18 keys, 248 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| period | BIGINT | False | - |
| possessionId | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| turnedOverId | BIGINT | True | - |
| stealerId | BIGINT | True | - |
| teamId | BIGINT | False | - |
| teamTo | BOOLEAN | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| touchId | VARCHAR | True | - |

### free_throws

`events_free_throws`, 15 keys, 430 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| shooterId | BIGINT | False | - |
| outcome | BOOLEAN | False | - |
| foulId | VARCHAR | True | - |
| shotId | VARCHAR | True | - |

### fouls

`events_fouls`, 24 keys, 443 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| foulerId | BIGINT | False | - |
| fouledId | BIGINT | False | - |
| foulerTeamId | BIGINT | False | - |
| fouledTeamId | BIGINT | False | - |
| shooting | BOOLEAN | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| foulType | VARCHAR | False | - |
| isBonus | BOOLEAN | False | - |
| isTeam | BOOLEAN | False | - |
| isTechnical | BOOLEAN | False | - |
| touchId | VARCHAR | True | - |
| shotId | VARCHAR | True | - |

### timeouts

`events_timeouts`, 10 keys, 65 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| teamId | BIGINT | True | - |

### passes

`events_passes`, 30 keys, 4786 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| period | BIGINT | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| startFrame | BIGINT | False | - |
| endFrame | BIGINT | True | - |
| startWallClock | BIGINT | False | - |
| endWallClock | BIGINT | True | - |
| startGameClock | DOUBLE | False | - |
| endGameClock | DOUBLE | True | - |
| shotClock | DOUBLE | True | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| passerId | BIGINT | False | - |
| receiverId | BIGINT | True | - |
| toReceiverId | BIGINT | True | - |
| complete | BOOLEAN | True | - |
| turnover | BOOLEAN | False | - |
| ledToShot | BOOLEAN | False | - |
| assistOpp | BOOLEAN | False | - |
| inbounds | BOOLEAN | True | - |
| backcourt | BOOLEAN | False | - |
| passerLoc | POINT2D | True | - |
| receiverLoc | POINT2D | True | - |
| passerRegion | VARCHAR | True | - |
| receiverRegion | VARCHAR | True | - |
| distance | DOUBLE | True | - |
| touchId | VARCHAR | True | - |

### touches

`events_touches`, 27 keys, 6662 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| period | BIGINT | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| startFrame | BIGINT | False | - |
| endFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| startGameClock | DOUBLE | False | - |
| endGameClock | DOUBLE | False | - |
| shotClock | DOUBLE | True | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| playerId | BIGINT | False | - |
| defenderId | BIGINT | True | - |
| closestDefLoc | POINT2D | True | - |
| location | POINT2D | True | - |
| endLoc | POINT2D | True | - |
| numDribbles | BIGINT | False | - |
| ledToShot | BOOLEAN | False | - |
| touchTime | DOUBLE | False | - |
| outcomes | LIST<VARCHAR> | False | - |
| regionsIn | LIST<VARCHAR> | False | - |
| endClosestDefLoc | POINT2D | True | - |
| direct | BOOLEAN | False | - |

### dribbles

`events_dribbles`, 15 keys, 13962 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| ballhandlerId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| touchId | VARCHAR | True | - |

### picks

`events_picks`, 26 keys, 1520 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | False | - |
| region | VARCHAR | False | - |
| shotClock | DOUBLE | True | - |
| ballhandlerId | BIGINT | False | - |
| screenerId | BIGINT | False | - |
| ballhandlerDefId | BIGINT | False | - |
| screenerDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| locationType | VARCHAR | False | - |
| bhrDefType | VARCHAR | False | - |
| scrDefType | VARCHAR | False | - |
| bhrOutcomes | LIST<VARCHAR> | False | - |
| scrOutcomes | LIST<VARCHAR> | False | - |
| handoffPick | BOOLEAN | False | - |
| touchId | VARCHAR | True | - |

### isolations

`events_isolations`, 23 keys, 180 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| startGameClock | DOUBLE | False | - |
| startFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endGameClock | DOUBLE | False | - |
| endFrame | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | False | - |
| region | VARCHAR | False | - |
| endLoc | POINT2D | False | - |
| shotClock | DOUBLE | True | - |
| ballhandlerId | BIGINT | False | - |
| ballhandlerDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| bhrOutcomes | LIST<VARCHAR> | False | - |
| touchId | VARCHAR | False | - |

### handoffs

`events_handoffs`, 25 keys, 417 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | False | - |
| region | VARCHAR | False | - |
| shotClock | DOUBLE | False | - |
| setterId | BIGINT | False | - |
| receiverId | BIGINT | False | - |
| setterDefId | BIGINT | False | - |
| receiverDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| locationType | VARCHAR | False | - |
| receiverDefType | VARCHAR | False | - |
| setterDefType | VARCHAR | False | - |
| bhrOutcomes | LIST<VARCHAR> | False | - |
| handoffPick | BOOLEAN | False | - |
| touchId | VARCHAR | True | - |

### drives

`events_drives`, 28 keys, 660 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| startGameClock | DOUBLE | False | - |
| startFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endGameClock | DOUBLE | False | - |
| endFrame | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| endLoc | POINT2D | False | - |
| shotClock | DOUBLE | True | - |
| ballhandlerId | BIGINT | False | - |
| ballhandlerDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| category | VARCHAR | False | - |
| blowby | BOOLEAN | False | - |
| endType | VARCHAR | False | - |
| direction | VARCHAR | False | - |
| bhrOutcomes | LIST<VARCHAR> | False | - |
| dribbleThrough | BOOLEAN | False | - |
| touchId | VARCHAR | False | - |

### posts

`events_posts`, 25 keys, 105 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| startGameClock | DOUBLE | False | - |
| startFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endGameClock | DOUBLE | False | - |
| endFrame | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | False | - |
| region | VARCHAR | False | - |
| endLoc | POINT2D | False | - |
| shotClock | DOUBLE | False | - |
| ballhandlerId | BIGINT | False | - |
| ballhandlerDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| bhrOutcomes | LIST<VARCHAR> | False | - |
| section | VARCHAR | True | - |
| dribbledInto | BOOLEAN | False | - |
| touchId | VARCHAR | False | - |

### off_ball_screens

`events_off_ball_screens`, 27 keys, 1103 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| gameClock | DOUBLE | False | - |
| frame | BIGINT | False | - |
| wallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | False | - |
| region | VARCHAR | False | - |
| shotClock | DOUBLE | True | - |
| cutterId | BIGINT | False | - |
| screenerId | BIGINT | False | - |
| cutterDefId | BIGINT | False | - |
| screenerDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| cutterDefType | VARCHAR | False | - |
| screenerDefType | VARCHAR | False | - |
| outcomes | LIST<VARCHAR> | False | - |
| ledToTouch | BOOLEAN | False | - |
| ledToShot | BOOLEAN | False | - |
| scrOutcomes | LIST<VARCHAR> | False | - |
| touchId | VARCHAR | True | - |
| scrTouchId | VARCHAR | True | - |

### closeouts

`events_closeouts`, 31 keys, 601 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| touchGameClock | DOUBLE | True | - |
| touchFrame | BIGINT | True | - |
| touchWallClock | BIGINT | True | VARCHAR |
| startGameClock | DOUBLE | False | - |
| startFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endGameClock | DOUBLE | False | - |
| endFrame | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| direct | BOOLEAN | False | - |
| location | POINT2D | True | - |
| region | VARCHAR | True | - |
| startLoc | POINT2D | True | - |
| endLoc | POINT2D | True | - |
| touchLoc | POINT2D | True | - |
| startDistance | DOUBLE | True | - |
| touchDistance | DOUBLE | True | - |
| endDistance | DOUBLE | True | - |
| ballhandlerId | BIGINT | True | - |
| ballhandlerDefId | BIGINT | False | - |
| offTeamId | BIGINT | False | - |
| defTeamId | BIGINT | False | - |
| bhrOutcomes | LIST<VARCHAR> | False | - |
| bhrAction | VARCHAR | True | - |
| touchId | VARCHAR | True | - |

### chance_players

`events_chance_players`, 14 keys, 20540 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| playerId | BIGINT | False | - |
| offense | BOOLEAN | False | - |
| startMatchupId | BIGINT | True | - |
| endMatchupId | BIGINT | True | - |
| shotLoc | POINT2D | True | - |
| rimLoc | POINT2D | True | - |
| reboundLoc | POINT2D | True | - |
| minutesPlayedBefore | DOUBLE | False | - |

### matchups

`events_matchups`, 15 keys, 14416 rows read.

| key | type | nullable | source_type |
|---|---|---|---|
| id | VARCHAR | False | - |
| gameId | BIGINT | False | - |
| season | VARCHAR | False | - |
| chanceId | VARCHAR | False | - |
| possessionId | VARCHAR | False | - |
| period | BIGINT | False | - |
| startGameClock | DOUBLE | False | - |
| startFrame | BIGINT | False | - |
| startWallClock | BIGINT | False | - |
| endGameClock | DOUBLE | False | - |
| endFrame | BIGINT | False | - |
| endWallClock | BIGINT | False | - |
| shotClock | DOUBLE | True | - |
| defPlayerId | BIGINT | False | - |
| offPlayerId | BIGINT | False | - |

## Declared casts

- `closeouts.touchWallClock`: source `VARCHAR` -> stored `BIGINT`.

## game_data.json

12 header keys per match: `gameId, date, competitionEditionId, competitionId, competitionName, seasonId, seasonName, dynamicEventsLastProcessingDate, trackingLastProcessingDate, physicalLastProcessingDate` plus `homeTeam` and `awayTeam`, each `{teamId, teamName, players[]}`. Every player carries `{playerId, firstName, lastName, jersey}`, `jersey` delivered as a string in every roster of the bundle. Roster size per match: home 11-12, away 10-12 (`n_home_players`/`n_away_players` in the report).

## matches.json

A list of 10 matches. Every match shares the same 12 keys: `away_score, away_team, competition_edition_id, competition_id, competition_name, date_time, home_score, home_team, id, season, season_id, status`. `home_team`/`away_team` are each `{id, name}`. Bronze flattens them to `home_team_id, home_team_name, away_team_id, away_team_name` and keeps every other key as delivered.

## player_id_aliases.csv

18 data rows, columns `player_id, player_name, canonical_player_id, canonical_player_name, acb_player_id`. Maps a provider `player_id` that changed between seasons (a name typo, a mid-season correction) to a `canonical_player_id` and to the ACB's own id.

## Aggregates

Season grain (player x team x season for `shots`/`drives`, per the CSV's own key for `picks`), no `match_id`: `SEASON_LINEAGE_FIELDS` (`sport, source_file, source_row`).

| table | n_columns | header_sha256 |
|---|---|---|
| aggregates_drives | 71 | a78b84b754ea |
| aggregates_picks | 684 | bbaeae88e085 |
| aggregates_shots | 308 | bf17310b28fd |
