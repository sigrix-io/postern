"""SPEC.md section 3 — the conformance levels, and the rule that guards them.

    A runner MUST answer a verb above its declared level with `501` and code
    `not_implemented`, rather than degrading to a lesser behaviour.

This is the check the whole tool is named for, and it has a property worth
stating because it is what makes it safe to run against a real agent: a
verb *above* the runner's level must refuse, so probing one executes
nothing. The level rule can therefore be checked in full, on any runner, at
no cost — which is the opposite of the verbs at or below the level, where
asking is the same as running.

The complementary half is checked too, and is nearly as cheap. A verb *at*
the runner's level must not answer `501`, and a request the runner has to
reject on its body (section 4.2) never reaches the agent — so a Level 2
runner that has not in fact implemented `run` is caught by a request it was
always going to refuse.
"""

from __future__ import annotations

from typing import Any

from ..context import Context
from ..probe import Response, Runner
from ..report import Check, failed, passed, skipped
from . import error_envelope_checks

SECTION = "3"

# The level at which each verb becomes required, from section 3's table.
VERB_LEVEL = {"run": 2, "stream": 3}


def run(runner: Runner, context: Context) -> list[Check]:
    level = context.level
    if level is None:
        return [
            skipped(
                SECTION,
                "verbs above the declared level answer 501",
                "`status` reported no usable `level`, so there is no declared "
                "level to hold the runner to. A runner MUST report its level "
                "in `status` (§4.4), and a client MUST NOT assume one it has "
                "not read.",
            )
        ]

    checks: list[Check] = [
        passed(SECTION, f"declares Level {level}", _level_name(level))
    ]

    probe_body = context.a_body_that_cannot_execute()

    for verb, required_level in sorted(VERB_LEVEL.items(), key=lambda pair: pair[1]):
        if level < required_level:
            checks.extend(_above_level(runner, verb, level, required_level, probe_body))
        else:
            checks.extend(_at_level(runner, verb, level, probe_body, context))

    return checks


def _level_name(level: int) -> str:
    return {1: "Describe", 2: "Execute", 3: "Stream"}[level] + " — " + {
        1: "describe, status",
        2: "describe, status, run",
        3: "describe, status, run, stream",
    }[level]


def _above_level(
    runner: Runner,
    verb: str,
    level: int,
    required_level: int,
    probe_body: dict[str, Any] | None,
) -> list[Check]:
    """A verb above the level MUST answer 501 `not_implemented`.

    Nothing here can execute the agent, and the body is what guarantees it
    rather than the rule being checked. `{"inputs": []}` is malformed —
    `run-request.schema.json` types `inputs` as an object — so there is no
    runner that could execute it, level-ignoring or not.

    That matters because the guarantee used to rest on the body omitting a
    `required` input, which is only unservable when the agent declares one.
    Against an agent declaring none, `{"inputs": {}}` is a *valid* request,
    so a runner that ignored its level would have run it — and the README's
    "it does not run your agent unless you ask" was false in exactly that
    case.

    A conformant runner still answers 501 either way: section 4.6 puts the
    level check at step 1, ahead of the media type, the inputs and the
    environment, so the malformed body is never reached. A runner that
    ignores its level now answers 400 instead of running, which is still
    the finding this check reports.
    """
    title = f"{verb} answers 501 above Level {level}"
    response = runner.post_json(verb, probe_body or {"inputs": []})

    if response.status == 501:
        checks = [passed(SECTION, title)]
        checks.extend(
            error_envelope_checks(
                response, context=f"{verb} above level", expected_code="not_implemented"
            )
        )
        return checks

    detail = (
        f"answered {response.status}. `{verb}` requires Level {required_level} "
        f"and this runner declares Level {level}. Section 3 requires the "
        "refusal to be `501` with `not_implemented` rather than a lesser "
        "behaviour: the code matters as much as the status, because a "
        "runner's level is permanent and `unavailable` would invite a retry "
        "that can never succeed."
    )
    if verb == "stream" and response.status == 200:
        detail += (
            "\nAnswering 200 is the specific degradation section 4.3 names: a "
            "client that asked for a stream and silently got one event cannot "
            "tell 'not supported' from 'finished instantly'."
        )
    return [failed(SECTION, title, detail)]


def _at_level(
    runner: Runner,
    verb: str,
    level: int,
    probe_body: dict[str, Any] | None,
    context: Context,
) -> list[Check]:
    """A verb at or below the level MUST NOT answer 501.

    Skipped where no body can be built that the runner is obliged to refuse,
    because the only remaining way to ask is to run the agent — which is
    `--execute`'s decision to make, not this check's.
    """
    title = f"{verb} is implemented at Level {level}"

    if probe_body is None:
        return [
            skipped(
                SECTION,
                title,
                "the agent declares no required input, so there is no request "
                "this runner is obliged to reject — and any request it is not "
                "obliged to reject is one that runs the agent. Re-run with "
                "--execute to check this verb.",
            )
        ]

    response = _post(runner, verb, probe_body)

    if response.status != 501:
        return [passed(SECTION, title)]

    return [
        failed(
            SECTION,
            title,
            f"answered 501 `not_implemented` to a request that should have "
            f"been rejected as `bad_request` (§4.2). The runner declares Level "
            f"{level}, at which `{verb}` is required. Either the level is "
            "overstated or the verb is not wired up.",
        )
    ]


def _post(runner: Runner, verb: str, body: dict[str, Any]) -> Response:
    if verb == "stream":
        response, _events = runner.stream(body, timeout=runner.timeout)
        return response
    return runner.post_json(verb, body)
