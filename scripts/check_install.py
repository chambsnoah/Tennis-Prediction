"""Offline smoke checks for a selected installed dependency extra."""

import argparse
from importlib import import_module
from importlib.metadata import version
from importlib.resources import files


def check_install(feature="runtime"):
    api = import_module("tennis_api")
    assert api.__version__ == version("tennis-prediction")
    for name in api.__all__:
        getattr(api, name)
    for module in (
        "tennis_api.adapters.http_adapter",
        "tennis_api.config.api_config",
        "tennis_preds.tennis",
    ):
        import_module(module)
    rules = import_module("tennis_pool.rules")
    rules.load_register()

    if feature in ("ml", "all"):
        models = import_module("tennis_api.models")
        ml = import_module("tennis_api.ml")
        for package in (models, ml):
            for name in package.__all__:
                getattr(package, name)
        for module in (
            "tennis_api.models.ai_player",
            "tennis_api.ml.feature_engineering",
            "tennis_api.ml.prediction_models",
        ):
            assert import_module(module).ML_AVAILABLE, module
        import_module("tennis_api.simulation.enhanced_match_engine")

    if feature in ("excel", "all"):
        excel = import_module("openpyxl")
        workbook = excel.Workbook()
        assert workbook.active is not None
        workbook.close()

    if feature in ("web", "all"):
        server = import_module("web_interface.server")
        import_module("web_interface.match_simulator")
        import_module("web_interface.team_optimizer")
        for resource in ("index.html", "app.js", "styles.css"):
            assert files("web_interface").joinpath(resource).is_file(), resource
        with server.app.test_client() as client:
            for path in ("/", "/app.js", "/styles.css"):
                assert client.get(path).status_code == 200, path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature", choices=("runtime", "ml", "excel", "web", "all"))
    args = parser.parse_args()
    check_install(args.feature)
    print(f"Installation smoke check passed: {args.feature}")
