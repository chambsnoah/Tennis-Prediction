"""Synthetic regression coverage for missing provider observations (issue #2)."""

import json

import numpy as np
import pytest

from tennis_api.models.player_stats import (
    PlayerStats,
    ReturnStatistics,
    ServeStatistics,
)
from tennis_api.clients.tennis_live_client import TennisLiveAPIClient
from tennis_api.clients.tennis_stats_client import TennisStatsAPIClient
from tennis_api.clients.tennis_stats_client_clean import (
    TennisStatsAPIClient as CleanStatsClient,
)
from tennis_api.ml.feature_engineering import FeatureConfig, FeatureExtractor
from tennis_api.ml.ensemble import PredictionEnsemble
from tennis_api.models.ai_player import MLModel, PerformanceContext, PlayerAI
from tennis_api.models.enhanced_player import PlayerEnhanced
from tennis_api.integration import (
    PlayerEnhanced as IntegratedPlayer,
    PlayerSimpleEnhanced,
)
from tennis_api.extractors.api_extractor import APIPlayerExtractor
from tennis_api.simulation.enhanced_match_engine import EnhancedMatchEngine


@pytest.mark.parametrize("model", [ServeStatistics, ReturnStatistics])
def test_omitted_statistics_are_null_and_round_trip(model):
    empty = model()
    assert all(value is None for value in empty.to_dict().values())
    assert model.from_dict({}).to_dict() == empty.to_dict()
    assert (
        model.from_dict(json.loads(json.dumps(empty.to_dict()))).to_dict()
        == empty.to_dict()
    )


@pytest.mark.parametrize("block", ["serve_stats", "return_stats"])
def test_missing_or_null_blocks_remain_empty_statistics(block):
    for data in ({"name": "Synthetic A"}, {"name": "Synthetic A", block: None}):
        player = PlayerStats.from_dict(data)
        assert all(value is None for value in player.to_dict()[block].values())
        assert PlayerStats.from_json(player.to_json()).to_dict() == player.to_dict()


def test_partial_statistics_preserve_zero_and_both_existing_key_formats():
    serve = ServeStatistics.from_dict(
        {"first_serve_win_percentage": 0.0, "aces_per_match": 0.0}
    )
    assert serve.first_serve_win_percentage == 0.0
    assert serve.aces_per_match == 0.0
    assert serve.second_serve_win_percentage is None
    assert ServeStatistics.from_dict(serve.to_dict()) == serve
    # Established serialized keys take precedence, even when explicitly null.
    assert (
        ServeStatistics.from_dict(
            {"first_serve_win_pct": None, "first_serve_win_percentage": 0.7}
        ).first_serve_win_percentage
        is None
    )
    returns = ReturnStatistics.from_dict({"first_serve_return_points_won": 0.0})
    assert returns.first_serve_return_points_won == 0.0
    assert ReturnStatistics.from_dict(returns.to_dict()) == returns


@pytest.mark.parametrize("client_type", [TennisStatsAPIClient, CleanStatsClient])
def test_provider_parser_does_not_reintroduce_defaults(client_type):
    client = object.__new__(client_type)
    player = client._parse_detailed_player_stats(
        {"statistics": {"serve": {"aces_per_match": 0.0}, "return": None}},
        {},
        [],
        "Synthetic A",
    )
    assert player.serve_stats.aces_per_match == 0.0
    assert player.serve_stats.first_serve_win_percentage is None
    assert all(value is None for value in player.return_stats.to_dict().values())


def test_live_aggregation_never_estimates_granular_observations():
    client = object.__new__(TennisLiveAPIClient)
    for matches in (
        [],
        [{}],
        [
            {
                "statistics": {
                    "serve_points_won": 30,
                    "serve_points_total": 50,
                    "return_points_won": 10,
                    "return_points_total": 50,
                }
            }
        ],
    ):
        serve, returns, _ = client._calculate_stats_from_matches(matches)
        assert all(value is None for value in serve.to_dict().values())
        assert all(value is None for value in returns.to_dict().values())


def test_live_rates_use_only_paired_observations_and_preserve_measured_zero():
    client = object.__new__(TennisLiveAPIClient)
    serve, returns, form = client._calculate_stats_from_matches(
        [
            {
                "winner": "A",
                "player": "A",
                "statistics": {
                    "first_serve_made": 10,
                    "first_serve_won": 0,
                    "second_serve_made": 4,
                    "second_serve_won": 2,
                    "first_serve_return_points": 20,
                    "first_serve_return_won": 5,
                },
            },
            {
                "statistics": {
                    "first_serve_made": 90,
                    "first_serve_return_points": 80,
                    "second_serve_return_points": 0,
                    "second_serve_return_won": 0,
                }
            },
        ]
    )
    assert serve.first_serve_win_percentage == 0.0
    assert serve.second_serve_win_percentage == 0.5
    assert returns.first_serve_return_points_won == 0.25
    assert returns.second_serve_return_points_won is None
    assert serve.first_serve_percentage is None
    assert form == ["W"]


@pytest.mark.parametrize(
    "won,total",
    [(None, 10), (0, None), (True, 10), (-1, 10), (11, 10), (np.nan, 10), (1, np.inf)],
)
def test_invalid_live_count_pairs_do_not_become_observations(won, total):
    client = object.__new__(TennisLiveAPIClient)
    serve, _, _ = client._calculate_stats_from_matches(
        [{"statistics": {"first_serve_won": won, "first_serve_made": total}}]
    )
    assert serve.first_serve_win_percentage is None


def test_trained_ensemble_requires_fitted_preprocessing():
    ensemble = PredictionEnsemble()
    ensemble.outcome_predictor.is_trained = True
    with pytest.raises(ValueError, match="fitted missing-value"):
        ensemble.predict_match({}, {}, {})


def test_raw_features_preserve_missingness_and_serialized_measurements():
    extractor = FeatureExtractor()
    p1 = PlayerStats(
        "Synthetic A", serve_stats=ServeStatistics(first_serve_win_percentage=0.0)
    )
    features = extractor.extract_statistical_features(
        p1.to_dict(), {"serve_stats": None}
    )
    assert features["player1_first_serve_win"] == 0.0
    assert np.isnan(features["player2_first_serve_win"])
    assert np.isnan(features["first_serve_advantage"])
    assert np.isnan(features["player1_break_points"])


@pytest.mark.parametrize(
    "policy, expected", [("median", 4.0), ("mean", 5.0), ("zero", 0.0)]
)
def test_imputation_is_explicit_and_uses_only_training_values(policy, expected):
    extractor = FeatureExtractor(
        FeatureConfig(
            scaling_method="none",
            use_feature_selection=False,
            handle_missing_values=policy,
        )
    )
    training = [
        {"observed": 1.0},
        {"observed": 4.0},
        {"observed": 10.0},
        {"observed": np.nan},
    ]
    with pytest.warns(RuntimeWarning, match="Imputing"):
        extractor.fit_transformers(training)
    with pytest.warns(RuntimeWarning, match="Imputing"):
        assert extractor.transform_features({}) == [expected]
    assert extractor.missing_features == ["observed"]
    assert extractor.transform_features({"observed": 0.0}) == [0.0]
    assert extractor.missing_features == []


@pytest.mark.parametrize("policy", ["median", "mean", "drop"])
def test_unfillable_or_rejected_training_missingness_fails_closed(policy):
    extractor = FeatureExtractor(FeatureConfig(handle_missing_values=policy))
    with pytest.raises(ValueError, match="missing"):
        extractor.fit_transformers([{"unreported": np.nan}])
    assert not extractor.is_fitted


def test_scaling_and_feature_selection_use_same_training_and_inference_pipeline():
    rows = [{"one": float(i), "two": float(i * 2), "three": 1.0} for i in range(8)]
    extractor = FeatureExtractor(
        FeatureConfig(max_features=2, feature_selection_method="f_test")
    )
    extractor.fit_transformers(rows, [float(i) for i in range(8)])
    assert len(extractor.feature_names) == 2
    assert len(extractor.input_feature_names) == 3
    assert len(extractor.transform_features(rows[0])) == 2
    assert np.isfinite(extractor.transform_features(rows[0])).all()


def test_ensemble_training_consumes_transformed_features_and_reports_missingness(
    monkeypatch,
):
    ensemble = PredictionEnsemble(
        feature_config=FeatureConfig(
            handle_missing_values="zero",
            scaling_method="none",
            use_feature_selection=False,
        )
    )
    received = []

    def train(vectors, targets, names):
        received.append((vectors, targets, names))
        return {}

    monkeypatch.setattr(ensemble.outcome_predictor, "train", train)
    with pytest.warns(RuntimeWarning, match="Imputing"):
        ensemble.train_ensemble(
            {
                "features": [
                    {
                        "player1": {"current_ranking": 1},
                        "player2": {"current_ranking": 2},
                    }
                ],
                "outcomes": [1],
            }
        )
    vectors, targets, names = received[0]
    assert np.isfinite(vectors).all()
    assert vectors[0][names.index("player1_first_serve_win")] == 0.0
    assert vectors[0][names.index("ranking_difference")] == -1.0
    assert targets == [1]
    with pytest.warns(RuntimeWarning, match="Imputing"):
        result = ensemble.predict_match({}, {}, {})
    assert "player1_first_serve_win" in result.explanation["missing_features"]
    assert result.explanation["imputation_policy"] == "zero"


def test_untrained_ensemble_fallback_reports_missing_features_without_inventing_stats():
    result = PredictionEnsemble().predict_match({}, {}, {})
    assert "player1_first_serve_win" in result.explanation["missing_features"]
    assert result.explanation["imputation_policy"] is None


def test_legacy_simulation_assumptions_never_mutate_or_export_observations():
    stats = PlayerStats("Synthetic A")
    with pytest.warns(RuntimeWarning, match="simulation assumption"):
        assert np.isfinite(
            PlayerEnhanced(
                "Synthetic A", api_stats=stats
            ).get_adjusted_serve_percentage("hard", 100)
        )
    with pytest.warns(RuntimeWarning, match="simulation assumptions"):
        player = IntegratedPlayer("Synthetic A", api_stats=stats)
    with pytest.warns(RuntimeWarning, match="simulation assumptions"):
        simple = PlayerSimpleEnhanced("Synthetic A", api_stats=stats)
    assert np.isfinite(simple.points_won_on_serve_percentage)
    assert player.to_dict()["serve_percentage"] is None
    assert player.to_dict()["return_percentage"] is None
    assert all(value is None for value in stats.serve_stats.to_dict().values())
    fallback = object.__new__(APIPlayerExtractor)._get_fallback_player_data(
        "Synthetic B", None, 100
    )
    assert fallback["serve_percentage"] is None
    assert fallback["return_percentage"] is None


def test_player_ai_excludes_unobserved_labels_and_incomplete_features():
    stats = PlayerStats(
        "Synthetic A",
        serve_stats=ServeStatistics(
            first_serve_percentage=0.0,
            first_serve_win_percentage=0.0,
            aces_per_match=0.0,
        ),
        return_stats=ReturnStatistics(
            first_serve_return_points_won=0.0,
            second_serve_return_points_won=0.0,
            break_points_converted=0.0,
        ),
    )
    player = PlayerAI("Synthetic A", api_stats=stats)
    context = PerformanceContext()
    with pytest.warns(RuntimeWarning, match="Skipping"):
        player.update_models_after_match("W", {}, context)
    assert player.training_labels["serve"] == []
    assert player.training_labels["return"] == []
    player.update_models_after_match(
        "W", {"serve_percentage": 0.0, "return_percentage": 0.0}, context
    )
    assert player.training_labels["serve"] == [0.0]
    assert player.training_labels["return"] == [0.0]
    stats.serve_stats.aces_per_match = None
    with pytest.warns(RuntimeWarning, match="Skipping serve"):
        player.update_models_after_match(
            "W", {"serve_percentage": 0.5, "return_percentage": 0.0}, context
        )
    assert player.training_labels["serve"] == [0.0]


def test_trained_player_model_rejects_missing_observations_and_training_labels():
    model = MLModel("serve_predictor")
    model.is_trained = True
    with pytest.raises(ValueError, match="Missing observations"):
        model.predict([np.nan])
    with pytest.raises(ValueError, match="Missing observations or labels"):
        model.train([[0.0]], [np.nan])


def test_saved_ensemble_preserves_fitted_imputation_and_scaling(tmp_path):
    path = str(tmp_path / "synthetic")
    ensemble = PredictionEnsemble()
    ensemble.feature_extractor.fit_transformers([{"observed": 2.0}, {"observed": 6.0}])
    ensemble.is_trained = True
    ensemble.save_ensemble(path)
    restored = PredictionEnsemble()
    restored.load_ensemble(path)
    with pytest.warns(RuntimeWarning, match="Imputing"):
        assert restored.feature_extractor.transform_features({}) == [0.0]
    assert restored.feature_extractor.imputation_values == {"observed": 4.0}


def test_legacy_saved_ensemble_requires_retraining(tmp_path):
    path = str(tmp_path / "legacy")
    (tmp_path / "legacy_ensemble.json").write_text(json.dumps({"is_trained": True}))
    with pytest.raises(ValueError, match="retrain"):
        PredictionEnsemble().load_ensemble(path)


def test_partial_retraining_preserves_preprocessing_used_by_other_models(monkeypatch):
    ensemble = PredictionEnsemble(
        feature_config=FeatureConfig(use_feature_selection=False)
    )

    def train_outcome(vectors, targets, names):
        ensemble.outcome_predictor.is_trained = True
        return {}

    received = []

    def train_score(vectors, targets, names):
        received.extend(vectors)
        return {}

    monkeypatch.setattr(ensemble.outcome_predictor, "train", train_outcome)
    monkeypatch.setattr(ensemble.score_predictor, "train", train_score)
    ensemble.train_ensemble(
        {"features": [[0.0], [10.0]], "feature_names": ["value"], "outcomes": [0, 1]}
    )
    ensemble.train_ensemble(
        {
            "features": [[100.0], [200.0]],
            "feature_names": ["value"],
            "scores": {"winner_sets": [2, 2]},
        }
    )
    assert ensemble.feature_extractor.imputation_values == {"value": 5.0}
    assert received == [[19.0], [39.0]]


def test_simulation_prediction_adapter_forwards_available_observations():
    stats = PlayerStats(
        "Synthetic A",
        serve_stats=ServeStatistics(
            first_serve_win_percentage=0.75,
            second_serve_win_percentage=0.5,
            aces_per_match=0.0,
        ),
        return_stats=ReturnStatistics(
            first_serve_return_points_won=0.25, break_points_converted=0.0
        ),
    )
    player = PlayerEnhanced("Synthetic A", api_stats=stats)
    data = EnhancedMatchEngine()._prepare_player_data(player)
    features = FeatureExtractor().extract_statistical_features(data, data)
    assert features["player1_aces_per_match"] == 0.0
    assert features["player1_return_first_serve"] == 0.25
    assert features["player1_break_points"] == 0.0
    assert np.isfinite(list(features.values())).all()
