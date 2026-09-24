// The published possession (task 17), as validated by schema.json.

export type Sport = "basketball" | "football";
export type ClockKind = "countdown" | "elapsed";

export interface Surface {
  spec: string;
  length_m: number;
  width_m: number;
}

export interface Entity {
  i: number;
  entity_id: string;
  kind: "player" | "ball";
  team_id: string | null;
  jersey: string | null;
  name: string | null;
}

// [entity index, x_m, y_m, z_m or null, is_detected 0/1], venue frame.
export type Observation = [number, number, number, number | null, 0 | 1];

export interface Frame {
  t: number;
  clock: number;
  o: Observation[];
}

export interface Possession {
  schema_version: number;
  possession_id: string;
  sport: Sport;
  match: { match_id: string; home: string; away: string; kickoff_utc: string };
  surface: Surface;
  clock_kind: ClockKind;
  sample_rate_hz: number;
  team_in_possession: string;
  attack_sign: 1 | -1;
  entities: Entity[];
  frames: Frame[];
}
