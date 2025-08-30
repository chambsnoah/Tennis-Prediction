"""
Machine Learning Package for Tennis Prediction

This package contains ML models, feature engineering, and prediction engines
for advanced tennis match prediction using real-time data and contextual factors.
"""

from typing import List

# Lazy export map: name -> (module, attr)
_EXPORTS = {
    "FeatureExtractor": (".feature_engineering", "FeatureExtractor"),
    "FeatureConfig": (".feature_engineering", "FeatureConfig"),
    "FeatureType": (".feature_engineering", "FeatureType"),
    "OutcomePredictor": (".prediction_models", "OutcomePredictor"),
    "ScorePredictor": (".prediction_models", "ScorePredictor"),
    "UpsetDetector": (".prediction_models", "UpsetDetector"),
    "PredictionEnsemble": (".ensemble", "PredictionEnsemble"),
    "ModelTrainer": (".training", "ModelTrainer"),
}

__all__: List[str] = [
    "FeatureExtractor",
    "FeatureConfig", 
    "FeatureType",
    "OutcomePredictor",
    "ScorePredictor",
    "UpsetDetector",
    "PredictionEnsemble",
    "ModelTrainer",
]


# PEP 562: Lazy attribute access for re-exports
def __getattr__(name: str):
    try:
        from importlib import import_module
        mod_name, attr = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    module = import_module(mod_name, __package__)
    value = getattr(module, attr)
    globals()[name] = value  # cache after first access
    return value


def __dir__():
    return sorted(__all__)