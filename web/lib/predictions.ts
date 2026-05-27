import data from "./data/predictions.json";

export type Prediction = {
  tla: string;
  name: string;
  win_probability_raw: number;
  win_probability_adjusted: number;
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
  };
  predictions: Prediction[];
};

export const predictions: PredictionsFile = data as PredictionsFile;

/** Top N teams by adjusted win probability. */
export function topN(n: number): Prediction[] {
  return [...predictions.predictions]
    .sort((a, b) => b.win_probability_adjusted - a.win_probability_adjusted)
    .slice(0, n);
}
