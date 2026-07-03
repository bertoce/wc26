"""Tests for the four-outcome knockout predictor (wc26/knockout.py)."""

from wc26.knockout import confidence_tier, four_outcome_prediction


def test_four_outcomes_sum_to_one_and_decompose_advance():
    p = four_outcome_prediction(0.6, -0.3, 0.2, 0.1, home_advantage=0.25,
                                rho=-0.05, host_home=False)
    four = (p["a_win_regulation"], p["b_win_regulation"],
            p["draw_then_a_advances"], p["draw_then_b_advances"])
    assert abs(sum(four) - 1.0) < 1e-9
    assert abs(p["p_a_advances"] + p["p_b_advances"] - 1.0) < 1e-9
    # Advance probability decomposes into regulation win + draw-then-advance.
    assert abs(p["p_a_advances"] - (p["a_win_regulation"] + p["draw_then_a_advances"])) < 1e-12
    assert abs(p["p_b_advances"] - (p["b_win_regulation"] + p["draw_then_b_advances"])) < 1e-12


def test_stronger_team_more_likely_to_advance():
    strong = four_outcome_prediction(1.0, -0.5, -0.2, 0.4, home_advantage=0.25,
                                     rho=-0.05, host_home=False)
    assert strong["p_a_advances"] > strong["p_b_advances"]


def test_host_home_helps_the_home_side():
    away_venue = four_outcome_prediction(0.3, 0.0, 0.3, 0.0, home_advantage=0.3,
                                         rho=-0.05, host_home=False)
    home_venue = four_outcome_prediction(0.3, 0.0, 0.3, 0.0, home_advantage=0.3,
                                          rho=-0.05, host_home=True)
    assert home_venue["p_a_advances"] > away_venue["p_a_advances"]


def test_confidence_tier_thresholds():
    assert confidence_tier(0.88) == "strong"
    assert confidence_tier(0.12) == "strong"   # symmetric on the favourite
    assert confidence_tier(0.64) == "lean"
    assert confidence_tier(0.55) == "tossup"
