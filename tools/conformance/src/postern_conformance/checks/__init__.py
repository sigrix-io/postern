"""Shared machinery for the individual rule checks.

Each module in this package covers one section of SPEC.md and exposes a
`run(...)` returning a list of `Check`s. Nothing here decides an exit
status — that is `Report`'s job — so a check is free to report what it
found without also having to know what it costs.
"""

from __future__ import annotations

from typing import Any, Iterable

import jsonschema

from .. import schemas
from ..probe import Response
from ..report import Check, failed, passed

# The same format checker `scripts/validate.py` installs, and for the same
# reason: `format` is an annotation unless a library for the specific format
# is present, so a schema declaring `date-time` without one accepts every
# string ever written while looking exactly like a schema that works.
FORMAT_CHECKER = jsonschema.FormatChecker()

# SPEC.md section 2.1's table, as the pairing it states. A code is listed
# with the status it is defined to travel on, and with the side that may
# emit it — `R` for a runner, `D` for a distributor.
ERROR_CODE_STATUS = {
    "bad_request": 400,
    "unauthorized": 401,
    "not_found": 404,
    "not_entitled": 403,
    "idempotency_conflict": 409,
    "withdrawn": 410,
    "missing_credential": 424,
    "agent_error": 500,
    "not_implemented": 501,
    "unavailable": 503,
    "run_timeout": 504,
}

# Codes marked `D` only. A runner emitting one has told the client
# something about the responder rather than about the request — section 2.1
# calls such a code unconstructible on the wrong side.
DISTRIBUTOR_ONLY_CODES = frozenset({"withdrawn"})


def error_code(response: Response) -> str | None:
    """The `error.code` of a refusal, or None where the body carries none."""
    body = response.json
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("code")
        return code if isinstance(code, str) else None
    return None


def schema_errors(schema_filename: str, payload: Any) -> list[str]:
    """Validate a payload, returning human-readable messages.

    Sorted by path so a body with several problems reports them in the
    order a reader would find them, rather than in whatever order the
    validator happened to walk.
    """
    validator = jsonschema.Draft202012Validator(
        schemas.load(schema_filename), format_checker=FORMAT_CHECKER
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    ]


def check_schema(
    section: str, title: str, schema_filename: str, payload: Any
) -> Check:
    errors = schema_errors(schema_filename, payload)
    if errors:
        return failed(section, title, "\n".join(errors))
    return passed(section, title)


def error_envelope_checks(
    response: Response,
    *,
    context: str,
    expected_code: str | None = None,
) -> Iterable[Check]:
    """Check one non-2xx answer against SPEC.md section 2.1.

    `context` names the request that produced it, because these run against
    every refusal the checker provokes and a bare "error envelope" line
    repeated eight times tells a reader nothing about which one broke.

    There is deliberately no `expected_status`. The status a refusal travels
    on is not a caller's to state: section 2.1 pairs each code with one, and
    `ERROR_CODE_STATUS` below reads the pairing off the answer's own code. A
    caller passing both would be restating what the specification already
    binds, and could contradict it. Where a check genuinely turns on the
    status — the two entitlement states of section 5.7.4, which differ in
    status and in code together — the caller branches on it before calling
    here, because it has different things to say about each.
    """
    checks: list[Check] = []
    body = response.json

    if body is None:
        checks.append(
            failed(
                "2.1",
                f"{context}: error body is JSON",
                f"body was not JSON ({response.media_type or 'no content-type'}): "
                f"{response.text[:200]!r}",
            )
        )
        return checks

    checks.append(
        check_schema("2.1", f"{context}: error envelope", "error.schema.json", body)
    )

    # Stated separately from the schema even though `error.schema.json` is
    # closed at the root and so already rejects this. The schema reports it
    # as an `additionalProperties` violation on `<root>`, which is true and
    # says nothing about why — and section 2.1 spends four paragraphs on
    # this being the one closed root in the specification.
    if isinstance(body, dict):
        siblings = sorted(set(body) - {"error"})
        if siblings:
            checks.append(
                failed(
                    "2.1",
                    f"{context}: nothing sits beside `error`",
                    "the envelope's root carries "
                    + ", ".join(repr(name) for name in siblings)
                    + " alongside `error`. The root is closed so that every "
                    "future addition lands inside `error`, where unknown "
                    "members are already ignored.",
                )
            )

    inner = body.get("error") if isinstance(body, dict) else None
    if not isinstance(inner, dict):
        return checks

    code = inner.get("code")

    if expected_code is not None and code != expected_code:
        checks.append(
            failed(
                "2.1",
                f"{context}: code is `{expected_code}`",
                f"code was {code!r}.",
            )
        )

    if isinstance(code, str) and code in DISTRIBUTOR_ONLY_CODES:
        checks.append(
            failed(
                "2.1",
                f"{context}: emits no distributor-only code",
                f"`{code}` is defined for a distributor (side `D`). A runner "
                "has no state that can produce it.",
            )
        )
    elif isinstance(code, str) and code in ERROR_CODE_STATUS:
        defined = ERROR_CODE_STATUS[code]
        if response.status != defined:
            checks.append(
                failed(
                    "2.1",
                    f"{context}: `{code}` travels on {defined}",
                    f"code `{code}` arrived on HTTP {response.status}. Section "
                    f"2.1 pairs it with {defined}, and a client reading the "
                    "status class gets a different answer from one reading "
                    "the code.",
                )
            )

    return checks


def stream_event_errors(event_name: str, payload: Any) -> list[str]:
    """Validate one stream event against the schema for *its own name*.

    `stream-event.schema.json` is a `oneOf` over the three payload shapes,
    so validating against it whole asks only whether the payload is one of
    them — and a `start` event carrying a `delta` body passes that. Pinning
    the subschema by name is what turns it into the question section 4.3
    actually asks, which is whether this event is the thing it says it is.
    """
    schema = schemas.load("stream-event.schema.json")
    definitions = schema.get("$defs", {})
    if event_name not in definitions:
        return []
    pinned = {
        "$schema": schema.get("$schema"),
        "$defs": definitions,
        "$ref": f"#/$defs/{event_name}",
    }
    validator = jsonschema.Draft202012Validator(pinned, format_checker=FORMAT_CHECKER)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    ]
