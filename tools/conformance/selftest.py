#!/usr/bin/env python3
"""Prove each check can fail, by breaking one rule at a time.

    python tools/conformance/selftest.py

A conformance checker's own failure mode is a false green: every check
reads correctly, passes against the one real implementation, and would have
passed just as happily against a runner that did none of it. Nothing about
reading the code distinguishes a check that works from one that returns
PASS unconditionally.

So this runs the checker twice per rule. Once against a deliberately
conformant fake runner, where nothing may fail; then against the same
runner with exactly one rule broken, where the matching check — named here,
not merely *some* check — must fail. A check that cannot be made to fail is
reported as such, which is the finding this file exists to produce.

Standard library only. Exit status is 0 when every rule is caught, 1
otherwise, matching `scripts/validate.py`.
"""

from __future__ import annotations

import ast
import pathlib
import sys
import time
from typing import Iterator

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tests"))

from fake_runner import ALLOWED_ORIGIN, Fault, fake_runner  # noqa: E402

from postern_conformance.checks import ERROR_CODE_STATUS  # noqa: E402
from postern_conformance.cli import check  # noqa: E402
from postern_conformance.context import Context  # noqa: E402
from postern_conformance.probe import Runner  # noqa: E402
from postern_conformance.report import Outcome  # noqa: E402

# Fault -> the check that must catch it, as (section, a substring of the
# title). The substring is deliberately specific: asserting merely that
# *something* failed would let a fault be "caught" by an unrelated check
# reacting to the same broken runner, which proves nothing about the rule
# the fault was planted for.
EXPECTED: dict[Fault, tuple[str, str, dict]] = {
    Fault.WILDCARD_CORS: ("2.3", "no wildcard", {}),
    Fault.NULL_ORIGIN_ALLOWED: ("2.3", "Origin: null is not allowed", {}),
    Fault.NO_RUN_PREFLIGHT: ("2.3", "answers OPTIONS on run", {}),
    Fault.NO_VARY: ("2.3", "Vary: Origin on the preflight", {}),
    # --execute, and this is a finding rather than a detail. The default
    # probe sends a body the runner must reject anyway, so a runner that
    # parses `text/plain` still answers 400 and the check still passes —
    # which is exactly what the check's own detail says. Only the
    # conclusive probe, which sends a body the runner has no other grounds
    # to refuse, can tell the two apart.
    Fault.PARSES_TEXT_PLAIN: (
        "2.3",
        "run rejects a non-JSON media type (valid body)",
        {"execute": True},
    ),
    Fault.RUNS_ABOVE_LEVEL: ("3", "run answers 501 above Level 1", {"level": 1}),
    Fault.STREAM_DEGRADES: ("3", "stream answers 501 above Level 2", {"level": 2}),
    Fault.NOT_IMPLEMENTED_AT_LEVEL: ("3", "stream is implemented at Level 3", {}),
    Fault.ERROR_SIBLING: ("2.1", "nothing sits beside `error`", {}),
    Fault.MISCODED_ERROR: ("2.1", "travels on 503", {}),
    Fault.DISTRIBUTOR_CODE: ("2.1", "emits no distributor-only code", {}),
    # The status half of this is a warning now (§2.1 constrains what a
    # 404 means, not which status an unimplemented path takes), so the
    # fault is caught by the half that is a real MUST: a 200 carries no
    # error envelope at all.
    Fault.NO_404: ("2.1", "unknown path", {}),
    Fault.CREDENTIAL_VALUE: ("4.1.3", "credentials are declared by name only", {}),
    Fault.WRITE_TOOLS_NOT_SUBSET: ("4.1.2", "write_tools is a subset of tools", {}),
    Fault.AGENT_ID_MISMATCH: ("2.2", "describe and status name the same agent", {}),
    Fault.STALE_NOT_REQUIRED: (
        "4.4",
        "not_required carries no check timestamp",
        {"as_warning": True},
    ),
    Fault.IDEMPOTENT_WITHOUT_HEADER: (
        "2.3",
        "preflight allows Idempotency-Key",
        {"idempotent": True},
    ),
    Fault.NO_START_EVENT: ("4.3", "start is first", {"execute": True}),
    Fault.DELTAS_DISAGREE: ("4.3", "deltas concatenate", {"execute": True}),
    Fault.TWO_TERMINALS: ("4.3", "exactly one done or error", {"execute": True}),
    Fault.LATENCY_ON_STARTED: ("4.3", "event payloads match their schemas", {"execute": True}),
    Fault.CREDENTIAL_BEFORE_REQUEST: (
        "4.2",
        "run refuses a missing required input",
        {"execute": True},
    ),
    Fault.DUPLICATE_RUN_ID: ("4.2", "run_id is unique", {"execute": True}),
    Fault.STATUS_IN_RUN_BODY: (
        "4.2",
        "the run response carries no status field",
        {"execute": True, "as_warning": True},
    ),
    Fault.VALIDATES_BEFORE_ENTITLEMENT: (
        "5.7.4",
        "run refuses a revoked entitlement",
        {"revoked": True},
    ),
    Fault.STREAM_NOT_ROUTED: ("3", "stream is implemented at Level 3", {}),
    Fault.EXAMPLE_ON_BYTES_OUTPUT: (
        "4.1",
        "a bytes output declares no example",
        {"returns_bytes": True},
    ),
    Fault.DELTAS_ON_BYTES_RUN: (
        "4.1.4",
        "a bytes run emits no delta",
        {"execute": True, "returns_bytes": True},
    ),
    Fault.IGNORES_DECLARED_VALIDATION: (
        "4.2",
        "run refuses a declared validation",
        {"execute": True},
    ),
    Fault.WILDCARD_ON_GETS: ("2.3", "no wildcard", {}),
    Fault.WILDCARD_TO_KNOWN_ORIGIN: (
        "2.3",
        "preflight echoes the origin octet-for-octet",
        {},
    ),
    Fault.RUNS_WITHOUT_EVER_CHECKING: (
        "5.7.3",
        "run refuses an entitlement it has never been able to check",
        {"never_checked": True},
    ),
    Fault.RERUNS_AN_IDENTICAL_REPEAT: (
        "4.2",
        "a repeat under the same key is replayed",
        {"execute": True, "idempotent": True},
    ),
    Fault.REPLAYS_A_MISMATCHED_KEY: (
        "4.2",
        "reused key with different inputs",
        {"execute": True, "idempotent": True},
    ),
    Fault.SECRET_SHAPE_OUTSIDE_CREDENTIALS: (
        "4.1.3",
        "no credential value elsewhere in describe",
        {"as_warning": True},
    ),
    Fault.STREAM_RUN_ID_DISAGREES: (
        "4.3",
        "start and done name the same run",
        {"execute": True},
    ),
    Fault.RUNS_WITHOUT_ITS_CREDENTIALS: (
        "4.6",
        "run refuses a credential it has not got",
        {"execute": True, "credentials_missing": True},
    ),
}


def _report(
    *faults: Fault,
    execute: bool = False,
    level: int = 3,
    idempotent: bool = False,
    revoked: bool = False,
    never_checked: bool = False,
    strict_origin: bool = False,
    requires_nothing: bool = False,
    returns_bytes: bool = False,
    credentials_missing: bool = False,
    credentials_unreported: bool = False,
    origin: str | None = ALLOWED_ORIGIN,
):
    with fake_runner(
        *faults,
        level=level,
        idempotent=idempotent,
        revoked=revoked,
        never_checked=never_checked,
        strict_origin=strict_origin,
        requires_nothing=requires_nothing,
        returns_bytes=returns_bytes,
        credentials_missing=credentials_missing,
        credentials_unreported=credentials_unreported,
    ) as (base, counter):
        report = check(
            Runner(base, timeout=10.0),
            Context(execute=execute, origin=origin),
            "self-test",
        )
        report.runs = counter.runs  # type: ignore[attr-defined]
        return report


def _baseline_is_clean(problems: list[str]) -> int:
    """The conformant runner must pass, at every level and in both modes.

    Run first, because a fault test only means something if the same runner
    without the fault passes. A baseline that fails makes every later
    "caught" ambiguous — the check might be reacting to the fault, or to
    whatever was already wrong.
    """
    checked = 0
    for level in (1, 2, 3):
        for execute in (False, True):
            if execute and level < 2:
                continue
            # Both idempotency postures. Declaring `idempotent_retry` changes
            # what the runner owes — a key binds, and a repeat carrying other
            # inputs is refused — so a runner that only ever passes without
            # the declaration leaves the conformant half of that rule
            # unexercised, and a check for it could pass by never running.
            for idempotent in (False, True):
                report = _report(execute=execute, level=level, idempotent=idempotent)
                checked += 1
                if report.failures:
                    problems.append(
                        f"the conformant fake runner failed at Level {level} "
                        f"(execute={execute}, idempotent={idempotent}): "
                        + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
                    )

    # And the same runner with its entitlement revoked, which is a posture
    # rather than a fault: §5.7.4 says such a runner refuses `run` and
    # `stream`, and §4.6 step 2 says it refuses them before it reads the
    # request. A runner doing both is conformant and must sweep clean.
    #
    # This is the case #108 reported and the one nothing here could reach:
    # the checker demanded `400` from probes below step 2 and `403` from the
    # §5.7.4 probe, using the same body for both, so every revoked runner
    # failed whichever order it picked. The baseline above never noticed
    # because the fake runner had no entitlement state at all.
    for level in (2, 3):
        report = _report(level=level, revoked=True)
        checked += 1
        if report.failures:
            problems.append(
                f"the conformant fake runner failed at Level {level} with its "
                "entitlement revoked: "
                + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
            )

    # A runner whose output is a file. Returning `bytes` is conformant, and
    # the two rules that only bind for it -- no `example` in `describe`, no
    # `delta` in the stream -- were unreachable until something produced one.
    for execute in (False, True):
        report = _report(execute=execute, returns_bytes=True)
        checked += 1
        if report.failures:
            problems.append(
                f"the conformant fake runner failed returning bytes "
                f"(execute={execute}): "
                + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
            )

    # §5.7.3's runner: `unknown` with no `checked_at`, refusing with 503
    # `unavailable`. Conformant, and it must sweep clean -- the checker used
    # to skip this state entirely, so nothing here could see either answer.
    for level in (2, 3):
        report = _report(level=level, never_checked=True)
        checked += 1
        if report.failures:
            problems.append(
                f"the conformant fake runner failed at Level {level} having "
                "never completed an entitlement check: "
                + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
            )

    # §4.6 step 5's runner: `status` reports a declared credential unset, and
    # every `run` is refused `424` before the agent starts. Conformant, and a
    # posture rather than a fault for the same reason `revoked` is -- the
    # refusal is what the specification asks for.
    #
    # Both modes, because the two are different claims. Without --execute the
    # rule is not reached at all and nothing may fail on the way past it; with
    # it, the checker sends a request satisfying every declared input, and the
    # checks that need a real run have to stand down rather than read the
    # refusal as the agent failing to answer.
    for execute in (False, True):
        report = _report(execute=execute, credentials_missing=True)
        checked += 1
        if report.failures:
            problems.append(
                f"the conformant fake runner failed reporting a missing "
                f"credential (execute={execute}): "
                + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
            )
        if report.runs:  # type: ignore[attr-defined]
            problems.append(
                f"the checker ran the agent {report.runs} time(s) against a "  # type: ignore[attr-defined]
                f"runner refusing every run for a missing credential "
                f"(execute={execute}) — the refusal happens before the agent "
                "starts, so no run should have been counted."
            )

    # And the runner that says nothing about its credentials at all, which
    # §4.4 permits and most runners will be. It must sweep clean, and the
    # rule must be reported as unreachable rather than silently omitted:
    # a check that emits nothing here is indistinguishable from one nobody
    # wrote, which is the whole failure mode this self-test exists for.
    report = _report(execute=True, credentials_unreported=True)
    checked += 1
    if report.failures:
        problems.append(
            "the conformant fake runner failed reporting no credential state "
            "at all, which §4.4 permits: "
            + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
        )
    if not [
        c
        for c in report.checks
        if c.outcome is Outcome.SKIP and "credential it has not got" in c.title
    ]:
        problems.append(
            "a runner publishing no `status.credentials` drew no skip for "
            "§4.6 step 5 — the rule is unreachable against it, and saying so "
            "is the difference between a checker that could not ask and one "
            "that never had the check."
        )

    # A runner that refuses a stranger's preflight with 403 rather than 204.
    # §2.3 asks for the 204 as a SHOULD, so this is a permitted deviation and
    # a warning at most. Run without --origin, which is the case that broke:
    # the checker made up an origin the runner was entitled to refuse and
    # then failed it for refusing.
    report = _report(strict_origin=True, origin=None)
    checked += 1
    if report.failures:
        problems.append(
            "a runner refusing a stranger's preflight with 403 failed, and "
            "§2.3 only SHOULDs the 204: "
            + "; ".join(f"§{c.section} {c.title}" for c in report.failures)
        )
    if not [c for c in report.checks if c.outcome is Outcome.WARN and "OPTIONS" in c.title]:
        problems.append(
            "a runner refusing a stranger's preflight with 403 drew no warning "
            "at all — the SHOULD is still worth reporting, just not as a "
            "failure."
        )

    # The README's claim, asserted rather than described: "it does not run
    # your agent unless you ask." The case that broke it is an agent
    # declaring no required input, against a runner that ignores its own
    # level -- then the level probe's `{"inputs": {}}` was a *valid*
    # request, so the runner ran it. A malformed body cannot be executed by
    # anyone, and §4.6 step 1 puts the level check ahead of reading it, so a
    # conformant runner still answers 501.
    for fault, level in ((Fault.RUNS_ABOVE_LEVEL, 1), (Fault.STREAM_DEGRADES, 2)):
        report = _report(fault, level=level, requires_nothing=True)
        checked += 1
        if report.runs:  # type: ignore[attr-defined]
            problems.append(
                f"the checker ran the agent {report.runs} time(s) against a "  # type: ignore[attr-defined]
                f"runner that ignores its level ({fault.name}) and declares no "
                "required input — without --execute, and the README promises "
                "it does not."
            )

    return checked


def _every_fault_is_caught(problems: list[str]) -> int:
    uncovered = sorted(set(Fault) - set(EXPECTED), key=lambda f: f.name)
    if uncovered:
        problems.append(
            "no expectation is recorded for: "
            + ", ".join(fault.name for fault in uncovered)
            + ". A fault nothing asserts on is a rule this self-test does not "
            "actually cover."
        )

    for fault, expectation in EXPECTED.items():
        section, fragment, options = expectation[0], expectation[1], dict(expectation[2])
        # A fault may be caught as a warning rather than a failure, where
        # the rule it breaks is one the specification states without a
        # MUST. That is still the check looking — which is all this file
        # asserts — so the expectation names the outcome instead of
        # assuming a failure. Anything not named is a failure, so an
        # existing entry keeps meaning what it meant.
        as_warning = options.pop("as_warning", False)
        report = _report(fault, **options)
        seen = (
            [c for c in report.checks if c.outcome is Outcome.WARN]
            if as_warning
            else report.failures
        )
        matching = [
            c for c in seen if c.section == section and fragment.lower() in c.title.lower()
        ]
        if not matching:
            kind = "warnings" if as_warning else "failures"
            other = "; ".join(f"§{c.section} {c.title}" for c in seen)
            problems.append(
                f"{fault.name} was not caught by §{section} …{fragment}…\n"
                f"    the runner {fault.value}\n"
                f"    {kind} reported: {other or 'none at all'}"
            )

    # §4.1.3 is scanned twice — a failure inside `credentials`, a warning
    # everywhere else — and the wide scan skips that block so one value is
    # not reported as two problems under two titles. Nothing above can see
    # that: an extra warning does not stop a fault being "caught", so the
    # skip would go on reading as deliberate long after it stopped working.
    report = _report(Fault.CREDENTIAL_VALUE)
    doubled = [
        c
        for c in report.checks
        if c.outcome is Outcome.WARN and "elsewhere in describe" in c.title
    ]
    if doubled:
        problems.append(
            "a credential value inside `credentials` was reported twice — once "
            "as §4.1.3's failure and again as its warning. The wide scan skips "
            "that block precisely so one value is one finding."
        )

    return len(EXPECTED)


def _every_defined_code_is_known(problems: list[str]) -> int:
    """The code table here must match the one the specification publishes.

    `error.schema.json` enumerates the codes a conforming implementation
    emits, and `ERROR_CODE_STATUS` pairs each with the status section 2.1
    defines for it. The pairing is prose in SPEC.md and so cannot be
    validated from the schema — but the *set* can, and a code added to the
    specification without a status here would silently stop being checked.
    """
    from postern_conformance import schemas

    schema = schemas.load("error.schema.json")
    published = set(
        schema["properties"]["error"]["properties"]["code"]["enum"]
    )
    known = set(ERROR_CODE_STATUS)

    if published != known:
        missing = sorted(published - known)
        extra = sorted(known - published)
        problems.append(
            "the error-code table has drifted from error.schema.json"
            + (f"\n    in the schema and not checked: {', '.join(missing)}" if missing else "")
            + (f"\n    checked and not in the schema: {', '.join(extra)}" if extra else "")
        )
    return len(published)


def _the_build_hook_bundles_every_schema(problems: list[str]) -> int:
    """The build hook's file list must match the one the loader reads.

    They are two lists of the same thing in two files, which is the shape
    this repository keeps warning about elsewhere — and the failure is the
    quiet kind. A schema added to `schemas/` and to the loader but not to
    the hook produces a wheel that installs cleanly, reports its schemas as
    bundled, and then cannot find the one it needs.

    It must also write none of them into the source tree. That is the
    second half of the same rule rather than a tidiness preference: the
    hook used to copy the schemas into `src/postern_conformance/_schemas`
    and return early whenever that directory was already populated, so
    every wheel built in a checkout after the first carried the first
    build's schemas. A hook that leaves no copy behind has nothing to go
    stale, so `shutil` appearing here again is the defect returning.

    Read with `ast` rather than imported, because importing `hatch_build`
    needs hatchling — a build dependency, and not one a self-test that
    otherwise runs on the standard library should drag in.
    """
    from postern_conformance import schemas

    hook = pathlib.Path(__file__).resolve().parent / "hatch_build.py"
    tree = ast.parse(hook.read_text(encoding="utf-8"), str(hook))

    bundled: set[str] | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "SCHEMA_FILENAMES"
            for target in node.targets
        ):
            bundled = {
                element.value
                for element in ast.walk(node.value)
                if isinstance(element, ast.Constant) and isinstance(element.value, str)
            }

    if bundled is None:
        problems.append(
            f"{hook.name} declares no SCHEMA_FILENAMES, so nothing says which "
            "schemas a wheel carries."
        )
        return 0

    read = set(schemas.SCHEMA_FILENAMES)
    if bundled != read:
        problems.append(
            "hatch_build.py and schemas.py disagree about which schemas exist"
            + (
                f"\n    bundled, never read: {', '.join(sorted(bundled - read))}"
                if bundled - read
                else ""
            )
            + (
                f"\n    read, never bundled: {', '.join(sorted(read - bundled))}"
                if read - bundled
                else ""
            )
        )

    writes = sorted(
        {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("shutil")
        }
        | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
            if alias.name.startswith("shutil")
        }
    )
    if writes:
        problems.append(
            "hatch_build.py imports "
            + ", ".join(writes)
            + ", so it is copying the schemas into the tree again — the copy "
            "is what goes stale, and a rebuilt wheel then ships the previous "
            "build's schemas."
        )

    return len(read)


def _every_declared_format_is_asserted(problems: list[str]) -> int:
    """Every `format` the loaded schemas declare must be one the checker asserts.

    `format` is an annotation in JSON Schema unless the validator has a
    library for the specific format, and jsonschema asserts only the ones it
    can. So a schema declaring `date-time` against a checker with no
    date-time library accepts every string ever written, and looks exactly
    like a schema that works: the specification says RFC 3339, the file says
    `date-time`, the run says ok, and nothing has looked at the value.

    `scripts/validate.py` already makes this check, and it is not the same
    check. That one runs against `scripts/requirements.txt`, installed by the
    `validate` workflow. This package pins its own format libraries in
    `pyproject.toml`, and the `conformance` workflow installs *those*
    (`pip install ./tools/conformance`) before running this file — so the
    wheel's list is the one nothing was comparing. Dropping
    `rfc3986-validator` from it leaves `uri` silently unasserted while every
    check here still passes, because a validator that asserts less passes
    everything it passed before.

    It reads the schemas the checker really loads, through the same
    `schemas.load`, so it speaks for whichever copy resolved — a checkout's
    or the one bundled in the wheel.
    """
    from postern_conformance import schemas
    from postern_conformance.checks import FORMAT_CHECKER

    declared: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "format" and isinstance(value, str):
                    declared.add(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for filename in schemas.SCHEMA_FILENAMES:
        walk(schemas.load(filename))

    unasserted = sorted(declared - set(FORMAT_CHECKER.checkers))
    if unasserted:
        problems.append(
            "the schemas declare formats this package does not assert: "
            + ", ".join(unasserted)
            + "\n    a format with no library behind it accepts anything, and "
            "nothing else here can tell\n    check the format libraries "
            "pinned in pyproject.toml"
        )

    return len(declared)


def _the_stream_reader_stops_without_going_blind(problems: list[str]) -> int:
    """The bounded SSE read must still see what section 4.3 forbids.

    `stream` used to read to EOF, which hangs against a runner that will
    not close — so the read is bounded now. The tempting bound is "stop at
    the terminal event", and it is the wrong one: section 4.3 forbids a
    *second* terminal and any event *after* the first, so a reader that
    stopped on the first would leave both of `_terminates_once`'s failure
    branches with nothing to fire on. Those two checks would go on passing
    and could no longer fail, which is the false green this whole suite is
    against.

    Driven over a plain list of lines rather than a socket: the property is
    about what the reader keeps, and a real connection would make this slow
    and flaky for nothing.
    """
    from postern_conformance.probe import _read_sse

    def framed(*events: tuple[str, str]) -> list[bytes]:
        lines: list[bytes] = []
        for name, data in events:
            lines += [f"event: {name}\n".encode(), f"data: {data}\n".encode(), b"\n"]
        return lines

    far = time.monotonic() + 30.0
    shapes = 0

    shapes += 1
    events, truncated = _read_sse(iter(framed(("start", "{}"), ("done", "{}"), ("step", "{}"))), deadline=far)
    if [name for name, _ in events] != ["start", "done", "step"] or truncated:
        problems.append(
            "the stream reader drops what follows a terminal event, so "
            "`the stream ends with exactly one done or error` can no longer "
            f"catch an event after `done` — it read {[n for n, _ in events]}."
        )

    shapes += 1
    events, truncated = _read_sse(iter(framed(("start", "{}"), ("done", "{}"), ("done", "{}"))), deadline=far)
    if [name for name, _ in events] != ["start", "done", "done"] or truncated:
        problems.append(
            "the stream reader drops a second terminal event, so "
            "`the stream ends with exactly one done or error` can no longer "
            f"catch two — it read {[n for n, _ in events]}."
        )

    shapes += 1

    # Bounded, though the reader under test should never reach the end of
    # it: a guard for "this reads forever" must not itself read forever, or
    # the regression it catches arrives as a hung run rather than a
    # failing one. A working reader stops on the deadline after a few
    # thousand of these; a broken one exhausts them and reports.
    def keepalives() -> Iterator[bytes]:
        for _ in range(2_000_000):
            yield b": keepalive\n"

    events, truncated = _read_sse(keepalives(), deadline=time.monotonic() + 0.05)
    if not truncated:
        problems.append(
            "the stream reader does not stop on its own deadline, so a "
            "runner that never terminates reads forever — the socket's "
            "timeout is per read and a keepalive resets it."
        )

    return shapes


def _the_readme_quotes_this_run(tallies: list[str], problems: list[str]) -> None:
    """README.md's transcript of this command must be what it prints.

    It is a `$ python tools/conformance/selftest.py` block, so a reader
    takes it for the output rather than for prose — and it is the first
    thing anyone weighing whether these checks are worth trusting reads.
    Every number in it is one this run knows, so nothing here has to be
    kept by hand.

    It had drifted three ways at once and none of them was visible from
    the file being edited: two counts had moved, and the schema-bundling
    line had been added to this self-test without ever reaching the block.
    A transcript short by a whole line reads exactly like a complete one.
    """
    readme = pathlib.Path(__file__).resolve().parent / "README.md"
    text = readme.read_text(encoding="utf-8")

    marker = "$ python tools/conformance/selftest.py"
    start = text.find(marker)
    if start == -1:
        problems.append(
            f"{readme.name} no longer shows a run of this command, so nothing "
            "tells a reader what it prints."
        )
        return

    fence = text.find("```", start)
    quoted = [
        line
        for line in text[start:fence].splitlines()
        if line.startswith("  ") and line.strip()
    ]

    if quoted != tallies:
        problems.append(
            f"{readme.name}'s transcript of this command has drifted from what "
            "it prints"
            + "".join(f"\n    quoted: {line.strip()}" for line in quoted)
            + "".join(f"\n    prints: {line.strip()}" for line in tallies)
        )


def main() -> int:
    problems: list[str] = []
    tallies: list[str] = []

    def say(line: str) -> None:
        tallies.append(line)
        print(line)

    print("postern-conformance self-test\n")

    baselines = _baseline_is_clean(problems)
    say(f"  {baselines} conformant baselines, none failing")

    codes = _every_defined_code_is_known(problems)
    say(f"  {codes} error codes, table agrees with the schema")

    bundled = _the_build_hook_bundles_every_schema(problems)
    say(f"  {bundled} schemas, the build hook bundles each one")

    formats = _every_declared_format_is_asserted(problems)
    say(f"  {formats} declared formats, every one asserted")

    shapes = _the_stream_reader_stops_without_going_blind(problems)
    say(f"  {shapes} stream shapes, each read to a bounded end")

    faults = _every_fault_is_caught(problems)
    say(f"  {faults} planted faults, each caught by its own check")

    _the_readme_quotes_this_run(tallies, problems)

    if problems:
        print("\n" + "\n".join(f"  ✗ {problem}" for problem in problems))
        print(f"\n{len(problems)} problem(s).")
        return 1

    print("\nEvery check can fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
