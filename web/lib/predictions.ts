import data from "./data/predictions.json";

export type RoundKey =
  | "reach_r32"
  | "reach_r16"
  | "reach_qf"
  | "reach_sf"
  | "reach_final"
  | "win";

export const ROUND_ORDER: RoundKey[] = [
  "reach_r32",
  "reach_r16",
  "reach_qf",
  "reach_sf",
  "reach_final",
  "win",
];

export const ROUND_LABEL: Record<RoundKey, string> = {
  reach_r32: "R32",
  reach_r16: "R16",
  reach_qf: "QF",
  reach_sf: "SF",
  reach_final: "Final",
  win: "Win",
};

export type Prediction = {
  tla: string;
  name: string;
  win_probability_raw: number;
  win_probability_adjusted: number;
  round_probability?: Partial<Record<RoundKey, number>>;
};

export type MatchOutcome = "H" | "D" | "A";

export type GroupMatch = {
  group: string | null;
  home: string;
  away: string;
  home_name: string;
  away_name: string;
  neutral: boolean;
  utc_date: string;
  /** For FINISHED matches these are the FROZEN pre-match probabilities —
   * what the model said before kickoff, never retro-fitted. */
  p_home_win: number;
  p_draw: number;
  p_away_win: number;
  expected_home_goals: number;
  expected_away_goals: number;
  status?: "FINISHED" | "SCHEDULED";
  actual_home_goals?: number;
  actual_away_goals?: number;
  predicted_outcome?: MatchOutcome;
  actual_outcome?: MatchOutcome;
  prediction_hit?: boolean;
  /** True when the match finished before we ever snapshotted it — the
   * "pre-match" numbers were computed by a model that had already seen
   * the result. Take the comparison with a grain of salt. */
  prediction_post_hoc?: boolean;
};

/** A real Round-of-32 tie with the four-outcome prediction and (once played)
 * the actual result. "Advancer" is H (home/Team A) or A (away/Team B) — a
 * knockout always produces one. These predictions are inherently pre-match:
 * the model's ratings never ingest knockout results. */
export type KnockoutR32Match = {
  home: string;
  away: string;
  home_name: string;
  away_name: string;
  host_home: boolean;
  utc_date: string;
  // The four mutually-exclusive outcomes (sum to 1)
  p_home_win_reg: number;
  p_away_win_reg: number;
  p_draw_home_adv: number;
  p_draw_away_adv: number;
  // Advance probabilities (each = reg win + draw-then-advance)
  p_home_advances: number;
  p_away_advances: number;
  expected_home_goals: number;
  expected_away_goals: number;
  predicted_advancer: "H" | "A";
  favored_name: string;
  tier: "strong" | "lean" | "tossup";
  status: "FINISHED" | "SCHEDULED";
  resolution?: "REGULAR" | "EXTRA_TIME" | "PENALTY_SHOOTOUT";
  actual_home_goals?: number;
  actual_away_goals?: number;
  pens_home?: number | null;
  pens_away?: number | null;
  actual_advancer?: "H" | "A";
  prediction_hit?: boolean;
  prediction_post_hoc?: boolean;
};

export type KnockoutMatch = {
  match_idx: number;
  home_top: string;
  home_top_name: string;
  p_home_top: number;
  away_top: string;
  away_top_name: string;
  p_away_top: number;
  p_matchup_top: number;
  p_home_win: number;
  p_draw: number;
  p_away_win: number;
  expected_home_goals: number;
  expected_away_goals: number;
};

export type KnockoutRound = {
  round: "R32" | "R16" | "QF" | "SF" | "F";
  round_size: number;
  n_matches: number;
  matches: KnockoutMatch[];
};

export type PredictionsFile = {
  metadata: {
    generated_at: string;
    n_sims: number;
    seed: number;
    host_continent: string;
    n_teams: number;
    n_group_fixtures: number;
    dc_home_advantage: number;
    dc_rho: number;
    dc_fit_matches: number;
    model_version: string;
    n_finished_matches?: number;
  };
  predictions: Prediction[];
  group_matches: GroupMatch[];
  knockout_bracket: KnockoutRound[];
  knockout_r32?: KnockoutR32Match[];
};

export const ROUND_FULL_NAMES: Record<KnockoutRound["round"], string> = {
  R32: "Round of 32",
  R16: "Round of 16",
  QF: "Quarter-finals",
  SF: "Semi-finals",
  F: "Final",
};

export const predictions: PredictionsFile = data as PredictionsFile;

/** Top N teams by adjusted win probability. */
export function topN(n: number): Prediction[] {
  return [...predictions.predictions]
    .sort((a, b) => b.win_probability_adjusted - a.win_probability_adjusted)
    .slice(0, n);
}

/** Real R32 ties in kickoff-date order. */
export function knockoutR32(): KnockoutR32Match[] {
  return [...(predictions.knockout_r32 ?? [])].sort((a, b) =>
    a.utc_date.localeCompare(b.utc_date),
  );
}

/** Group group_matches by group letter, preserving date order within each group. */
export function matchesByGroup(): Map<string, GroupMatch[]> {
  const map = new Map<string, GroupMatch[]>();
  for (const m of predictions.group_matches) {
    const key = m.group ?? "?";
    const arr = map.get(key) ?? [];
    arr.push(m);
    map.set(key, arr);
  }
  // Sort each group's matches by date
  for (const arr of map.values()) {
    arr.sort((a, b) => a.utc_date.localeCompare(b.utc_date));
  }
  return new Map([...map.entries()].sort(([a], [b]) => a.localeCompare(b)));
}
