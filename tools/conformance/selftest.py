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
    Fault.NO_404: ("2", "an unimplemented path answers 404", {}),
    Fault.CREDENTIAL_VALUE: ("4.1.3", "credentials are declared by name only", {}),
    Fault.WRITE_TOOLS_NOT_SUBSET: ("4.1.2", "write_tools is a subset of tools", {}),
    Fault.AGENT_ID_MISMATCH: ("2.2", "describe and status name the same agent", {}),
    Fault.STALE_NOT_REQUIRED: ("4.4", "not_required carries no check timestamp", {}),
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
    Fault.VALIDATES_BEFORE_ENTITLEMENT: (
        "5.7.4",
        "run refuses a revoked entitlement",
        {"revoked": True},
    ),
    Fault.REPLAYS_A_MISMATCHED_KEY: (
        "4.2",
        "reused key with different inputs",
        {"execute": True, "idempotent": True},
    ),
}


def _report(
    *faults: Fault,
    execute: bool = False,
    level: int = 3,
    idempotent: bool = False,
    revoked: bool = False,
):
    with fake_runner(*faults, level=level, idempotent=idempotent, revoked=revoked) as origin:
        return check(
            Runner(origin, timeout=10.0),
            Context(execute=execute, origin=ALLOWED_ORIGIN),
            "self-test",
        )


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

    for fault, (section, fragment, options) in EXPECTED.items():
        report = _report(fault, **options)
        matching = [
            c
            for c in report.failures
            if c.section == section and fragment.lower() in c.title.lower()
        ]
        if not matching:
            other = "; ".join(f"§{c.section} {c.title}" for c in report.failures)
            problems.append(
                f"{fault.name} was not caught by §{section} …{fragment}…\n"
                f"    the runner {fault.value}\n"
                f"    failures reported: {other or 'none at all'}"
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
    return len(read)


def main() -> int:
    problems: list[str] = []

    print("postern-conformance self-test\n")

    baselines = _baseline_is_clean(problems)
    print(f"  {baselines} conformant baselines, none failing")

    codes = _every_defined_code_is_known(problems)
    print(f"  {codes} error codes, table agrees with the schema")

    bundled = _the_build_hook_bundles_every_schema(problems)
    print(f"  {bundled} schemas, the build hook bundles each one")

    faults = _every_fault_is_caught(problems)
    print(f"  {faults} planted faults, each caught by its own check")

    if problems:
        print("\n" + "\n".join(f"  ✗ {problem}" for problem in problems))
        print(f"\n{len(problems)} problem(s).")
        return 1

    print("\nEvery check can fail.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
