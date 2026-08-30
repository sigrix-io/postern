"""SPEC.md section 4.1 — `GET /postern/v0/describe`.

`describe.schema.json` carries the shape: the required members, the three
input types, `options` being required for a `select`, the `output.type`
enum, the identifier grammar. What is left here is the part of section 4.1
written as prose about relationships between fields, and the two rules that
are about what a runner must not have *needed* in order to answer.
"""

from __future__ import annotations

import re
from typing import Any

from ..context import Context
from ..probe import Runner
from ..report import Check, failed, passed, warned
from . import check_schema, error_envelope_checks

SECTION = "4.1"

# Members a credential declaration may carry, per section 4.1.3's example.
# Anything else is not forbidden — the object is open — but a member whose
# name suggests it holds the credential itself is worth naming, because
# "declares credentials by environment variable name only" is the rule that
# makes "your keys stay on your machine" checkable rather than promised.
_CREDENTIAL_VALUE_NAMES = frozenset(
    {"value", "secret", "token", "key", "api_key", "apikey", "password", "credential"}
)

# Shapes of well-known credentials, matched only inside the `credentials`
# block. Scoped there deliberately: an agent's `examples` may legitimately
# discuss an API key, and a checker that failed a runner for documenting one
# would be unusable by exactly the agents that most need to.
_SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{28,}"),
)


def run(runner: Runner, context: Context) -> list[Check]:
    checks: list[Check] = []
    response = runner.get("describe")

    # Section 4.1: answerable without credentials and without an
    # entitlement — and section 5.7.4's table makes that hold in every
    # entitlement state, including `revoked`, where `run` and `stream` stop.
    # So this is one check that gets sharper the worse the runner's
    # entitlement is, and its wording says so.
    if response.status != 200:
        entitlement = context.entitlement_state
        aggravation = (
            f" The runner's entitlement state is `{entitlement}`, and §5.7.4 is "
            "explicit that `describe` is unaffected throughout — a runner that "
            "cannot run its agent still says what it is."
            if entitlement in ("revoked", "unknown")
            else ""
        )
        checks.append(
            failed(
                SECTION,
                "describe answers",
                f"answered {response.status}. `describe` must be answerable "
                f"without credentials and without an entitlement.{aggravation}",
            )
        )
        checks.extend(error_envelope_checks(response, context="describe"))
        return checks

    checks.append(passed(SECTION, "describe answers without credentials or entitlement"))

    body = response.json
    if not isinstance(body, dict):
        checks.append(
            failed(
                SECTION,
                "describe body is a JSON object",
                f"body was not a JSON object: {response.text[:200]!r}",
            )
        )
        return checks

    context.describe = body
    checks.append(
        check_schema(SECTION, "describe matches its schema", "describe.schema.json", body)
    )
    checks.append(_side_effect_free(runner, response.body))
    checks.extend(_write_tools(body))
    checks.extend(_credentials_are_names_only(body))
    checks.extend(_agrees_with_status(body, context))
    checks.extend(_capabilities_agree_with_level(body, context))
    return checks


def _side_effect_free(runner: Runner, first_body: bytes) -> Check:
    """Section 4.1 — `describe` MUST be side-effect free.

    Two identical GETs returning identical bytes is evidence, not proof: a
    side effect that leaves no trace in the response is invisible from
    outside, and nothing reachable over HTTP could see it. So a difference
    warns rather than fails — it says the answer moved under a request that
    should not have moved it, which is worth a reader's attention without
    being a finding this tool can stand behind as a breach.
    """
    second = runner.get("describe")
    if second.status == 200 and second.body == first_body:
        return passed(SECTION, "describe is stable across two calls")
    if second.status != 200:
        return warned(
            SECTION,
            "describe is stable across two calls",
            f"a second identical GET answered {second.status} where the first "
            "answered 200.",
        )
    return warned(
        SECTION,
        "describe is stable across two calls",
        "two identical GETs returned different bodies. `describe` must be "
        "side-effect free; a body that moves on its own is not proof of a "
        "side effect, but it is the only symptom of one visible from here.",
    )


def _write_tools(body: dict[str, Any]) -> list[Check]:
    """Section 4.1.2 — `write_tools` MUST be the subset of `tools`."""
    section = "4.1.2"
    capabilities = body.get("capabilities")
    if not isinstance(capabilities, dict):
        return []

    tools = capabilities.get("tools")
    write_tools = capabilities.get("write_tools")
    if not isinstance(write_tools, list):
        return []

    if not isinstance(tools, list):
        return [
            failed(
                section,
                "write_tools is a subset of tools",
                "`write_tools` is declared with no `tools` beside it. It is "
                "defined as the subset of `tools` that spend money or mutate "
                "state, so there is nothing for it to be a subset of.",
            )
        ]

    stray = sorted(set(map(str, write_tools)) - set(map(str, tools)))
    if stray:
        return [
            failed(
                section,
                "write_tools is a subset of tools",
                f"{', '.join(repr(name) for name in stray)} "
                f"{'is' if len(stray) == 1 else 'are'} in `write_tools` and not "
                "in `tools`. A client surfacing the money-spending tools to a "
                "user before the first run would show one the agent never "
                "declared it could invoke.",
            )
        ]
    return [passed(section, "write_tools is a subset of tools")]


def _credentials_are_names_only(body: dict[str, Any]) -> list[Check]:
    """Section 4.1.3 — a `describe` response MUST NOT contain a credential value."""
    credentials = body.get("credentials")
    if not isinstance(credentials, list) or not credentials:
        return []

    findings: list[str] = []
    for index, entry in enumerate(credentials):
        if not isinstance(entry, dict):
            continue
        for member, value in entry.items():
            if member.lower() in _CREDENTIAL_VALUE_NAMES:
                findings.append(
                    f"credentials[{index}] carries a member named {member!r}"
                )
            if isinstance(value, str):
                for shape in _SECRET_SHAPES:
                    if shape.search(value):
                        findings.append(
                            f"credentials[{index}].{member} matches the shape of a "
                            "well-known credential"
                        )
                        break

    if findings:
        return [
            failed(
                "4.1.3",
                "credentials are declared by name only",
                "\n".join(findings)
                + "\nCredentials are declared by environment variable name "
                "only. There is nowhere in this protocol for a secret to "
                "travel, which is the property that makes 'your keys stay on "
                "your machine' checkable rather than promised.",
            )
        ]
    return [passed("4.1.3", "credentials are declared by name only")]


def _agrees_with_status(body: dict[str, Any], context: Context) -> list[Check]:
    """Section 2.2 — a runner serves exactly one agent."""
    if not isinstance(context.status, dict):
        return []

    described = body.get("agent")
    reported = context.status.get("agent")
    if not isinstance(described, dict) or not isinstance(reported, dict):
        return []

    described_id = described.get("id")
    reported_id = reported.get("id")
    if not isinstance(described_id, str) or not isinstance(reported_id, str):
        return []

    if described_id != reported_id:
        return [
            failed(
                "2.2",
                "describe and status name the same agent",
                f"`describe` reports {described_id!r} and `status` reports "
                f"{reported_id!r}. A runner serves exactly one agent, and a "
                "client is entitled to treat this port as that agent's address.",
            )
        ]
    return [passed("2.2", "describe and status name the same agent")]


def _capabilities_agree_with_level(body: dict[str, Any], context: Context) -> list[Check]:
    checks: list[Check] = []
    capabilities = body.get("capabilities")
    level = context.level
    if not isinstance(capabilities, dict) or level is None:
        return checks

    streaming = capabilities.get("streaming")
    if isinstance(streaming, bool) and streaming != (level >= 3):
        checks.append(
            warned(
                SECTION,
                "capabilities.streaming agrees with the declared level",
                f"`capabilities.streaming` is {str(streaming).lower()} while "
                f"`status.level` is {level}. Section 3 makes `level` the "
                "authority — a client MUST NOT assume a level it has not read "
                "from `status` — so the two disagreeing costs a client that "
                "read the other field a call it should not have made.",
            )
        )

    # Section 4.2: "A Level 1 runner has no `run` to be idempotent about and
    # SHOULD NOT declare the field at all."
    if level == 1 and "idempotent_retry" in capabilities:
        checks.append(
            warned(
                "4.2",
                "Level 1 declares no idempotent_retry",
                "`capabilities.idempotent_retry` is declared by a Level 1 "
                "runner, which implements no `run` for a key to make "
                "idempotent.",
            )
        )

    return checks
