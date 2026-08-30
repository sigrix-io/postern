"""SPEC.md section 2 — the transport, and the one 404 a runner has.

Small on purpose. Most of section 2.1 is checked where the refusals happen,
by `error_envelope_checks`, because an envelope rule is only observable on
a response that carries one. What is left is the pair of facts about the
transport itself, and the single error a runner can be provoked into
without asking it to do anything.
"""

from __future__ import annotations

from ..context import Context
from ..probe import Runner
from ..report import Check, failed, passed
from . import error_envelope_checks

SECTION = "2"


def run(runner: Runner, context: Context) -> list[Check]:
    checks: list[Check] = []
    response = runner.get("status")

    if response.http_version >= 11:
        checks.append(passed(SECTION, "serves HTTP/1.1"))
    else:
        checks.append(
            failed(
                SECTION,
                "serves HTTP/1.1",
                f"answered HTTP/1.{response.http_version % 10}. Section 2 "
                "requires HTTP/1.1 over a TCP port — and without chunked "
                "encoding a `stream` cannot deliver events as they happen, "
                "which is the whole of what distinguishes it from `run`.",
            )
        )

    checks.extend(_unknown_path(runner))
    return checks


def _unknown_path(runner: Runner) -> list[Check]:
    """Section 2.1 — a runner's only use of `404` is a path it does not implement.

    Worth asking because a runner has nothing else to miss: it serves
    exactly one agent (§2.2) and none of the four verbs carries an agent
    identifier, so unlike a distributor it has no catalogue in which
    something can be absent. A `404` from a runner therefore says nothing
    about the agent, and this is the one way to see the envelope it uses to
    say it.
    """
    response = runner.get("not-a-postern-verb")

    if response.status != 404:
        return [
            failed(
                SECTION,
                "an unimplemented path answers 404",
                f"answered {response.status} for `/postern/v0/not-a-postern-verb`. "
                "A runner's only use of 404 is a path it does not implement.",
            )
        ]

    checks: list[Check] = [passed(SECTION, "an unimplemented path answers 404")]
    checks.extend(
        error_envelope_checks(
            response, context="unknown path", expected_code="not_found"
        )
    )
    return checks
