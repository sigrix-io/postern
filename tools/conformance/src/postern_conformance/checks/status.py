"""SPEC.md section 4.4 — `GET /postern/v0/status`.

`status.schema.json` already carries most of this section's shape: the
`level` enum, the three `state` values, the four `entitlement.state` values,
the conditional requirement of `checked_at` and `stale_after_seconds`, and
`max_concurrent_runs` bottoming out at 1. Validating against it is
therefore most of the work, and what follows are the rules a schema cannot
reach — the ones about what a runner must *not* have needed in order to
answer, and the one prose requirement stated as an omission.
"""

from __future__ import annotations

from typing import Any

from ..context import Context
from ..probe import Response, Runner
from ..report import Check, failed, passed, warned
from . import check_schema, error_envelope_checks

SECTION = "4.4"


def run(runner: Runner, context: Context) -> list[Check]:
    checks: list[Check] = []
    response = runner.get("status")

    # "status MUST answer at Level 1, and MUST NOT require credentials."
    # The checker sends no credential of any kind, so a 2xx here is the
    # whole of the second half — and 424 is the specific refusal that would
    # mean a runner had made `status` conditional on the environment being
    # complete, which is exactly what this rule forbids.
    if response.status != 200:
        checks.append(
            failed(
                SECTION,
                "status answers",
                f"answered {response.status}. `status` must answer at Level 1 "
                "and must not require credentials, so it is the one verb that "
                "is available whatever else is wrong with the runner.",
            )
        )
        checks.extend(error_envelope_checks(response, context="status"))
        return checks

    checks.append(passed(SECTION, "status answers without credentials"))

    body = response.json
    if not isinstance(body, dict):
        checks.append(
            failed(
                SECTION,
                "status body is a JSON object",
                f"body was not a JSON object: {response.text[:200]!r}",
            )
        )
        return checks

    context.status = body
    checks.append(check_schema(SECTION, "status matches its schema", "status.schema.json", body))
    checks.extend(_media_type(response))
    checks.extend(_entitlement(body))
    return checks


def _media_type(response: Response) -> list[Check]:
    """Section 2 — bodies are `application/json; charset=utf-8`.

    Reported under this section rather than 2 because it is this response
    that carries it, and a reader chasing a status failure should not have
    to look somewhere else to find out that the content type was the
    problem.
    """
    if response.media_type == "application/json":
        return [passed(SECTION, "status is served as application/json")]
    return [
        failed(
            SECTION,
            "status is served as application/json",
            f"Content-Type was {response.header('content-type')!r}. Section 2 "
            "requires JSON bodies for every verb but `stream`.",
        )
    ]


def _entitlement(body: dict[str, Any]) -> list[Check]:
    entitlement = body.get("entitlement")
    if not isinstance(entitlement, dict):
        # `status.schema.json` requires the block now, so "status matches
        # its schema" already fails here and this is the sentence saying
        # why -- the same reason §2.1's sibling rule is stated beside the
        # closed root rather than left to an `additionalProperties`
        # violation. It stays a warning rather than becoming a second
        # failure for one answer.
        return [
            warned(
                SECTION,
                "entitlement state is reported",
                "no `entitlement` block. §5.1 requires a runner with no "
                "distributor to report `not_required`, and saying nothing "
                "is not a quieter way of saying it: a client cannot tell "
                "that from a runner that has not implemented entitlement "
                "at all.",
            )
        ]

    checks: list[Check] = []
    state = entitlement.get("state")

    # "It is omitted for not_required, where no check took place." The
    # schema requires the two fields under `active` and `revoked` and says
    # nothing about their absence here, because a schema cannot express
    # "this member must not be present when that one holds this value"
    # without a second conditional nobody would think to read.
    if state == "not_required":
        present = [name for name in ("checked_at", "stale_after_seconds") if name in entitlement]
        if present:
            checks.append(
                warned(
                    SECTION,
                    "not_required carries no check timestamp",
                    f"`entitlement` carries {', '.join(present)} while its state "
                    "is `not_required`. No check took place, so there is no "
                    "read time to report and nothing to go stale.\n"
                    "A warning rather than a failure: §4.4 says *\"it is "
                    "omitted for `not_required`\"* as a description, with no "
                    "MUST, and `status.schema.json` accepts the payload. The "
                    "field is meaningless here, not forbidden.",
                )
            )
        else:
            checks.append(passed(SECTION, "not_required carries no check timestamp"))

    # Section 5.7.4: `unknown` has two shapes, told apart by whether
    # `checked_at` is present — an agent still running with a deadline, or
    # one that cannot start. Both are legal, so this reports which was seen
    # rather than judging it.
    if state == "unknown":
        shape = (
            "inside a declared grace period"
            if "checked_at" in entitlement
            else "never checked at all — `run` and `stream` answer 503"
        )
        checks.append(passed(SECTION, "unknown entitlement is one of §5.7.4's two shapes", shape))

    return checks
