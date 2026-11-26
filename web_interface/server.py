#!/usr/bin/env python3
"""Single-user local web app for tennis simulation and pool decision support.

Start it with one command (it binds 127.0.0.1 only, never with the debugger)::

    python -m web_interface

Routes call ``LocalServices`` directly; heavy work runs as bounded jobs. Errors
return a reason code only. Public or multi-user hosting is out of scope.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from collections.abc import Sequence
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response as BaseResponse

from web_interface.config import LocalAppConfig
from web_interface.errors import ServiceError
from web_interface.services import LocalServices

WEB_ROOT = Path(__file__).resolve().parent
STATIC_FILES = {"app.js", "styles.css"}
LOG = logging.getLogger("web_interface.server")
_HTTP_CODES = {400: "bad_request", 403: "forbidden", 404: "not_found",
               405: "method_not_allowed", 413: "payload_too_large", 415: "unsupported_media_type"}


def _error(code: str, status: int) -> tuple[Response, int]:
    return jsonify({"error": code}), status


def create_app(config: LocalAppConfig, services: LocalServices | None = None) -> Flask:
    services = services or LocalServices(config)
    app = Flask(__name__, static_folder=None)
    app.config.update(
        DEBUG=False,
        PROPAGATE_EXCEPTIONS=False,
        # Werkzeug enforces this while reading; JSON routes lower it per request.
        MAX_CONTENT_LENGTH=config.max_upload_bytes,
        # Refuse DNS-rebinding hosts: only loopback names reach the routes.
        TRUSTED_HOSTS=["127.0.0.1", "localhost"],
    )
    origins = {f"http://{host}:{config.port}" for host in ("127.0.0.1", "localhost")}

    @app.before_request
    def guard() -> tuple[Response, int] | None:
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin is not None and origin not in origins:
                return _error("cross_origin_request", 403)
            if request.endpoint == "preview_workbook":
                if request.mimetype != "application/octet-stream":
                    return _error("octet_stream_required", 415)
            else:
                request.max_content_length = config.max_json_bytes
                if request.mimetype != "application/json":
                    return _error("json_required", 415)
        return None

    def body() -> object:
        return request.get_json(silent=True)

    @app.errorhandler(ServiceError)
    def service_error(error: ServiceError) -> tuple[Response, int]:
        return _error(error.code, error.status)

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> BaseResponse:
        # Start from Werkzeug's response so headers such as Allow (405) survive.
        response = error.get_response()
        status = error.code or 500
        response.set_data(json.dumps({"error": _HTTP_CODES.get(status, "http_error")}))
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def internal_error(error: Exception) -> tuple[Response, int]:
        request_id = uuid.uuid4().hex[:12]
        # Type name only: messages and tracebacks can carry paths or credentials.
        LOG.error("Internal error %s in %s: %s", request_id, request.endpoint,
                  type(error).__name__)
        response = jsonify({"error": "internal_error", "request_id": request_id})
        return response, 500

    @app.get("/")
    def index() -> Response:
        return send_from_directory(WEB_ROOT, "index.html")

    @app.get("/<name>")
    def static_file(name: str) -> Response | tuple[Response, int]:
        if name not in STATIC_FILES:
            return _error("not_found", 404)
        return send_from_directory(WEB_ROOT, name)

    @app.get("/api/status")
    def status() -> Response:
        return jsonify(services.status())

    @app.get("/api/tournaments")
    def tournaments() -> Response:
        return jsonify(services.tournaments())

    @app.get("/api/players/<year>/<slug>/<gender>")
    def players(year: str, slug: str, gender: str) -> Response:
        return jsonify(services.players(f"{year}/{slug}", gender))

    @app.get("/api/bracket/<year>/<slug>/<gender>")
    def bracket(year: str, slug: str, gender: str) -> Response:
        return jsonify(services.bracket(f"{year}/{slug}", gender))

    @app.post("/api/simulate-match")
    def simulate_match() -> Response:
        return jsonify(services.simulate_match(body()))

    @app.post("/api/optimize-team")
    def optimize_team() -> Response:
        return jsonify(services.optimize_team(body()))

    @app.post("/api/workbooks/preview")
    def preview_workbook() -> Response:
        data = request.get_data(cache=False)
        return jsonify(services.preview_workbook(data, request.args.to_dict()))

    @app.post("/api/predict")
    def predict() -> Response:
        return jsonify(services.predict(body()))

    @app.post("/api/pool/scenarios")
    def pool_scenarios() -> Response:
        return jsonify(services.simulate_tournament(body()))

    @app.post("/api/pool/recommend")
    def pool_recommend() -> Response:
        return jsonify(services.recommend(body()))

    return app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the local Tennis Prediction app on 127.0.0.1.")
    parser.add_argument("--port", type=int, help="port (default TENNIS_PORT or 5000)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = LocalAppConfig.from_env(os.environ, port=args.port)
        app = create_app(config)
    except ServiceError as error:
        print(f"Cannot start: {error.code}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"Cannot start: {error}", file=sys.stderr)
        return 2
    print(f"Tennis Prediction local app: http://{config.HOST}:{config.port}")
    app.run(host=config.HOST, port=config.port, debug=False, use_reloader=False,
            use_debugger=False, threaded=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
