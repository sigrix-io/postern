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

import dataclasses
import json
from typing import Any

from ..context import Context
from ..probe import TERMINAL_EVENT_NAMES, Response, Runner
from ..report import Check, failed, passed, skipped, warned
from . import check_schema, error_code, error_envelope_checks, stream_event_errors

RUN = "4.2"
STREAM = "4.3"
REFUSAL_ORDER = "4.6"

# A run may legitimately take minutes. `status.limits.max_run_seconds` is
# the runner's own bound where it declares one, and this is the fallback
# for a runner that declares none.
DEFAULT_RUN_TIMEOUT_SECONDS = 300.0

# The key the second attempt travels under, named here because two checks
# need the same string: one spends it to force a second execution, and the
# other presents it again to see whether the runner remembers what it was
# answered for.
SECOND_ATTEMPT_KEY = "postern-conformance-second-attempt"


@dataclasses.dataclass(frozen=True)
class BoundAttempt:
    """What the second execution bound, for the two checks that reuse it.

    `key` is the `Idempotency-Key` that execution was answered under, and
    `run_id` the identifier it answered with. They are separate because the
    checks need different halves: the conflict check presents the key with
    other inputs and never looks at the identifier, while the replay check
    compares the identifier and would be meaningless without it. A runner
    that answered `200` with no string `run_id` binds a usable key and no
    comparable identifier, which is why `run_id` is optional.
    """

    key: str
    run_id: str | None


def run(runner: Runner, context: Context) -> list[Check]:
    level = context.level
    if level is None or level < 2:
        return []

    checks: list[Check] = []
    checks.extend(_refuses_a_malformed_body(runner, context))
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

    checks.extend(_refuses_a_declared_validation(runner, context))
    checks.extend(_refuses_without_its_credentials(runner, context, body))

    if context.reports_a_missing_credential:
        checks.append(
            skipped(
                RUN,
                "the agent runs and answers",
                "`status` reports "
                + _credential_names(context)
                + " unset, and §4.6 step 5 has a conforming runner refuse a "
                "run rather than start the agent without it — so there is no "
                "result to measure here whichever way this one answered. "
                "Whether it refused is checked above. Set the credential and "
                "run this again to reach the rules that need a real run.",
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


def entitlement_preempted(response: Response, context: Context) -> str | None:
    """Why a request-level probe stands down here, or `None` to judge it.

    §4.6 puts the entitlement refusal at step 2, ahead of the media type,
    the inputs and the environment. So on a runner whose entitlement is not
    in force, a probe written for one of those steps earns the entitlement
    refusal instead of the one it was checking — and reporting that as a
    failure would be reporting the runner for obeying the order.

    Two things make this a stand-down rather than a hole.

    It is keyed on the *answer*, not on the state: a runner reporting
    `revoked` that nonetheless answers `400` to a malformed body is still
    judged, and still passes. Only a runner that actually preempts skips.

    And the answer is corroborated against `status` before it is believed.
    An entitled runner answering `not_entitled` to a body it simply did not
    like is a real defect, and one of the more attractive ones to hide
    behind — so a runner cannot skip its way out of §4.2 by claiming a
    refusal its own `status` does not support.
    """
    state = context.entitlement_state
    if state not in ("revoked", "unknown"):
        return None

    code = error_code(response)
    if response.status == 403 and code == "not_entitled":
        return (
            "the runner answered 403 `not_entitled`, and `status` reports its "
            "entitlement as `revoked`. §4.6 step 2 puts that refusal ahead of "
            "this check, so it is the correct answer to this probe and the "
            "rule below it cannot be reached from outside."
        )
    if response.status == 503 and code == "unavailable":
        return (
            "the runner answered 503 `unavailable`, and `status` reports its "
            "entitlement as `unknown` — §5.7.4's past-grace case, which §4.6 "
            "step 2 puts ahead of this check. Whether it is past grace cannot "
            "be determined from outside, so this is not read as a failure."
        )
    return None


def _refuses_a_malformed_body(runner: Runner, context: Context) -> list[Check]:
    """A body that is not JSON is a `bad_request`, and never reaches the agent."""
    response = runner.request(
        "POST",
        "run",
        body=b"{this is not json",
        headers={"Content-Type": "application/json", "Content-Length": "17"},
    )
    title = "run refuses a malformed body"
    preempted = entitlement_preempted(response, context)
    if preempted is not None:
        return [skipped(RUN, title, preempted)]
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

    preempted = entitlement_preempted(response, context)
    if preempted is not None:
        return [skipped(RUN, title, preempted)]

    # Section 4.6 orders these: a runner decides what the request says
    # before it inspects what it holds, so a request that is both malformed
    # and unservable is a `bad_request`. This used to be unordered, and the
    # check had to skip whenever a runner answered 424 -- which meant
    # section 4.2's MUST went untested on exactly the runners most likely
    # to be breaking it, since an incomplete environment is the ordinary
    # state of one being brought up. The 424 is now a finding, reported
    # under section 4.2 -- that is the MUST the runner broke, and the rule
    # its implementer has to fix. Section 4.6 only decides which of the two
    # refusals applies, so it belongs in the message rather than in the
    # section this is filed under.
    if response.status == 424 and error_code(response) == "missing_credential":
        return [
            failed(
                RUN,
                title,
                "answered 424 `missing_credential`"
                + (
                    " (" + ", ".join(context.missing_credentials) + ")"
                    if context.missing_credentials
                    else ""
                )
                + " to a request omitting "
                + ", ".join(repr(key) for key in missing)
                + ". Both refusals describe this request, and section 4.6 "
                "orders them: the request check comes first, so this is a "
                "`bad_request`. Validate the request before inspecting the "
                "environment.",
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
    if not context.refuses_runs:
        return []

    # §5.7.3 and §5.7.4 refuse for different reasons and owe different
    # answers, and the rule underneath both is the one that tells them
    # apart: a runner that has been told no answers `not_entitled` and does
    # not invite a retry; a runner that could not find out answers
    # `unavailable` and does. The never-checked case used to be skipped
    # entirely, so a runner answering 200 there -- running an agent it has
    # no entitlement for -- swept clean.
    never_checked = context.never_checked
    section = "5.7.3" if never_checked else "5.7.4"
    expected_status, expected_code = (503, "unavailable") if never_checked else (403, "not_entitled")
    condition = (
        "an entitlement it has never been able to check"
        if never_checked
        else "a revoked entitlement"
    )

    checks: list[Check] = []
    for verb in ("run", "stream"):
        if context.level is not None and context.level < (2 if verb == "run" else 3):
            continue
        response = _post(runner, verb, {"inputs": {}}, context)
        title = f"{verb} refuses {condition}"
        if response.status == expected_status:
            checks.append(passed(section, title))
            checks.extend(
                error_envelope_checks(
                    response,
                    context=f"{verb} with {condition}",
                    expected_code=expected_code,
                )
            )
        else:
            why = (
                "`status` reports the entitlement as `unknown` with no "
                "`checked_at`, so no check has ever completed — §5.7.3 says "
                "such a runner MUST NOT run the agent on entitlement grounds, "
                "however long it has been trying, and owes 503 `unavailable`. "
                "`not_entitled` would assert something no distributor has said."
                if never_checked
                else "`status` reports the entitlement as `revoked`, and a "
                "revoked entitlement is a refusal the runner has been told "
                "about — 403 `not_entitled`, the one place that code is "
                "correct. `unavailable` would invite a retry that cannot "
                "succeed."
            )
            checks.append(
                failed(
                    section,
                    title,
                    f"answered {response.status}. {why}"
                    + (
                        " This body also omits a required input, so a runner "
                        "validating the request first answers 400 here. §4.6 "
                        "puts the entitlement at step 2, ahead of the media "
                        "type, the inputs and the environment: a 400 names "
                        "something the caller could fix and so invites the "
                        "retry a refusing runner must not imply."
                        if response.status == 400
                        else ""
                    ),
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
    unique, bound = _run_id_is_unique(runner, context, body, first_run_id, timeout)
    checks.extend(unique)
    checks.extend(_a_repeat_is_replayed(runner, context, bound, body, timeout))
    checks.extend(_a_reused_key_is_refused(runner, context, bound, timeout))
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
            warned(
                RUN,
                "the run response carries no status field",
                f"the body carries `status`: {payload['status']!r}. A `run` "
                "body exists only where the run succeeded, so the field can "
                "only repeat the status line.\n"
                "Reported as a warning rather than a failure because the "
                "specification does not forbid it in those terms: §4.2 says "
                "*\"the response body carries no `status` field\"* as a "
                "description, with no MUST NOT, and `run-response.schema.json` "
                "is `additionalProperties: true`, so this payload is "
                "schema-valid. A tool cannot fail a runner for a rule two of "
                "the three places that state it do not state.",
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
) -> tuple[list[Check], BoundAttempt | None]:
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
    bound = BoundAttempt(key=key, run_id=second_run_id) if key else None
    if not isinstance(second_run_id, str):
        return [], bound

    if first_run_id == second_run_id:
        return [
            failed(
                RUN,
                "run_id is unique across two runs",
                f"two separate executions both reported {first_run_id!r}. It "
                "must be unique per execution within the runner's lifetime, and "
                "is what correlates a result with the runner's logs.",
            )
        ], bound
    return [passed(RUN, "run_id is unique across two runs")], bound


def _refuses_a_declared_validation(runner: Runner, context: Context) -> list[Check]:
    """§4.2 — a request failing a declared `validation` MUST be refused.

    The rule is one sentence with two halves — *"a request omitting a
    `required` input, or failing a declared `validation`"* — and only the
    first was asked about. A runner that checks presence and nothing else
    passed, which is the ordinary shape of a half-built validator.

    Under `--execute` for a reason that is the finding itself: a runner
    that ignores the constraint has no grounds to refuse this body, so it
    runs the agent. There is no way to ask the question that is free
    against a runner answering it wrongly — the run *is* the answer, and
    the caller has to have agreed to pay for it.

    Against a conformant runner it costs nothing: the refusal happens
    before the agent starts.
    """
    title = "run refuses a declared validation"

    if not context.execute:
        return [
            skipped(
                RUN,
                title,
                "not asked to execute. A runner that ignores its own declared "
                "validation has no grounds to refuse this request, so asking "
                "runs the agent (§4.1.2). Pass --execute to include it.",
            )
        ]

    built = context.a_body_that_fails_validation()
    if built is None:
        return [
            skipped(
                RUN,
                title,
                "no declared `validation` on any input could be violated from "
                "`describe` alone — §4.2 binds a runner to the validation it "
                "declares, so an agent declaring none is owed no refusal here.",
            )
        ]

    body, why = built
    response = runner.post_json("run", body, timeout=_timeout(context))

    preempted = entitlement_preempted(response, context)
    if preempted is not None:
        return [skipped(RUN, title, preempted)]

    if response.status == 400:
        checks = [passed(RUN, title, f"refused {why}.")]
        checks.extend(
            error_envelope_checks(
                response,
                context="run failing a declared validation",
                expected_code="bad_request",
            )
        )
        return checks

    return [
        failed(
            RUN,
            title,
            f"answered {response.status} to a request carrying {why}. §4.2 "
            "requires a request failing a declared `validation` to be refused "
            "`400` `bad_request`, in the same sentence that requires it for a "
            "missing `required` input"
            + (
                " — and this one ran the agent, so the constraint `describe` "
                "publishes is one the runner does not apply."
                if response.status == 200
                else "."
            ),
        )
    ]


def _credential_names(context: Context) -> str:
    """How the reports name what is missing, or a phrase for "it did not say"."""
    missing = context.missing_credentials
    if missing:
        return ", ".join(f"`{name}`" for name in missing)
    return "a credential it does not name"


def _refuses_without_its_credentials(
    runner: Runner, context: Context, body: dict[str, Any]
) -> list[Check]:
    """§4.6 step 5 — a declared credential the environment lacks is a `424`.

    The **MUST** binds each row of the sequence as well as the sequence
    itself: where `describe` declares a credential and the runner does not
    hold it, the runner answers `424 missing_credential` rather than
    starting the agent and reporting whatever the agent's own failure turns
    out to be. That is the difference this asks about, and it is the one a
    client cannot discover any other way — a `424` names the variable to
    set, and the `500 agent_error` that follows a run started without it
    names nothing.

    Only askable because the runner said so first. §4.4 makes
    `status.credentials` **OPTIONAL**, so a runner that publishes no
    credential state is conformant and its environment is not observable
    from outside; the skip says as much rather than passing it quietly.
    That optionality governs *publishing*, not checking — a runner may
    perform step 5 and report nothing — so the absence is a limit on this
    checker, not a finding about the runner.

    Under `--execute` for the same reason `_refuses_a_declared_validation`
    is: the body satisfies every declared input, so a runner that skips
    step 5 has no grounds to refuse it and runs the agent. Against a
    conforming runner it costs nothing, because the refusal happens before
    the agent starts.

    `run` only, though §4.6 orders `stream` the same way. Every state the
    entitlement checks cover refuses both verbs, so probing both is free
    there; here the second probe is free only against a runner that
    passes, and buys a second execution against exactly the runner that
    does not.
    """
    title = "run refuses a credential it has not got"

    if not context.reports_a_missing_credential:
        if context.credentials_satisfied is True:
            # The runner says its environment is complete, so there is no
            # request it owes a 424 and the step passes vacuously. Reported
            # as nothing rather than as a skip: this is the ordinary state
            # of a working runner, and a line saying so on every clean run
            # would be noise.
            return []
        if not context.declared_credentials:
            # §4.1.3 declares credentials by name, and this agent names
            # none — so there is nothing for step 5 to check.
            return []
        return [
            skipped(
                REFUSAL_ORDER,
                title,
                "`describe` declares "
                + ", ".join(f"`{name}`" for name in context.declared_credentials)
                + ", and `status` reports no credential state. §4.4 makes "
                "`status.credentials` OPTIONAL, so this runner is conformant "
                "and its environment cannot be read from outside — publish "
                "the block and this rule becomes checkable.",
            )
        ]

    response = runner.post_json("run", body, timeout=_timeout(context))
    names = _credential_names(context)

    if response.status == 424:
        checks = [
            passed(
                REFUSAL_ORDER,
                title,
                f"refused a request satisfying every declared input, with "
                f"`status` reporting {names} unset.",
            )
        ]
        checks.extend(
            error_envelope_checks(
                response,
                context="run without a declared credential",
                expected_code="missing_credential",
            )
        )
        return checks

    return [
        failed(
            REFUSAL_ORDER,
            title,
            f"answered {response.status} to a request satisfying every "
            f"declared input, while `status` reports {names} unset. §4.6 "
            "step 5 requires `424` `missing_credential` here"
            + (
                " — and this one started the agent, so a client meeting an "
                "unset credential learns about it from whatever the agent "
                "fails with rather than from the name of the variable to set."
                if response.status == 200
                else "."
            ),
        )
    ]


def _a_repeat_is_replayed(
    runner: Runner,
    context: Context,
    bound: BoundAttempt | None,
    body: dict[str, Any],
    timeout: float,
) -> list[Check]:
    """Section 4.2 — a repeat carrying the *same* inputs is replayed, not re-run.

    This is the promise `idempotent_retry` exists to make: a client whose
    connection dropped mid-run resends and gets the first answer back
    rather than a second bill. Its sibling below checks the refusal a
    *mismatched* key owes, which is the rule that protects the promise —
    but a runner can honour that refusal perfectly and still re-run every
    identical repeat, which is the case this asks about.

    A re-run is invisible from the outside except here. The response is a
    `200` in a valid envelope carrying a valid `run_id`; nothing about it
    says it was computed twice. Only comparing the identifier against the
    one the key was bound to distinguishes a replay from a fresh execution,
    which is why the identifier is carried down rather than the key alone.

    Costs no execution of its own against a conformant runner — the whole
    point is that it does not run — and against a broken one the run it
    provokes *is* the finding.
    """
    title = "a repeat under the same key is replayed"

    if not context.declares_idempotent_retry:
        return [
            skipped(
                RUN,
                title,
                "the runner does not declare `capabilities.idempotent_retry`, "
                "so it promises no replay and owes nothing here.",
            )
        ]
    if bound is None or bound.run_id is None:
        return [
            skipped(
                RUN,
                title,
                "no execution bound a key to a comparable `run_id`, so there "
                "is nothing to present again.",
            )
        ]

    response = runner.post_json(
        "run", body, timeout=timeout, extra_headers={"Idempotency-Key": bound.key}
    )
    if response.status != 200:
        return [
            failed(
                RUN,
                title,
                f"answered {response.status} to a repeat carrying the same "
                f"inputs under a key it had already answered. §4.2 requires "
                "the first result back: a client that resent after a dropped "
                "connection is told its retry failed, which is the situation "
                "the header exists to survive.",
            )
        ]

    payload = response.json
    replayed = payload.get("run_id") if isinstance(payload, dict) else None
    if not isinstance(replayed, str):
        return [
            failed(
                RUN,
                title,
                "the repeat answered 200 with no string `run_id`, so a client "
                "cannot tell a replay from a second execution.",
            )
        ]
    if replayed != bound.run_id:
        return [
            failed(
                RUN,
                title,
                f"the repeat answered a different `run_id` ({replayed!r} "
                f"against {bound.run_id!r}), so the agent ran again. §4.2 "
                "requires the first result back — identical inputs under a "
                "key already answered MUST NOT execute a second time. The "
                "caller has been billed twice for one request, and nothing "
                "in the response says so.",
            )
        ]
    return [passed(RUN, title)]


def _a_reused_key_is_refused(
    runner: Runner,
    context: Context,
    bound: BoundAttempt | None,
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

    if bound is None:
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
        "run", other, timeout=timeout, extra_headers={"Idempotency-Key": bound.key}
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

    checks.extend(_terminates_once(names, response.stream_truncated))
    checks.extend(_one_run_is_named(events))
    checks.extend(_payloads(events, context))
    checks.extend(_bytes_run_emits_no_delta(events, context))
    checks.extend(_deltas_concatenate(events))
    return checks


def _terminates_once(names: list[str], truncated: bool = False) -> list[Check]:
    """A stream MUST end with exactly one `done` or one `error`.

    `truncated` says the reader stopped on its own deadline rather than at
    the end of the stream, which changes what the absence of a terminal
    event means and so what this reports. Reading "the stream ended
    carrying neither" off a stream that never ended sends an implementer
    looking for an early close that did not happen.
    """
    terminals = [name for name in names if name in TERMINAL_EVENT_NAMES]
    title = "the stream ends with exactly one done or error"

    if len(terminals) == 1 and names[-1] in TERMINAL_EVENT_NAMES:
        return [passed("4.3", title, f"ended with `{names[-1]}`.")]

    if not terminals:
        ended = (
            "the checker stopped reading before either arrived, so the run "
            "is still open as far as a client is concerned"
            if truncated
            else f"the stream ended after {names[-1]!r} with neither"
        )
        return [
            failed(
                "4.3",
                title,
                f"{ended}. A client cannot tell a finished run from a "
                "dropped connection.",
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


def _one_run_is_named(events: list[tuple[str, str]]) -> list[Check]:
    """§4.3 — `done` repeats `start`'s `run_id`.

    The only correlation a stream offers. The response committed to `200
    text/event-stream` before any of this was decided, so there is no header
    or status left to carry it, and a client that watched one run and was
    handed another's identifier has no second source to notice with.

    It spans two events, so neither `stream-event.schema.json` nor
    `run-response.schema.json` can see it — the same reason §4.3's `delta`
    concatenation rule is asserted rather than schema'd.

    Silent where either end is missing or unreadable: `start is first` and
    `exactly one done or error` already report those, and repeating them
    here would file one defect twice under a title that is not about it.
    """
    started = _event_run_id(events, "start")
    finished = _event_run_id(events, "done")
    if started is None or finished is None:
        return []

    title = "start and done name the same run"
    if started == finished:
        return [passed(STREAM, title)]
    return [
        failed(
            STREAM,
            title,
            f"`start` reported {started!r} and `done` reported {finished!r}. "
            "A client correlates a stream with its result, and with the "
            "runner's logs, on that identifier and on nothing else — the "
            "response committed to `200 text/event-stream` before either was "
            "written, so there is no status or header carrying it instead.",
        )
    ]


def _event_run_id(events: list[tuple[str, str]], name: str) -> str | None:
    """The `run_id` of the first event so named, or None if there is none to read."""
    for event_name, data in events:
        if event_name != name:
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return None
        run_id = payload.get("run_id") if isinstance(payload, dict) else None
        return run_id if isinstance(run_id, str) else None
    return None


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


def _bytes_run_emits_no_delta(
    events: list[tuple[str, str]], context: Context
) -> list[Check]:
    """§4.1.4 — a runner producing a `bytes` output MUST NOT emit `delta` at all.

    §4.3's invariant is that concatenated `delta.text` equals
    `output.value`, and for a `bytes` output that value is base64 — so
    fragments of it satisfy the invariant in the one way that is useless to
    the client rendering them: the stream prints the encoding.

    Which is why `_deltas_concatenate` could not catch this. It compares
    strings, and base64 halves do concatenate to the base64 whole. The rule
    it satisfies is the wrong rule for this output type, and the right one
    is that there should be no `delta` here at all.
    """
    declared = (context.describe or {}).get("output")
    if not isinstance(declared, dict) or declared.get("type") != "bytes":
        return []

    title = "a bytes run emits no delta"
    deltas = [data for name, data in events if name == "delta"]
    if not deltas:
        return [passed("4.1.4", title)]

    return [
        failed(
            "4.1.4",
            title,
            f"`describe` declares a `bytes` output and the stream carried "
            f"{len(deltas)} `delta` events. §4.1.4 forbids them outright for "
            "this type: they concatenate to the base64, so a client "
            "rendering them as they arrive prints the encoding rather than "
            "the artifact. Progress on such a run rides on `step`, which "
            "reports it without pretending to be the output.",
        )
    ]


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
