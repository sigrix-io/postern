"""A conformant runner, and a switch for each way of not being one.

The point of this file is the thing a conformance checker is most likely
to be wrong about: reporting a clean sweep while seeing nothing. Every
check in the tool is written against a specification and passes against
the one real implementation, and neither of those facts distinguishes a
check that works from a check that always returns PASS.

So the baseline here is deliberately conformant, and each `Fault` breaks
exactly one rule. A test asserts the matching check goes from PASS to FAIL
when the fault is applied — which is the only evidence that the check was
ever looking.
"""

from __future__ import annotations

import contextlib
import enum
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

ALLOWED_ORIGIN = "https://app.example.com"

# A one-pixel PNG, base64. Small on purpose: the point is the type.
BYTES_OUTPUT_VALUE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


class Fault(enum.Enum):
    """One broken rule each, named for what it breaks."""

    WILDCARD_CORS = "ships Access-Control-Allow-Origin: * by default (§2.3)"
    NULL_ORIGIN_ALLOWED = "treats Origin: null as an allowed origin (§2.3)"
    NO_RUN_PREFLIGHT = "does not answer OPTIONS on run (§2.3)"
    NO_VARY = "omits Vary: Origin (§2.3)"
    PARSES_TEXT_PLAIN = "executes a run body labelled text/plain (§2.3)"
    RUNS_ABOVE_LEVEL = "declares Level 1 and answers run anyway (§3)"
    STREAM_DEGRADES = "declares Level 2 and answers stream with 200 (§3, §4.3)"
    NOT_IMPLEMENTED_AT_LEVEL = "declares Level 3 and answers stream with 501 (§3)"
    ERROR_SIBLING = "puts a sibling beside `error` in the envelope (§2.1)"
    MISCODED_ERROR = "sends `bad_request` on a 500 (§2.1)"
    DISTRIBUTOR_CODE = "sends the distributor-only `withdrawn` (§2.1)"
    NO_404 = "answers 200 on a path it does not implement (§2.1)"
    CREDENTIAL_VALUE = "puts a credential value in describe (§4.1.3)"
    WRITE_TOOLS_NOT_SUBSET = "declares a write_tool absent from tools (§4.1.2)"
    AGENT_ID_MISMATCH = "names a different agent in describe and status (§2.2)"
    STALE_NOT_REQUIRED = "carries checked_at under not_required (§4.4)"
    IDEMPOTENT_WITHOUT_HEADER = "declares idempotent_retry, preflight omits the header (§2.3)"
    NO_START_EVENT = "streams without a leading `start` (§4.3)"
    DELTAS_DISAGREE = "streams deltas that do not concatenate to output.value (§4.3)"
    TWO_TERMINALS = "streams both `done` and `error` (§4.3)"
    LATENCY_ON_STARTED = "reports latency_ms on a started step (§4.3)"
    DUPLICATE_RUN_ID = "reuses one run_id across two runs (§4.2)"
    CREDENTIAL_BEFORE_REQUEST = (
        "answers missing_credential to a request that is also malformed (§4.6)"
    )
    STATUS_IN_RUN_BODY = "puts a `status` field in the run response body (§4.2)"
    VALIDATES_BEFORE_ENTITLEMENT = (
        "answers bad_request to a malformed request while its entitlement "
        "is revoked (§4.6 step 2)"
    )
    STREAM_NOT_ROUTED = "declares Level 3 and answers stream with 404 (§3)"
    EXAMPLE_ON_BYTES_OUTPUT = "declares an output example for a bytes output (§4.1.4)"
    DELTAS_ON_BYTES_RUN = "streams base64 deltas on a bytes run (§4.1.4)"
    IGNORES_DECLARED_VALIDATION = (
        "checks that a required input is present and applies none of the "
        "validation it declares (§4.2)"
    )
    WILDCARD_TO_KNOWN_ORIGIN = (
        "answers a configured origin with Access-Control-Allow-Origin: * "
        "while refusing a stranger correctly (§2.3)"
    )
    WILDCARD_ON_GETS = (
        "ships Access-Control-Allow-Origin: * on describe and status, so any "
        "page can read them (§2.3)"
    )
    RUNS_WITHOUT_EVER_CHECKING = (
        "reports unknown with no checked_at and runs the agent anyway (§5.7.3)"
    )
    RERUNS_AN_IDENTICAL_REPEAT = (
        "re-runs the agent on a repeat carrying the same inputs under a key "
        "it already answered (§4.2)"
    )
    REPLAYS_A_MISMATCHED_KEY = (
        "replays the first result for a reused Idempotency-Key carrying "
        "different inputs (§4.2)"
    )
    STREAM_PREFLIGHT_OMITS_CONTENT_TYPE = (
        "admits Content-Type on run's preflight and not on stream's (§2.3)"
    )
    SECRET_SHAPE_OUTSIDE_CREDENTIALS = (
        "puts a key-shaped string in describe outside the credentials block "
        "(§4.1.3)"
    )
    STREAM_RUN_ID_DISAGREES = (
        "streams a start whose run_id is not the one done reports (§4.3)"
    )
    RUNS_WITHOUT_ITS_CREDENTIALS = (
        "reports a declared credential as unset and runs the agent anyway "
        "(§4.6 step 5)"
    )

    def __str__(self) -> str:  # pragma: no cover - readable test ids
        return self.name.lower()


_DESCRIBE: dict[str, Any] = {
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
_DELTAS = ["## Positioning brief\n", "\nThe mid-market segment ", "is underserved."]


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": None}}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "fake-postern/0.1"

    # Silences the per-request line; the tests read the checker's report,
    # not this server's log.
    def log_message(self, *args: Any) -> None:  # pragma: no cover
        pass

    # ---- helpers -------------------------------------------------------

    @property
    def faults(self) -> set[Fault]:
        return self.server.faults  # type: ignore[attr-defined]

    @property
    def level(self) -> int:
        return self.server.level  # type: ignore[attr-defined]

    def _cors(self, methods: str, verb: str = "") -> dict[str, str]:
        origin = self.headers.get("Origin")
        headers: dict[str, str] = {}

        if Fault.WILDCARD_CORS in self.faults:
            headers["Access-Control-Allow-Origin"] = "*"
        elif Fault.WILDCARD_ON_GETS in self.faults and self.command == "GET":
            # Narrower than WILDCARD_CORS on purpose: `run` and `stream`
            # behave perfectly, so the probe that only ever asked `run`'s
            # preflight saw nothing. What leaks is what the agent *is* and
            # what it holds, to every page the user visits.
            headers["Access-Control-Allow-Origin"] = "*"
        elif origin == "null" and Fault.NULL_ORIGIN_ALLOWED in self.faults:
            headers["Access-Control-Allow-Origin"] = "null"
        elif origin == ALLOWED_ORIGIN and Fault.WILDCARD_TO_KNOWN_ORIGIN in self.faults:
            # Correct to a stranger (no header at all), wildcard to the one
            # origin it was configured for. Invisible to every stranger-based
            # probe, which is why the actual-response check is the only thing
            # that can see it -- and why it accepting `*` made that check
            # unable to fail.
            headers["Access-Control-Allow-Origin"] = "*"
        elif origin == ALLOWED_ORIGIN:
            headers["Access-Control-Allow-Origin"] = origin

        if headers and Fault.NO_VARY not in self.faults:
            headers["Vary"] = "Origin"
        if methods:
            headers["Access-Control-Allow-Methods"] = methods
            # Narrower than dropping it everywhere, on the same reasoning as
            # WILDCARD_ON_GETS: `run`'s preflight is perfect, so a probe that
            # only ever asked `run` saw nothing -- while no browser could
            # reach `stream` at all, since it cannot send a header its
            # preflight did not admit.
            omit_content_type = (
                verb == "stream"
                and Fault.STREAM_PREFLIGHT_OMITS_CONTENT_TYPE in self.faults
            )
            allowed = "" if omit_content_type else "Content-Type"
            if (
                Fault.IDEMPOTENT_WITHOUT_HEADER not in self.faults
                and self.server.idempotent  # type: ignore[attr-defined]
            ):
                allowed = f"{allowed}, Idempotency-Key" if allowed else "Idempotency-Key"
            headers["Access-Control-Allow-Headers"] = allowed
        return headers

    def _send(
        self, status: int, payload: Any, *, extra: dict[str, str] | None = None
    ) -> None:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (self._cors("") | (extra or {})).items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _verb(self) -> str:
        prefix = "/postern/v0/"
        return self.path[len(prefix):] if self.path.startswith(prefix) else ""

    # ---- routing -------------------------------------------------------

    def do_OPTIONS(self) -> None:
        verb = self._verb()
        if verb == "run" and Fault.NO_RUN_PREFLIGHT in self.faults:
            self._send(405, _error("bad_request", "no preflight here."))
            return

        # A posture, not a fault. §2.3 asks a runner refusing an origin for a
        # 204 rather than an error status, but only as a SHOULD, so a 403
        # here is a permitted deviation and the checker may warn at most.
        if self.server.strict_origin and self.headers.get("Origin") != ALLOWED_ORIGIN:  # type: ignore[attr-defined]
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        methods = "GET, OPTIONS" if verb in ("describe", "status") else "POST, OPTIONS"
        self.send_response(204)
        for key, value in self._cors(methods, verb).items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        verb = self._verb()
        if verb == "status":
            self._send(200, self._status())
        elif verb == "describe":
            self._send(200, self._describe())
        elif Fault.NO_404 in self.faults:
            self._send(200, {"postern": "0.1"})
        else:
            self._send(404, _error("not_found", "No such path."))

    def do_POST(self) -> None:
        verb = self._verb()
        if verb not in ("run", "stream"):
            self._send(404, _error("not_found", "No such path."))
            return

        # A verb that was never wired up at all: the path 404s like any
        # other unknown one. Distinct from NOT_IMPLEMENTED_AT_LEVEL, which
        # routes `stream` and answers 501 from inside it.
        if verb == "stream" and Fault.STREAM_NOT_ROUTED in self.faults:
            self._send(404, _error("not_found", "No such path."))
            return

        required_level = 2 if verb == "run" else 3
        degrading = (
            verb == "run" and Fault.RUNS_ABOVE_LEVEL in self.faults
        ) or (verb == "stream" and Fault.STREAM_DEGRADES in self.faults)

        if self.level < required_level and not degrading:
            self._send(501, _error("not_implemented", f"This runner does not serve {verb}."))
            return

        if verb == "stream" and Fault.NOT_IMPLEMENTED_AT_LEVEL in self.faults:
            self._send(501, _error("not_implemented", "Not wired up."))
            return

        # §4.6 step 2, and the position is the whole point: above the body
        # read, so nothing about the request can be reached first. A revoked
        # runner answers this to every request, which is what makes a `400`
        # here wrong -- it would name something the caller could fix.
        #
        # The fault skips the gate rather than moving it. Moving it below the
        # validation would also break §4.6, but by then the runner has read a
        # body it was never entitled to read, so the two defects would arrive
        # together and the check could not say which it caught.
        if (
            self.server.revoked  # type: ignore[attr-defined]
            and Fault.VALIDATES_BEFORE_ENTITLEMENT not in self.faults
        ):
            self._send(403, _error("not_entitled", "This entitlement is revoked."))
            return

        if (
            self.server.never_checked  # type: ignore[attr-defined]
            and Fault.RUNS_WITHOUT_EVER_CHECKING not in self.faults
        ):
            # `unavailable`, not `not_entitled`: retrying may genuinely help
            # once the network returns, and no distributor has said no.
            self._send(503, _error("unavailable", "No entitlement check has completed."))
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        media_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if media_type != "application/json" and Fault.PARSES_TEXT_PLAIN not in self.faults:
            self._send(400, _error("bad_request", "Content-Type must be application/json."))
            return

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            # The refusal itself is correct — 400 for a body that is not
            # JSON — so these two faults change only the code travelling on
            # it. That is what lets them reach the envelope rules in
            # section 2.1 instead of tripping the status check in front.
            if Fault.MISCODED_ERROR in self.faults:
                self._send(400, _error("unavailable", "A code defined for 503."))
            elif Fault.DISTRIBUTOR_CODE in self.faults:
                self._send(400, _error("withdrawn", "A distributor's answer."))
            else:
                self._send(400, _error("bad_request", "Body is not JSON."))
            return

        inputs = payload.get("inputs") if isinstance(payload, dict) else None
        needs_segment = not self.server.requires_nothing  # type: ignore[attr-defined]
        if not isinstance(inputs, dict) or (needs_segment and "segment" not in inputs):
            # §4.6 orders the request check ahead of the environment check.
            # This fault reverses them: the runner reports its own missing
            # credential first, so a malformed request is answered 424.
            if Fault.CREDENTIAL_BEFORE_REQUEST in self.faults:
                self._send(
                    424,
                    _error("missing_credential", "OPENAI_API_KEY is not set."),
                )
                return
            body = _error("bad_request", "Missing required input 'segment'.")
            if Fault.ERROR_SIBLING in self.faults:
                body["trace_id"] = "abc123"
            self._send(400, body)
            return

        # §4.2's other half: a request failing a *declared* validation is
        # refused in the same sentence as one omitting a required input.
        # This runner declares `max_length` on `segment` and `options` on
        # `depth`, so it owes both.
        if Fault.IGNORES_DECLARED_VALIDATION not in self.faults:
            invalid = _validation_failure(inputs)
            if invalid is not None:
                self._send(400, _error("bad_request", invalid))
                return

        # §4.6 step 5, and the position is the point: after the request
        # checks above, so an incomplete environment cannot mask a
        # malformed request, and before the agent starts, so the client is
        # told the name of the variable to set rather than whatever the
        # agent fails with.
        #
        # The fault skips the gate rather than moving it, which is what
        # makes it the defect §4.6 obliges rather than a second ordering
        # bug: the runner reports the credential as unset in `status` and
        # runs the agent regardless.
        if (
            self.server.credentials_missing  # type: ignore[attr-defined]
            and Fault.RUNS_WITHOUT_ITS_CREDENTIALS not in self.faults
        ):
            self._send(424, _error("missing_credential", "OPENAI_API_KEY is not set."))
            return

        if verb == "run":
            self._answer_run(inputs)
        else:
            self._stream()

    def _answer_run(self, inputs: dict[str, Any]) -> None:
        """Serve `run`, honouring an Idempotency-Key where this runner declares one.

        Scoped to `run` because that is the only verb the checker sends a
        key on. Section 4.2 does define a replay's shape on `stream` — a
        `start` then a `done` — and a fake implementing a rule nothing
        exercises would be a second, unchecked implementation of it.
        """
        key = self.headers.get("Idempotency-Key")
        if not (key and self.server.idempotent):  # type: ignore[attr-defined]
            self._send(200, self._run_response())
            return

        answered = self.server.answered_keys  # type: ignore[attr-defined]
        remembered = answered.get(key)

        if remembered is not None:
            first_inputs, first_response = remembered
            if first_inputs != inputs and Fault.REPLAYS_A_MISMATCHED_KEY not in self.faults:
                self._send(
                    409,
                    _error(
                        "idempotency_conflict",
                        "That Idempotency-Key was already answered for "
                        "different inputs. Send a new key to run these.",
                    ),
                )
                return
            if Fault.RERUNS_AN_IDENTICAL_REPEAT in self.faults:
                # Honours the conflict refusal above and still re-runs every
                # identical repeat -- the promise the header exists to make,
                # broken while the rule protecting it is kept.
                fresh = self._run_response()
                answered[key] = (inputs, fresh)
                self._send(200, fresh)
                return
            # Same inputs: the replay section 4.2 requires. Under the fault,
            # a mismatch takes this branch too, which is the whole defect.
            self._send(200, first_response)
            return

        response = self._run_response()
        answered[key] = (inputs, response)
        self._send(200, response)

    # ---- payloads ------------------------------------------------------

    def _status(self) -> dict[str, Any]:
        entitlement: dict[str, Any] = {"state": "not_required"}
        if Fault.STALE_NOT_REQUIRED in self.faults:
            entitlement["checked_at"] = "2026-08-15T09:14:02Z"
            entitlement["stale_after_seconds"] = 60
        if self.server.never_checked:  # type: ignore[attr-defined]
            # §5.7.3: no check has ever completed, so there is no
            # `checked_at` and no grace to count from.
            entitlement = {"state": "unknown"}
        if self.server.revoked:  # type: ignore[attr-defined]
            # §5.7.4: a runner told `404` supplies both fields itself.
            entitlement = {
                "state": "revoked",
                "checked_at": "2026-09-02T09:00:00Z",
                "stale_after_seconds": 60,
            }

        agent_id = (
            "acme/a-different-crew"
            if Fault.AGENT_ID_MISMATCH in self.faults
            else _DESCRIBE["agent"]["id"]
        )
        return {
            "postern": "0.1",
            "level": self.level,
            "state": "ready",
            "agent": {"id": agent_id, "version": "1.3.0"},
            "entitlement": entitlement,
            **(
                {}
                # §4.4 makes the block OPTIONAL, and a runner omitting it is
                # the ordinary case rather than a broken one -- the posture
                # exists so the checker's answer to "cannot tell" is exercised
                # by something.
                if self.server.credentials_unreported  # type: ignore[attr-defined]
                else {
                    "credentials": (
                        {"satisfied": False, "missing": ["OPENAI_API_KEY"]}
                        if self.server.credentials_missing  # type: ignore[attr-defined]
                        else {"satisfied": True, "missing": []}
                    )
                }
            ),
            "limits": {"max_run_seconds": 900, "max_concurrent_runs": 1},
        }

    def _describe(self) -> dict[str, Any]:
        document = json.loads(json.dumps(_DESCRIBE))
        if self.server.requires_nothing:  # type: ignore[attr-defined]
            for declared in document["inputs"]:
                declared["required"] = False
        if self.server.returns_bytes:  # type: ignore[attr-defined]
            document["output"] = {"type": "bytes", "media_type": "image/png"}
            if Fault.EXAMPLE_ON_BYTES_OUTPUT in self.faults:
                # §4.1.4: `example` stays text-only. An inline artifact
                # would inflate a document every catalogue listing fetches.
                document["output"]["example"] = BYTES_OUTPUT_VALUE
        if self.server.idempotent:  # type: ignore[attr-defined]
            document["capabilities"]["idempotent_retry"] = True
        if Fault.CREDENTIAL_VALUE in self.faults:
            document["credentials"][0]["value"] = "sk-abcdefghijklmnopqrstuvwxyz012345"
        if Fault.SECRET_SHAPE_OUTSIDE_CREDENTIALS in self.faults:
            # §4.1.3 binds the whole response. The summary is where a key
            # most plausibly ends up by accident -- pasted in while writing
            # the listing copy -- and it is nowhere the narrow scan looks.
            document["agent"]["summary"] = (
                "Researches a market segment. Configured with "
                "sk-abcdefghijklmnopqrstuvwxyz012345."
            )
        if Fault.WRITE_TOOLS_NOT_SUBSET in self.faults:
            document["capabilities"]["write_tools"] = ["file_write", "wire_transfer"]
        return document

    def _run_response(self) -> dict[str, Any]:
        self.server.runs += 1  # type: ignore[attr-defined]
        run_id = (
            "01JD8XW2Q9"
            if Fault.DUPLICATE_RUN_ID in self.faults
            else f"01JD8XW2Q{self.server.runs}"  # type: ignore[attr-defined]
        )
        body: dict[str, Any] = {
            "postern": "0.1",
            "run_id": run_id,
            "output": (
                {"type": "bytes", "media_type": "image/png", "value": BYTES_OUTPUT_VALUE}
                if self.server.returns_bytes  # type: ignore[attr-defined]
                else {"type": "text", "value": OUTPUT_VALUE}
            ),
            "usage": {"input_tokens": 4210, "output_tokens": 918, "cost_usd": 0.001182},
        }
        if Fault.STATUS_IN_RUN_BODY in self.faults:
            # Schema-valid -- run-response.schema.json is open at its root --
            # and §4.2 describes its absence without a MUST NOT, so the
            # checker warns rather than failing.
            body["status"] = "ok"
        return body

    def _stream(self) -> None:
        events: list[tuple[str, Any]] = []

        # Built before `start` rather than at `done`, so the identifier
        # `start` announces is the one `done` reports (§4.3). It used to be
        # a literal here while `done` took one from the run counter, so the
        # two disagreed on every stream this runner served -- and the
        # baseline swept clean, because nothing compared them.
        response = self._run_response()
        run_id = response["run_id"]

        if Fault.NO_START_EVENT not in self.faults:
            announced = (
                "01JD8XW2Q-not-the-one-done-reports"
                if Fault.STREAM_RUN_ID_DISAGREES in self.faults
                else run_id
            )
            events.append(("start", {"run_id": announced}))

        events.append(
            (
                "step",
                {"name": "research", "status": "started"}
                | ({"latency_ms": 12} if Fault.LATENCY_ON_STARTED in self.faults else {}),
            )
        )

        if self.server.returns_bytes:  # type: ignore[attr-defined]
            # §4.1.4: a bytes run emits no delta at all. Progress rides on
            # `step`, which reports it without pretending to be the output.
            if Fault.DELTAS_ON_BYTES_RUN in self.faults:
                half = len(BYTES_OUTPUT_VALUE) // 2
                events.extend(
                    ("delta", {"text": chunk})
                    for chunk in (BYTES_OUTPUT_VALUE[:half], BYTES_OUTPUT_VALUE[half:])
                )
        else:
            deltas = list(_DELTAS)
            if Fault.DELTAS_DISAGREE in self.faults:
                deltas[-1] = "is thoroughly served."
            events.extend(("delta", {"text": chunk}) for chunk in deltas)
        events.append(("done", response))
        if Fault.TWO_TERMINALS in self.faults:
            events.append(("error", _error("agent_error", "and an error too.")))

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Transfer-Encoding", "chunked")
        for key, value in self._cors("").items():
            self.send_header(key, value)
        self.end_headers()

        for name, payload in events:
            chunk = f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")
            self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii") + chunk + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")


class RunCounter:
    """How many times the agent actually started, for the README's claim.

    `postern-conformance` says it does not run your agent unless you ask.
    That is a property of the checker, not of any rule it checks, so the
    only way to assert it is to count.
    """

    def __init__(self, server: Any) -> None:
        self._server = server

    @property
    def runs(self) -> int:
        return self._server.runs


def _validation_failure(inputs: dict[str, Any]) -> str | None:
    """The first declared constraint these inputs break, or None.

    Read off `_DESCRIBE` rather than restated: a fake enforcing a rule it
    does not publish would refuse requests the checker had every right to
    send, and the mismatch would read as a checker bug.
    """
    for declared in _DESCRIBE["inputs"]:
        key = declared["key"]
        if key not in inputs:
            continue
        value = inputs[key]
        rules = declared.get("validation") or {}

        options = rules.get("options")
        if isinstance(options, list) and value not in options:
            return f"'{key}' must be one of {', '.join(options)}."

        max_length = rules.get("max_length")
        if isinstance(max_length, int) and isinstance(value, str) and len(value) > max_length:
            return f"'{key}' is longer than {max_length} characters."
    return None


@contextlib.contextmanager
def fake_runner(
    *faults: Fault,
    level: int = 3,
    idempotent: bool = False,
    revoked: bool = False,
    never_checked: bool = False,
    strict_origin: bool = False,
    requires_nothing: bool = False,
    returns_bytes: bool = False,
    credentials_missing: bool = False,
    credentials_unreported: bool = False,
) -> Iterator[tuple[str, "RunCounter"]]:
    """Serve a runner with the given faults; yields its origin and run counter.

    `revoked` puts the runner in §5.7.4's refused state, which is a posture
    rather than a fault: a revoked runner that refuses correctly is fully
    conformant, and the baseline asserts exactly that. It is here because
    the checker's whole §5.7.4 branch was unreachable without it — the
    reason the ordering defect in #108 shipped.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.faults = set(faults)  # type: ignore[attr-defined]
    server.level = level  # type: ignore[attr-defined]
    server.idempotent = idempotent  # type: ignore[attr-defined]
    server.revoked = revoked  # type: ignore[attr-defined]
    server.never_checked = never_checked  # type: ignore[attr-defined]
    server.strict_origin = strict_origin  # type: ignore[attr-defined]
    server.requires_nothing = requires_nothing  # type: ignore[attr-defined]
    server.returns_bytes = returns_bytes  # type: ignore[attr-defined]
    server.credentials_missing = credentials_missing  # type: ignore[attr-defined]
    server.credentials_unreported = credentials_unreported  # type: ignore[attr-defined]
    server.runs = 0  # type: ignore[attr-defined]
    # Idempotency-Key -> (the inputs it was first answered for, that answer).
    server.answered_keys = {}  # type: ignore[attr-defined]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", RunCounter(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
