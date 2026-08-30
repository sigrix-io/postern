"""SPEC.md section 2.3 — browser clients.

Two halves, and they fail differently.

The **preflight** half is about a runner being reachable from a page at
all, and most of it is only checkable against an origin the runner has been
configured to allow — which this checker cannot guess. So the rules that
hold for *any* origin are checked unconditionally, and the rest run only
when `--origin` names one.

The **media type** half is not about browsers at all, and section 2.3 says
so: it is the one rule there that binds a runner nobody will ever point a
browser at. A runner that parses whatever it is handed has no preflight,
because a JSON body labelled `text/plain` is sent cross-origin without one
— so the agent runs, spending money and invoking `write_tools`, before any
origin decision has been reached. It is checked on every run.
"""

from __future__ import annotations

from ..context import Context
from ..probe import Response, Runner
from ..report import Check, failed, passed, skipped, warned
from . import error_code

SECTION = "2.3"

# An origin no runner can plausibly have been configured to allow. Used to
# ask what a runner says to a stranger, which is the only way to see a
# wildcard default from outside.
_STRANGER = "https://postern-conformance.invalid"

PREFLIGHT_VERBS = {
    "run": "POST",
    "stream": "POST",
    "describe": "GET",
    "status": "GET",
}


def run(runner: Runner, context: Context) -> list[Check]:
    checks: list[Check] = []
    checks.extend(_preflight_is_answered(runner, context))
    checks.extend(_no_wildcard_default(runner))
    checks.extend(_null_origin(runner))
    checks.extend(_allowed_origin(runner, context))
    checks.extend(_media_type_guard(runner, context))
    return checks


def _preflight(runner: Runner, verb: str, origin: str) -> Response:
    return runner.options(
        verb,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": PREFLIGHT_VERBS[verb],
            "Access-Control-Request-Headers": "content-type",
        },
    )


def _preflight_is_answered(runner: Runner, context: Context) -> list[Check]:
    """A runner MUST answer `OPTIONS` on `run` and `stream`, at any level.

    Section 2.3 is explicit that the preflight's answer does not depend on
    the conformance level: a Level 1 runner preflighted for `run` answers it
    like any other, so that the `POST` behind it arrives and can be refused
    `501` — a readable answer, where a refused preflight leaves the client
    with an opaque failure that names nothing.
    """
    checks: list[Check] = []
    origin = context.origin or _STRANGER

    for verb in ("run", "stream"):
        response = _preflight(runner, verb, origin)
        title = f"answers OPTIONS on {verb}"
        if 200 <= response.status < 300:
            checks.append(passed(SECTION, title))
        else:
            level_note = (
                f"\nThe runner declares Level {context.level}, which does not "
                f"implement `{verb}` — but the preflight does not depend on the "
                "level. Refusing it leaves a browser client with an opaque "
                "failure instead of the 501 it could act on."
                if context.level is not None and context.level < (2 if verb == "run" else 3)
                else ""
            )
            checks.append(
                failed(
                    SECTION,
                    title,
                    f"answered {response.status}. A preflight must be answered "
                    f"on a 2xx — 204 is the usual choice.{level_note}",
                )
            )

    for verb in ("describe", "status"):
        response = _preflight(runner, verb, origin)
        if 200 <= response.status < 300:
            checks.append(passed(SECTION, f"answers OPTIONS on {verb}"))
        else:
            checks.append(
                warned(
                    SECTION,
                    f"answers OPTIONS on {verb}",
                    f"answered {response.status}. A SHOULD rather than a MUST: "
                    "it matters for a client sending a request header outside "
                    "the browser's safelist, which preflights its GET too.",
                )
            )

    return checks


def _no_wildcard_default(runner: Runner) -> list[Check]:
    """A runner MUST NOT ship `Access-Control-Allow-Origin: *` as a default.

    Asked by presenting an origin no runner can have been configured to
    allow. A wildcard is a configuration an operator may legitimately
    choose; it is not one a runner may choose on their behalf, because a
    runner defines no authentication and the origin check is the entirety
    of its access control against a browser.
    """
    response = _preflight(runner, "run", _STRANGER)
    allowed = response.header_values("access-control-allow-origin")
    title = "no wildcard Access-Control-Allow-Origin by default"

    if "*" in allowed:
        return [
            failed(
                SECTION,
                title,
                f"the preflight for an origin the runner cannot have been "
                f"configured to allow ({_STRANGER}) answered "
                "`Access-Control-Allow-Origin: *`. Every page the user visits "
                "can then run this agent.",
            )
        ]

    if _STRANGER in allowed:
        return [
            failed(
                SECTION,
                title,
                f"the runner echoed {_STRANGER} back as an allowed origin. "
                "A runner MUST NOT allow an origin it was not configured to "
                "allow; echoing whatever arrives is a wildcard written the "
                "long way.",
            )
        ]

    return [passed(SECTION, title)]


def _null_origin(runner: Runner) -> list[Check]:
    """`Origin: null` MUST NOT be treated as an origin a configuration can name."""
    response = _preflight(runner, "run", "null")
    allowed = response.header_values("access-control-allow-origin")
    title = "Origin: null is not allowed"

    if "null" in allowed or "*" in allowed:
        return [
            failed(
                SECTION,
                title,
                "the runner allowed `Origin: null`. Sandboxed documents, "
                "`file://` pages and several redirect chains all send it, so "
                "allowing `null` allows all of them at once — it is a wildcard "
                "wearing the shape of one specific origin.",
            )
        ]
    return [passed(SECTION, title)]


def _allowed_origin(runner: Runner, context: Context) -> list[Check]:
    """The header rules, checked against an origin the runner allows."""
    origin = context.origin
    if origin is None:
        return [
            skipped(
                SECTION,
                "allowed-origin headers",
                "no --origin given. The header rules only bind where the "
                "runner allows the origin, and which origins it allows is the "
                "runner's decision — the specification fixes only the two ends "
                "of it. Pass --origin to check them.",
            )
        ]

    checks: list[Check] = []
    preflight = _preflight(runner, "run", origin)
    allowed = preflight.header_values("access-control-allow-origin")

    if origin not in allowed:
        return [
            skipped(
                SECTION,
                "allowed-origin headers",
                f"the runner did not allow {origin} (preflight answered "
                f"{preflight.status}, Access-Control-Allow-Origin "
                f"{allowed or 'absent'}). Refusing an origin is a legitimate "
                "configuration, so this is not a failure — but it means the "
                "header rules could not be checked. Name an origin the runner "
                "is configured for.",
            )
        ]

    checks.append(
        passed(SECTION, "preflight echoes the origin octet-for-octet", f"{origin}")
    )

    # Vary: Origin, on the preflight and on the actual response. A browser
    # keys its preflight cache by origin already; a shared cache between the
    # page and the runner keys on the URL, so a runner echoing an origin
    # without Vary invites that cache to hand the first caller's permission
    # to the second.
    checks.append(_vary(preflight, "preflight"))

    methods = _joined(preflight.header_values("access-control-allow-methods"))
    if "POST" in methods.upper():
        checks.append(passed(SECTION, "preflight allows POST on run"))
    else:
        checks.append(
            failed(
                SECTION,
                "preflight allows POST on run",
                f"Access-Control-Allow-Methods was {methods!r}; `run` is a POST.",
            )
        )

    headers_allowed = _joined(preflight.header_values("access-control-allow-headers")).lower()
    if "content-type" in headers_allowed:
        checks.append(passed(SECTION, "preflight allows Content-Type"))
    else:
        checks.append(
            failed(
                SECTION,
                "preflight allows Content-Type",
                f"Access-Control-Allow-Headers was {headers_allowed!r}. `run` "
                "carries `application/json`, which a browser will not send "
                "unless the preflight admits the header.",
            )
        )

    # Naming Idempotency-Key is a MUST for a runner that declares
    # idempotent_retry: a browser cannot send a header its preflight did not
    # admit, so the promise would otherwise hold for every client kind
    # except the one that has to ask permission to take it up.
    if context.declares_idempotent_retry:
        title = "preflight allows Idempotency-Key"
        if "idempotency-key" in headers_allowed:
            checks.append(passed(SECTION, title))
        else:
            checks.append(
                failed(
                    SECTION,
                    title,
                    "the runner declares `capabilities.idempotent_retry` and "
                    "its preflight does not admit `Idempotency-Key`. To a "
                    "browser client alone, this runner looks like one ignoring "
                    "a header it never received.",
                )
            )

    if preflight.header_values("access-control-allow-credentials"):
        checks.append(
            warned(
                SECTION,
                "no Access-Control-Allow-Credentials",
                "the runner sends `Access-Control-Allow-Credentials`. Postern "
                "defines no cookie and no browser-presented token, so the "
                "header can only admit ambient credentials this protocol never "
                "asked for.",
            )
        )
    else:
        checks.append(passed(SECTION, "no Access-Control-Allow-Credentials"))

    # "MUST ride the actual response as well, and not only the preflight."
    # `status` is the actual response used, because it is the one verb
    # guaranteed to answer at every level and to need nothing.
    actual = runner.get("status", headers={"Origin": origin})
    actual_allowed = actual.header_values("access-control-allow-origin")
    title = "the actual response carries the origin header"
    if origin in actual_allowed or "*" in actual_allowed:
        checks.append(passed(SECTION, title))
    else:
        checks.append(
            failed(
                SECTION,
                title,
                f"`GET status` with `Origin: {origin}` answered "
                f"{actual.status} with Access-Control-Allow-Origin "
                f"{actual_allowed or 'absent'}. The two are refused "
                "separately: a preflight authorises the request, and a "
                "response arriving without the header is discarded by the "
                "browser exactly as an unpermitted one would be — the agent "
                "having run.",
            )
        )
    checks.append(_vary(actual, "actual response"))

    return checks


def _vary(response: Response, where: str) -> Check:
    vary = _joined(response.header_values("vary")).lower()
    title = f"Vary: Origin on the {where}"
    if "origin" in [part.strip() for part in vary.split(",")]:
        return passed(SECTION, title)
    return failed(
        SECTION,
        title,
        f"Vary was {vary or 'absent'}. A shared cache between the page and "
        "the runner keys on the URL, so echoing an origin without `Vary: "
        "Origin` invites it to hand the first caller's permission to the "
        "second.",
    )


def _media_type_guard(runner: Runner, context: Context) -> list[Check]:
    """`run` and `stream` MUST reject a non-JSON media type with `bad_request`.

    Two probes, and only the second is conclusive.

    The safe one sends a body the runner is obliged to reject anyway — one
    omitting a required input — labelled `text/plain`. A conformant runner
    refuses on the media type before reading it; a runner that parses
    whatever it is handed refuses on the body. Both answer `400
    bad_request`, so a pass here is consistent with conformance rather than
    proof of it, and the detail says so.

    The conclusive one sends a *valid* body as `text/plain`, which a
    conformant runner still refuses and a vulnerable one executes. That is
    the vulnerability itself, so it runs only under `--execute`.
    """
    checks: list[Check] = []
    refusable = context.a_body_that_cannot_execute()

    for verb in ("run", "stream"):
        if context.level is not None and context.level < (2 if verb == "run" else 3):
            # Above the level, 501 is the right answer and says nothing
            # about the media-type guard.
            continue

        title = f"{verb} rejects a non-JSON media type"

        if refusable is None:
            checks.append(
                skipped(
                    SECTION,
                    title,
                    "the agent declares no required input, so every body this "
                    "checker could send is one the runner may legitimately "
                    "execute. Re-run with --execute to check this rule.",
                )
                if not context.execute
                else _conclusive(runner, verb, context, title)
            )
            continue

        response = _post_as_text(runner, verb, refusable)
        if response.status == 400 and error_code(response) == "bad_request":
            checks.append(
                passed(
                    SECTION,
                    title,
                    "refused a `text/plain` body with 400 `bad_request`. This "
                    "probe sends a body the runner must reject on its contents "
                    "too, so the refusal is consistent with the media-type "
                    "guard rather than proof of it — --execute makes it "
                    "conclusive.",
                )
            )
        else:
            checks.append(
                failed(
                    SECTION,
                    title,
                    f"answered {response.status}"
                    + (f" with code {error_code(response)!r}" if error_code(response) else "")
                    + ". A browser sends a cross-origin POST with no preflight "
                    "at all when the Content-Type is on its safelist, and "
                    "`text/plain` is on it. A runner that does not reject the "
                    "media type has no preflight: a page on any origin posts "
                    "to this verb and the agent runs before any origin "
                    "decision is reached.",
                )
            )

        if context.execute:
            checks.append(_conclusive(runner, verb, context, title + " (valid body)"))

    # The other half of the same rule: parameters do not enter into it, so a
    # runner MUST accept `application/json; charset=utf-8`. Only asked with
    # a body the runner is obliged to refuse — a 400 naming the body is the
    # pass, and a 415 or a media-type complaint is the failure.
    if refusable is not None and context.level is not None and context.level >= 2:
        response = runner.post_json(
            "run", refusable, content_type="application/json; charset=utf-8"
        )
        title = "application/json; charset=utf-8 is the same media type"
        if response.status == 415:
            checks.append(
                failed(
                    SECTION,
                    title,
                    "answered 415 to `application/json; charset=utf-8`. Section "
                    "2 requires a client to send that form without making the "
                    "bare `application/json` nonconformant to receive — "
                    "parameters do not enter into it.",
                )
            )
        else:
            checks.append(passed(SECTION, title))

    return checks


def _conclusive(runner: Runner, verb: str, context: Context, title: str) -> Check:
    valid = context.a_valid_body()
    if valid is None:
        return skipped(
            SECTION,
            title,
            "could not build a request satisfying every declared input from "
            "`describe` alone, so a refusal could not be attributed to the "
            "media type rather than to the body.",
        )

    response = _post_as_text(runner, verb, valid)
    if response.status == 400 and error_code(response) == "bad_request":
        return passed(SECTION, title, "refused a valid body sent as `text/plain`.")
    return failed(
        SECTION,
        title,
        f"answered {response.status} to a valid body labelled `text/plain`. "
        "The agent ran, or was about to: this is the cross-origin request a "
        "browser sends without asking anyone.",
    )


def _post_as_text(runner: Runner, verb: str, body: dict) -> Response:
    return runner.post_json(verb, body, content_type="text/plain")


def _joined(values: tuple[str, ...]) -> str:
    return ", ".join(values)
