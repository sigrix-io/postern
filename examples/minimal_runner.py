"""A minimal, conformant Postern runner: real HTTP, no framework, one file.

    python examples/minimal_runner.py [port]      # defaults to 8787

Serves the "Market Research Crew" example agent used throughout `examples/`
at Level 3, with no distributor — the common case for an agent that is
free, self-authored, or local, where `entitlement` is always
`{"state": "not_required"}` and section 5 does not apply. Point the checker
or `examples/client.py` at it:

    python examples/minimal_runner.py &
    postern-conformance --execute http://127.0.0.1:8787
    OPENAI_API_KEY=x python examples/client.py http://127.0.0.1:8787 segment="B2B SaaS observability"

`OPENAI_API_KEY` gates `run`/`stream` the way section 4.6 step 5 requires —
set it to anything, since this runner never calls out to it, it only checks
that it is set. Nothing here calls a model; `OUTPUT_VALUE` below is what
every run answers, which is what makes the example runnable with no
network and no API key spent.

What conformance actually requires reduces to what is below: refuse a
browser origin you did not configure (`_cors`, section 2.3), answer
`describe`/`status`/`run`/`stream` (sections 4.1 through 4.4), and apply
`run`/`stream`'s refusals in the order section 4.6 fixes — level, then
entitlement, then media type, then the request body, then credentials —
never the agent's own work ahead of any of them. Idempotency and a `bytes`
output are real but optional, and left out here for the same reason the
distributor is: `tools/conformance/tests/fake_runner.py` is the fixture
that exercises those, and every way of getting the checks above wrong, for
the checker's own test suite. It imports the payload below rather than
keeping its own copy, so the two cannot silently disagree about what this
example agent returns.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

LEVEL = 3

ALLOWED_ORIGIN = "https://app.example.com"

DESCRIBE: dict[str, Any] = {
    "postern": "0.1",
    "agent": {
        "id": "acme/market-research-crew",
        "name": "Market Research Crew",
        "version": "1.3.0",
        "summary": "Researches a market segment and returns a positioning brief.",
    },
    "inputs": [
        {
            "key": "segment",
            "label": "Market segment",
            "type": "text",
            "required": True,
            "default": None,
            "validation": {"max_length": 200},
        },
        {
            "key": "depth",
            "label": "Depth",
            "type": "select",
            "required": False,
            "default": "standard",
            "validation": {"options": ["quick", "standard", "exhaustive"]},
        },
    ],
    "output": {"type": "text", "example": "## Positioning brief"},
    "capabilities": {
        "tools": ["serper_search", "file_write"],
        "write_tools": ["file_write"],
    },
    "credentials": [
        {
            "env": "OPENAI_API_KEY",
            "purpose": "Runs the agents in this crew.",
            "signup_url": "https://platform.openai.com/api-keys",
        }
    ],
}

OUTPUT_VALUE = "## Positioning brief\n\nThe mid-market segment is underserved."
DELTAS = ["## Positioning brief\n", "\nThe mid-market segment ", "is underserved."]


def error(code: str, message: str, *, detail: Any = None) -> dict[str, Any]:
    """Section 2.1's envelope: every non-2xx body is `{"error": {...}}`, nothing beside it."""
    return {"error": {"code": code, "message": message, "detail": detail}}


def validation_failure(inputs: dict[str, Any]) -> str | None:
    """The first declared constraint `inputs` breaks, or None.

    Read off DESCRIBE rather than restated, so a runner enforcing a rule it
    does not publish (section 4.2) is not a mistake this function can make.
    """
    for declared in DESCRIBE["inputs"]:
        key = declared["key"]
        if key not in inputs:
            continue
        value = inputs[key]
        rules = declared.get("validation") or {}

        options = rules.get("options")
        if isinstance(options, list) and value not in options:
            return f"'{key}' must be one of {', '.join(options)}."

        max_length = rules.get("max_length")
        if (
            isinstance(max_length, int)
            and isinstance(value, str)
            and len(value) > max_length
        ):
            return f"'{key}' is longer than {max_length} characters."
    return None


def missing_credentials() -> list[str]:
    """The declared env vars this process does not have — section 4.6 step 5's check."""
    return [c["env"] for c in DESCRIBE["credentials"] if not os.environ.get(c["env"])]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "minimal-postern/0.1"

    def log_message(self, *args: Any) -> None:  # pragma: no cover - quiet by design
        pass

    # ---- section 2.3: browser origins --------------------------------------

    def _cors(self, methods: str = "") -> dict[str, str]:
        """Allow only the one configured origin, and say so in `Vary`.

        No header for a stranger's origin is not an oversight — it is what
        makes serving `run` over plain HTTP safe at all, since a runner
        defines no authentication of its own (section 2.3). curl and
        server-to-server calls never send `Origin` and are never affected;
        only a browser enforces what this method publishes.
        """
        origin = self.headers.get("Origin")
        headers: dict[str, str] = {}
        if origin == ALLOWED_ORIGIN:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Vary"] = "Origin"
        if methods:
            headers["Access-Control-Allow-Methods"] = methods
            headers["Access-Control-Allow-Headers"] = "Content-Type"
        return headers

    def do_OPTIONS(self) -> None:
        verb = self._verb()
        methods = "GET, OPTIONS" if verb in ("describe", "status") else "POST, OPTIONS"
        self.send_response(204)
        for key, value in self._cors(methods).items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in self._cors().items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    # ---- routing ------------------------------------------------------------

    def _verb(self) -> str:
        prefix = "/postern/v0/"
        return self.path[len(prefix) :] if self.path.startswith(prefix) else ""

    def do_GET(self) -> None:
        verb = self._verb()
        if verb == "describe":
            self._send(200, DESCRIBE)
        elif verb == "status":
            self._send(200, self._status())
        else:
            self._send(404, error("not_found", "No such path."))

    def do_POST(self) -> None:
        verb = self._verb()
        if verb not in ("run", "stream"):
            self._send(404, error("not_found", "No such path."))
            return

        # Section 4.6's order, and this method is the whole of it:
        #
        #   1. level      2. entitlement      3. media type
        #   4. the request body                5. credentials
        #
        # Step 2 is a no-op here rather than absent: with no distributor
        # configured, entitlement is always `not_required`, so nothing ever
        # refuses at this row — see the README's "An agent that is free,
        # self-authored, or local has no distributor and skips all of
        # this." Step 1 can never fire either, since this runner always
        # declares Level 3; both stay in the method, in position, because
        # the order is the property being demonstrated, not just the rows
        # that happen to be reachable on this particular runner.
        required_level = 2 if verb == "run" else 3
        if LEVEL < required_level:
            self._send(
                501, error("not_implemented", f"This runner does not serve {verb}.")
            )
            return

        media_type = (
            (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        )
        if media_type != "application/json":
            self._send(
                400, error("bad_request", "Content-Type must be application/json.")
            )
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, error("bad_request", "Body is not JSON."))
            return

        inputs = payload.get("inputs") if isinstance(payload, dict) else None
        if not isinstance(inputs, dict) or "segment" not in inputs:
            self._send(400, error("bad_request", "Missing required input 'segment'."))
            return

        invalid = validation_failure(inputs)
        if invalid is not None:
            self._send(400, error("bad_request", invalid))
            return

        missing = missing_credentials()
        if missing:
            # SHOULD, section 4.6: name the variables in `detail.missing`,
            # the same array `status.credentials.missing` reports, rather
            # than leaving `message` as the only machine-readable copy.
            self._send(
                424,
                error(
                    "missing_credential",
                    f"{', '.join(missing)} not set.",
                    detail={"missing": missing},
                ),
            )
            return

        if verb == "run":
            self._send(200, self._run_response())
        else:
            self._stream()

    # ---- payloads -------------------------------------------------------

    def _status(self) -> dict[str, Any]:
        missing = missing_credentials()
        return {
            "postern": "0.1",
            "level": LEVEL,
            "state": "ready",
            "agent": {
                "id": DESCRIBE["agent"]["id"],
                "version": DESCRIBE["agent"]["version"],
            },
            "entitlement": {"state": "not_required"},
            "credentials": {"satisfied": not missing, "missing": missing},
            "limits": {"max_run_seconds": 900, "max_concurrent_runs": 1},
        }

    def _run_response(self) -> dict[str, Any]:
        self.server.runs += 1  # type: ignore[attr-defined]
        return {
            "postern": "0.1",
            "run_id": f"01JD8XW2Q{self.server.runs}",  # type: ignore[attr-defined]
            "output": {"type": "text", "value": OUTPUT_VALUE},
            "usage": {"input_tokens": 4210, "output_tokens": 918, "cost_usd": 0.001182},
        }

    def _stream(self) -> None:
        # Built before `start` rather than at `done`, so the run_id `start`
        # announces is the one `done` reports (section 4.3) — they read the
        # same response because there is only one.
        response = self._run_response()
        events: list[tuple[str, Any]] = [("start", {"run_id": response["run_id"]})]
        events.append(("step", {"name": "research", "status": "started"}))
        events.extend(("delta", {"text": chunk}) for chunk in DELTAS)
        events.append(("done", response))

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        for key, value in self._cors().items():
            self.send_header(key, value)
        self.end_headers()
        for name, payload in events:
            chunk = f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")
            self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii") + chunk + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.runs = 0  # type: ignore[attr-defined]
    print(f"{DESCRIBE['agent']['id']} · Level {LEVEL} · http://127.0.0.1:{port}")
    missing = missing_credentials()
    if missing:
        print(f"{', '.join(missing)} not set — run/stream will answer 424 until it is.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
