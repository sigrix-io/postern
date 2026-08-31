"""SPEC.md sections 4.2 and 4.3 — `run` and `stream`.

Split by what a check costs. Section 4.1.2 establishes that a run may
invoke tools which spend money and mutate state outside the workspace, and
section 4.5 that an abort is not a rollback — so a conformance checker that
ran an agent to find out whether it conforms would be charging the person
running it for the answer, and would have done so before they could read
this.

So the default is the set of rules a runner must apply *before* the agent
starts: the validation refusals of section 4.2, and the entitlement
refusals of section 5.7.4. Each is a request the runner is obliged to
reject, and a rejected request executes nothing.

`--execute` opts into the rest, which cannot be checked any other way: the
response body's shape, the stream's framing, the `delta` concatenation
invariant, `run_id` uniqueness, and the refusal a reused `Idempotency-Key`
carrying different `inputs` owes. That last one executes nothing itself —
it reuses the key the uniqueness check bound — but it needs a real run to
have bound one.
"""

from __future__ import annotations

import json
from typing import Any

from ..context import Context
from ..probe import Response, Runner
from ..report import Check, failed, passed, skipped, warned
from . import check_schema, error_code, error_envelope_checks, stream_event_errors

RUN = "4.2"
STREAM = "4.3"

# A run may legitimately take minutes. `status.limits.max_run_seconds` is
# the runner's own bound where it declares one, and this is the fallback
# for a runner that declares none.
DEFAULT_RUN_TIMEOUT_SECONDS = 300.0

# The key the second attempt travels under, named here because two checks
# need the same string: one spends it to force a second execution, and the
# other presents it again to see whether the runner remembers what it was
# answered for.
SECOND_ATTEMPT_KEY = "postern-conformance-second-attempt"


def run(runner: Runner, context: Context) -> list[Check]:
    level = context.level
    if level is None or level < 2:
        return []

    checks: list[Check] = []
    checks.extend(_refuses_a_malformed_body(runner))
    checks.extend(_refuses_a_missing_required_input(runner, context))
    checks.extend(_entitlement_refusals(runner, context))

    if not context.execute:
        checks.append(
            skipped(
                RUN,
                "the agent runs and answers",
                "not asked to execute. A run may invoke tools that spend money "
                "and mutate state outside the workspace (§4.1.2), and an abort "
                "is not a rollback (§4.5) — so the checks that need a real run "
                "are opt-in. Pass --execute to include them.",
            )
        )
        return checks

    if not context.runs_are_free:
        checks.append(
            skipped(
                RUN,
                "the agent runs and answers",
                f"the runner's entitlement state is "
                f"`{context.entitlement_state}`, so a run is refused rather "
                "than executed. The refusal itself is checked above.",
            )
        )
        return checks

    body = context.a_valid_body()
    if body is None:
        checks.append(
            skipped(
                RUN,
                "the agent runs and answers",
                "could not build a request satisfying every declared input "
                "from `describe` alone — an input carries a `pattern` this "
                "checker will not try to solve, or a declaration it cannot "
                "read. Guessing produces a `bad_request` that reads as the "
                "runner's fault.",
            )
        )
        return checks

    checks.extend(_executes(runner, context, body))
    if context.level == 3:
        checks.extend(_streams(runner, context, body))
    return checks


def _timeout(context: Context) -> float:
    limits = (context.status or {}).get("limits")
    if isinstance(limits, dict):
        declared = limits.get("max_run_seconds")
        if isinstance(declared, int) and declared > 0:
            # Past the runner's own bound it owes a 504 rather than a
            # result, so waiting longer than it buys nothing.
            return float(declared) + 10.0
    return DEFAULT_RUN_TIMEOUT_SECONDS


def _refuses_a_malformed_body(runner: Runner) -> list[Check]:
    """A body that is not JSON is a `bad_request`, and never reaches the agent."""
    response = runner.request(
        "POST",
        "run",
        body=b"{this is not json",
        headers={"Content-Type": "application/json", "Content-Length": "17"},
    )
    title = "run refuses a malformed body"
    if response.status == 400:
        checks = [passed(RUN, title)]
        checks.extend(
            error_envelope_checks(
                response, context="run with a malformed body", expected_code="bad_request"
            )
        )
        return checks
    return [
        failed(
            RUN,
            title,
            f"answered {response.status} to a body that is not JSON.",
        )
    ]


def _refuses_a_missing_required_input(runner: Runner, context: Context) -> list[Check]:
    """A request omitting a `required` input MUST be rejected with `bad_request`.

    And the runner SHOULD name the offending key in `message` — a SHOULD,
    so its absence warns. It is worth asking about because the client that
    reads this message is usually a person: a refusal that does not say
    which field was missing sends them back to `describe` to diff it by
    hand against what they sent.
    """
    missing = context.required_input_keys
    if not missing:
        return [
            skipped(
                RUN,
                "run refuses a missing required input",
                "the agent declares no required input, so there is no request "
                "the runner is obliged to reject on these grounds.",
            )
        ]

    response = runner.post_json("run", {"inputs": {}})
    title = "run refuses a missing required input"

    # A request that is missing a required input *and* arrives at a runner
    # whose environment is missing a credential has two correct refusals
    # available, and the specification orders neither: section 4.2 requires
    # `bad_request` for the input, section 2.1 defines `missing_credential`
    # for the environment, and both are true of this request. So a runner
    # answering 424 here has not been caught breaking a rule — it has been
    # asked a question with two right answers, and this check cannot tell
    # which rule it applies until the environment is complete.
    if response.status == 424 and error_code(response) == "missing_credential":
        return [
            skipped(
                RUN,
                title,
                "the runner answered 424 `missing_credential`"
                + (
                    " (" + ", ".join(context.missing_credentials) + ")"
                    if context.missing_credentials
                    else ""
                )
                + ". Both refusals are correct for this request and the "
                "specification does not order them, so this rule cannot be "
                "isolated until the runner's environment carries the "
                "credentials `describe` declares.",
            )
        ]

    if response.status != 400:
        return [
            failed(
                RUN,
                title,
                f"answered {response.status} to a request omitting "
                + ", ".join(repr(key) for key in missing)
                + ", each declared `required` by `describe`.",
            )
        ]

    checks: list[Check] = [passed(RUN, title)]
    checks.extend(
        error_envelope_checks(
            response, context="run with a missing input", expected_code="bad_request"
        )
    )

    message = _message(response)
    if message and not any(key in message for key in missing):
        checks.append(
            warned(
                RUN,
                "the refusal names the offending key",
                f"message was {message[:120]!r} and names none of "
                + ", ".join(repr(key) for key in missing)
                + ".",
            )
        )
    elif message:
        checks.append(passed(RUN, "the refusal names the offending key"))

    return checks


def _entitlement_refusals(runner: Runner, context: Context) -> list[Check]:
    """Section 5.7.4 — what `run` and `stream` owe in each entitlement state.

    Checked without executing anything, because every state this covers is
    one where the runner must refuse. The rule underneath the table is the
    one to hold it to: unreachable answers `unavailable`, refused answers
    `not_entitled`.
    """
    state = context.entitlement_state
    if state != "revoked":
        return []

    checks: list[Check] = []
    for verb in ("run", "stream"):
        if context.level is not None and context.level < (2 if verb == "run" else 3):
            continue
        response = _post(runner, verb, {"inputs": {}}, context)
        title = f"{verb} refuses a revoked entitlement"
        if response.status == 403:
            checks.append(passed("5.7.4", title))
            checks.extend(
                error_envelope_checks(
                    response,
                    context=f"{verb} with a revoked entitlement",
                    expected_code="not_entitled",
                )
            )
        else:
            checks.append(
                failed(
                    "5.7.4",
                    title,
                    f"answered {response.status}. `status` reports the "
                    "entitlement as `revoked`, and a revoked entitlement is a "
                    "refusal the runner has been told about — 403 "
                    "`not_entitled`, the one place that code is correct. "
                    "`unavailable` would invite a retry that cannot succeed.",
                )
            )
    return checks


def _executes(runner: Runner, context: Context, body: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    timeout = _timeout(context)
    response = runner.post_json("run", body, timeout=timeout)

    if response.status != 200:
        checks.append(
            failed(RUN, "the agent runs and answers", f"answered {response.status}.")
        )
        checks.extend(error_envelope_checks(response, context="run"))
        return checks

    checks.append(passed(RUN, "the agent runs and answers"))

    payload = response.json
    if not isinstance(payload, dict):
        checks.append(
            failed(RUN, "run body is a JSON object", f"{response.text[:200]!r}")
        )
        return checks

    checks.append(
        check_schema(RUN, "run matches its schema", "run-response.schema.json", payload)
    )
    checks.extend(_no_status_field(payload))
    checks.extend(_output_type_agrees(payload, context, where="run"))

    first_run_id = payload.get("run_id")
    unique, bound_key = _run_id_is_unique(runner, context, body, first_run_id, timeout)
    checks.extend(unique)
    checks.extend(_a_reused_key_is_refused(runner, context, bound_key, timeout))
    return checks


def _no_status_field(payload: dict[str, Any]) -> list[Check]:
    """Section 4.2 — the response body carries no `status` field.

    Not pedantry about an unused key. Every failure routes through the
    error envelope on a non-2xx, so a `run` body exists only where the run
    succeeded, and a field whose one legal value is `ok` repeats what the
    status line already said. The section says at length why it is not
    withheld as a place to grow one.
    """
    if "status" in payload:
        return [
            failed(
                RUN,
                "the run response carries no status field",
                f"the body carries `status`: {payload['status']!r}. A `run` "
                "body exists only where the run succeeded.",
            )
        ]
    return [passed(RUN, "the run response carries no status field")]


def _output_type_agrees(
    payload: dict[str, Any], context: Context, *, where: str
) -> list[Check]:
    """Section 4.1.4 — `run` carries the same `type` `describe` declared."""
    declared = (context.describe or {}).get("output")
    produced = payload.get("output")
    if not isinstance(declared, dict) or not isinstance(produced, dict):
        return []

    declared_type, produced_type = declared.get("type"), produced.get("type")
    if not isinstance(declared_type, str) or not isinstance(produced_type, str):
        return []

    title = f"{where} output type matches describe"
    if declared_type != produced_type:
        return [
            failed(
                "4.1.4",
                title,
                f"`describe` declares `{declared_type}` and the run returned "
                f"`{produced_type}`. `type` is what says how to read `value`, "
                "so a client that trusted `describe` has misread a known.",
            )
        ]
    return [passed("4.1.4", title)]


def _run_id_is_unique(
    runner: Runner,
    context: Context,
    body: dict[str, Any],
    first_run_id: Any,
    timeout: float,
) -> tuple[list[Check], str | None]:
    """`run_id` MUST be unique per execution within the runner's lifetime.

    Needs a second execution, which is a second agent invocation and a
    second bill. Where the runner declares `idempotent_retry`, the second
    request is sent with a fresh `Idempotency-Key` — a client wanting a
    genuine second attempt asks with a new key, which is what it would have
    done with no header at all.

    A fresh key is also what keeps this check honest about the rule it
    asserts. Uniqueness is per execution, so a replayed answer repeating the
    first run's identifier is conformant (section 4.2); reusing one key here
    would plant exactly that replay and read it as a duplicate.

    Returns its checks and the key this execution bound, so the conflict
    check below can present it again without buying a third run. The key is
    reported only for a `200`: section 4.2 binds a key to an execution, and
    a request refused before the agent ran binds none.
    """
    if not isinstance(first_run_id, str):
        return [], None

    key = SECOND_ATTEMPT_KEY if context.declares_idempotent_retry else None
    second = runner.post_json(
        "run",
        body,
        timeout=timeout,
        extra_headers={"Idempotency-Key": key} if key else None,
    )
    if second.status != 200:
        return [
            skipped(
                RUN,
                "run_id is unique across two runs",
                f"the second run answered {second.status}, so there is no "
                "second identifier to compare.",
            )
        ], None

    payload = second.json
    second_run_id = payload.get("run_id") if isinstance(payload, dict) else None
    if not isinstance(second_run_id, str):
        return [], key

    if first_run_id == second_run_id:
        return [
            failed(
                RUN,
                "run_id is unique across two runs",
                f"two separate executions both reported {first_run_id!r}. It "
                "must be unique per execution within the runner's lifetime, and "
                "is what correlates a result with the runner's logs.",
            )
        ], key
    return [passed(RUN, "run_id is unique across two runs")], key


def _a_reused_key_is_refused(
    runner: Runner,
    context: Context,
    bound_key: str | None,
    timeout: float,
) -> list[Check]:
    """Section 4.2 — a key already answered, presented with different `inputs`.

    A runner declaring `capabilities.idempotent_retry` binds a key to the
    inputs it was first answered for, and MUST refuse a repeat carrying
    different ones with `409` `idempotency_conflict` rather than replaying
    the first execution.

    The rule exists because the other reading fails silently. Answering
    from the first execution hands back a result computed for inputs the
    caller never sent — at `200`, in a valid envelope, with neither side
    able to detect it — so nothing but a check like this one can tell a
    runner that honours the rule from one that does not.

    Costs no execution of its own: it reuses the key the second attempt
    above already bound, and a conformant runner refuses this request
    without running the agent. A runner that runs it anyway has spent the
    money and demonstrated the defect in the same breath, which is the
    honest price of asking.
    """
    title = "a reused key with different inputs is refused"

    if not context.declares_idempotent_retry:
        return [
            skipped(
                RUN,
                title,
                "the runner does not declare `capabilities.idempotent_retry`, "
                "so it has made no promise about a key and binds none.",
            )
        ]

    if bound_key is None:
        return [
            skipped(
                RUN,
                title,
                "no second run answered 200 under a key, so there is no "
                "answered key to present again.",
            )
        ]

    other = context.a_different_valid_body()
    if other is None:
        return [
            skipped(
                RUN,
                title,
                "could not derive a second valid body differing from the "
                "first — every required input admits one derivable value, so "
                "there is no different request to send under the same key.",
            )
        ]

    response = runner.post_json(
        "run", other, timeout=timeout, extra_headers={"Idempotency-Key": bound_key}
    )

    if response.status != 409:
        detail = (
            "answered 200 to a key it had already answered for different "
            "inputs. Whether it replayed the first result or ran the agent "
            "again, a caller cannot tell: both are a 200 carrying a run the "
            "request did not ask for."
            if response.status == 200
            else f"answered {response.status} to a key it had already answered "
            "for different inputs."
        )
        return [failed(RUN, title, detail)]

    checks: list[Check] = [passed(RUN, title)]
    checks.extend(
        error_envelope_checks(
            response,
            context="run reusing an idempotency key",
            expected_code="idempotency_conflict",
        )
    )
    return checks


def _streams(runner: Runner, context: Context, body: dict[str, Any]) -> list[Check]:
    """Section 4.3 — the SSE framing rules, which no schema can reach."""
    checks: list[Check] = []
    response, events = runner.stream(body, timeout=_timeout(context))

    if response.status != 200:
        checks.append(
            failed(STREAM, "stream answers", f"answered {response.status}.")
        )
        checks.extend(error_envelope_checks(response, context="stream"))
        return checks

    if response.media_type == "text/event-stream":
        checks.append(passed(STREAM, "stream is served as text/event-stream"))
    else:
        checks.append(
            failed(
                STREAM,
                "stream is served as text/event-stream",
                f"Content-Type was {response.header('content-type')!r}.",
            )
        )

    if not events:
        checks.append(
            failed(STREAM, "stream carries events", "the stream carried no events.")
        )
        return checks

    names = [name for name, _ in events]

    if names[0] == "start":
        checks.append(passed(STREAM, "start is first"))
    else:
        checks.append(
            failed(
                STREAM,
                "start is first",
                f"the first event was {names[0]!r}. `start` carries the "
                "`run_id` the `done` payload repeats, which is how a client "
                "correlates a stream with its result.",
            )
        )

    checks.extend(_terminates_once(names))
    checks.extend(_payloads(events, context))
    checks.extend(_deltas_concatenate(events))
    return checks


def _terminates_once(names: list[str]) -> list[Check]:
    """A stream MUST end with exactly one `done` or one `error`."""
    terminals = [name for name in names if name in ("done", "error")]
    title = "the stream ends with exactly one done or error"

    if len(terminals) == 1 and names[-1] in ("done", "error"):
        return [passed("4.3", title, f"ended with `{names[-1]}`.")]

    if not terminals:
        return [
            failed(
                "4.3",
                title,
                f"the stream ended after {names[-1]!r} with neither. A client "
                "cannot tell a finished run from a dropped connection.",
            )
        ]

    if len(terminals) > 1:
        return [
            failed(
                "4.3",
                title,
                f"{len(terminals)} terminal events: {', '.join(terminals)}.",
            )
        ]

    return [
        failed(
            "4.3",
            title,
            f"`{terminals[0]}` was not last — {names[-1]!r} followed it.",
        )
    ]


def _payloads(events: list[tuple[str, str]], context: Context) -> list[Check]:
    """Validate each event's payload against the schema for its own name."""
    checks: list[Check] = []
    problems: list[str] = []
    unnamed = 0

    for index, (name, data) in enumerate(events):
        if name == "message":
            unnamed += 1
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            problems.append(f"event {index} (`{name}`): data is not JSON")
            continue

        if name == "done":
            for error in _schema_problems("run-response.schema.json", payload):
                problems.append(f"event {index} (`done`): {error}")
            checks.extend(_output_type_agrees(payload, context, where="stream done"))
        elif name == "error":
            for error in _schema_problems("error.schema.json", payload):
                problems.append(f"event {index} (`error`): {error}")
        else:
            for error in stream_event_errors(name, payload):
                problems.append(f"event {index} (`{name}`): {error}")

    if unnamed:
        checks.append(
            failed(
                "4.3",
                "every event is named",
                f"{unnamed} event(s) arrived with no `event:` line. Events are "
                "Server-Sent Events with a named `event:` and a JSON `data:` "
                "payload; an unnamed one reaches a client as `message`, which "
                "this specification defines nothing for.",
            )
        )

    if problems:
        checks.append(failed("4.3", "event payloads match their schemas", "\n".join(problems)))
    else:
        checks.append(passed("4.3", "event payloads match their schemas"))

    return checks


def _schema_problems(schema_filename: str, payload: Any) -> list[str]:
    from . import schema_errors

    return schema_errors(schema_filename, payload)


def _deltas_concatenate(events: list[tuple[str, str]]) -> list[Check]:
    """Section 4.3's one rule that spans events.

        If any `delta` is emitted, concatenating every `delta.text` in order
        MUST equal the final `output.value`.

    No schema can reach it — it is a relation between a sequence of events
    and a field in a later one — which is why it lives in the prose and why
    a checker is the only thing that can hold a runner to it.
    """
    deltas = [data for name, data in events if name == "delta"]
    title = "deltas concatenate to the final output"

    if not deltas:
        return [
            passed(
                "4.3",
                title,
                "no `delta` emitted, which is permitted: a runner that cannot "
                "produce incremental text emits none, and one producing a "
                "`bytes` output emits none by rule.",
            )
        ]

    done = next((data for name, data in events if name == "done"), None)
    if done is None:
        return [
            skipped(
                "4.3",
                title,
                "deltas were emitted and no `done` arrived to compare them to.",
            )
        ]

    try:
        accumulated = "".join(json.loads(chunk).get("text", "") for chunk in deltas)
        final = json.loads(done).get("output", {}).get("value")
    except (json.JSONDecodeError, AttributeError, TypeError):
        return [skipped("4.3", title, "a payload could not be read as JSON.")]

    if not isinstance(final, str):
        return [skipped("4.3", title, "`done` carried no string `output.value`.")]

    if accumulated == final:
        return [passed("4.3", title, f"{len(deltas)} deltas, {len(final)} characters.")]

    return [
        failed(
            "4.3",
            title,
            f"{len(deltas)} deltas concatenate to {len(accumulated)} characters "
            f"and `done` carries {len(final)}. A client that rendered the "
            "deltas and then read a different `output.value` has been shown "
            "two answers.",
        )
    ]


def _message(response: Response) -> str | None:
    body = response.json
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        message = body["error"].get("message")
        return message if isinstance(message, str) else None
    return None


def _post(
    runner: Runner, verb: str, body: dict[str, Any], context: Context
) -> Response:
    if verb == "stream":
        response, _events = runner.stream(body, timeout=runner.timeout)
        return response
    return runner.post_json(verb, body)
