"""Offline smoke checks for a selected installed dependency extra."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from importlib import import_module
from importlib.metadata import version
from importlib.resources import files


def check_install(feature="runtime", require_wheel=False):
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
        with tempfile.TemporaryDirectory(prefix="tennis-web-smoke-") as directory:
            tournament = Path(directory) / "2024" / "smoke"
            tournament.mkdir(parents=True)
            players = {name: {"seed": seed, "cost": 10} for seed, name in enumerate(
                ("Fixture A", "Fixture B", "Fixture C"), start=1
            )}
            (tournament / "players_male.json").write_text(json.dumps(players), encoding="utf-8")
            previous = os.environ.get("TENNIS_DATA_ROOT")
            os.environ["TENNIS_DATA_ROOT"] = directory
            try:
                server = import_module("web_interface.server")
                import_module("web_interface.match_simulator")
                import_module("web_interface.team_optimizer")
                for resource in ("index.html", "app.js", "styles.css"):
                    assert files("web_interface").joinpath(resource).is_file(), resource
                with server.app.test_client() as client:
                    for path in ("/", "/app.js", "/styles.css"):
                        assert client.get(path).status_code == 200, path
                    assert client.get("/api/tournaments").json[0]["id"] == "2024/smoke"
                    assert len(client.get("/api/players/2024/smoke/male").json) == 3
                    response = client.post("/api/simulate-match", json={
                        "tournament_path": "2024/smoke", "gender": "male",
                        "player1_name": "Fixture A", "player2_name": "Fixture B",
                        "sets_to_win": 1, "num_simulations": 1,
                    })
                    assert response.status_code == 200, response.json
                    response = client.post("/api/optimize-team", json={
                        "tournament_path": "2024/smoke", "gender": "male", "team_size": 2,
                    })
                    assert response.status_code == 200, response.json
            finally:
                if previous is None:
                    os.environ.pop("TENNIS_DATA_ROOT")
                else:
                    os.environ["TENNIS_DATA_ROOT"] = previous

    if require_wheel:
        for name, module in tuple(sys.modules.items()):
            if name.split(".")[0] in ("tennis_api", "tennis_pool", "tennis_preds", "web_interface"):
                location = getattr(module, "__file__", None)
                if location:
                    assert Path(location).resolve().is_relative_to(Path(sys.prefix).resolve()), location


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feature", choices=("runtime", "ml", "excel", "web", "all"))
    parser.add_argument("--require-wheel", action="store_true")
    args = parser.parse_args()
    check_install(args.feature, args.require_wheel)
    print(f"Installation smoke check passed: {args.feature}")
