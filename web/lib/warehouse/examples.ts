// The example queries of /warehouse and what `warehouse_examples.json` (`tracklab publish
// examples`) says each must return. The players, the minimum matches and games, and the metric
// come from that file, so the SQL and the expected answers cannot drift apart.
import examplesJson from "../../public/data/warehouse_examples.json";

export interface ExpectedColumn {
  name: string;
  // Digits the query rounds to (`round(x, decimals)`), or null for text and whole numbers.
  decimals: number | null;
}

export interface ExpectedExample {
  id: string;
  table: string;
  columns: ExpectedColumn[];
  rows: (string | number)[][];
}

export interface BasketballPercentileAliases {
  pool_rows_naive: number;
  pool_rows_merged: number;
  percentile_naive: number;
  percentile_merged: number;
}

export interface ExamplesFile {
  schema_version: number;
  params: {
    min_matches: number;
    min_games: number;
    football_metric: string;
    profile_player: string;
    football_player: string;
    basketball_player: string;
  };
  examples: ExpectedExample[];
  aliases: {
    alias_ids: number;
    bb_shots_alias_rows_in_a_team_with_their_canonical_id: number;
    profile_player_has_an_alias: boolean;
    basketball_percentile: BasketballPercentileAliases;
  };
}

export const EXAMPLES_FILE = examplesJson as ExamplesFile;

const { params } = EXAMPLES_FILE;

export interface Example {
  id: string;
  label: string;
  about: string;
  sql: string;
}

export const EXAMPLES: Example[] = [
  {
    id: "profile",
    label: "Player profile",
    about: "One basketball player's season line, from the team rows (never the traded players' total row).",
    sql: `SELECT player_name, team_name, games_played, attempts, mades,
       three_attempts, three_mades, total_points,
       round(total_points * 1.0 / games_played, 1) AS points_per_game
FROM bb_shots
WHERE player_name = '${params.profile_player}' AND NOT is_season_total`,
  },
  {
    id: "percentile",
    label: "Percentile in position",
    about: `Top speed (${params.football_metric}) of a football player against the others in his position group with at least ${params.min_matches} matches, with that group's players and matches.`,
    sql: `WITH pool AS (
  SELECT player_name, team_name, position_group, ${params.football_metric},
         percent_rank() OVER (PARTITION BY position_group ORDER BY ${params.football_metric}) AS pct,
         count(*) OVER (PARTITION BY position_group) AS players_in_group,
         sum(count_match) OVER (PARTITION BY position_group)::INTEGER AS matches_in_group
  FROM fb_physical
  WHERE ${params.football_metric} IS NOT NULL AND count_match >= ${params.min_matches}
)
SELECT player_name, team_name, position_group, ${params.football_metric},
       round(pct * 100, 1) AS percentile, players_in_group, matches_in_group
FROM pool
WHERE player_name = '${params.football_player}'`,
  },
  {
    id: "teams",
    label: "Teams side by side",
    about: "Basketball teams from their players' counts: sums over team rows, which add up; the total rows are left out.",
    sql: `SELECT team_name, sum(attempts)::INTEGER AS attempts, sum(mades)::INTEGER AS mades,
       round(100.0 * sum(mades) / sum(attempts), 1) AS fg_pct,
       sum(total_points)::INTEGER AS points
FROM bb_shots
WHERE NOT is_season_total
GROUP BY team_name
ORDER BY points DESC, team_name`,
  },
  {
    id: "basketball_percentile",
    label: "Basketball percentile",
    about: `Three-point attempts per game of a basketball player against the players with at least ${params.min_games} games. The alias ids below move it.`,
    sql: `WITH pool AS (
  SELECT player_name, team_name, games_played, three_attempts,
         three_attempts * 1.0 / games_played AS threes_per_game,
         percent_rank() OVER (ORDER BY three_attempts * 1.0 / games_played) AS pct,
         count(*) OVER () AS players_in_pool,
         sum(games_played) OVER ()::INTEGER AS games_in_pool
  FROM bb_shots
  WHERE NOT is_season_total AND games_played >= ${params.min_games}
)
SELECT player_name, team_name, games_played, three_attempts,
       round(threes_per_game, 2) AS threes_per_game, round(pct * 100, 1) AS percentile,
       players_in_pool, games_in_pool
FROM pool
WHERE player_name = '${params.basketball_player}'`,
  },
  {
    id: "fact",
    label: "Quantiles of one metric",
    about: `Median and 90th percentile of one metric over the long table, which is sorted by metric and cut into row groups: compare the row groups with fetched bytes to the total in the panel.`,
    sql: `SELECT round(quantile_cont(value, 0.5), 2) AS p50,
       round(quantile_cont(value, 0.9), 2) AS p90,
       count(*) AS n
FROM fact
WHERE metric = '${params.football_metric}' AND sport = 'football' AND family = 'physical'
  AND NOT is_season_total`,
  },
];
