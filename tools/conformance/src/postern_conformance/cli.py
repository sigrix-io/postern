"""The command line.

    postern-conformance http://127.0.0.1:8765

Ordered so that each check has what the last one learned: `status` first
because it declares the level every later rule is measured against,
`describe` next because the run probes are built from its `inputs`, and the
verbs last.

Two things about the defaults are decisions rather than conveniences.

**Nothing runs the agent unless asked.** A run may spend money and invoke
tools that mutate state outside the workspace (SPEC.md section 4.1.2), and
an abort is not a rollback (section 4.5). So the default checks only rules
a runner applies before the agent starts — which is most of the
specification — and `--execute` opts into the rest.

**A SHOULD cannot fail the run.** Only a MUST sets a non-zero exit status.
A checker that failed a runner for declining an option the specification
left open would be ignored, and the MUSTs would be ignored with it.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import POSTERN_VERSION, __version__
from .checks import cors, describe, execution, levels, status, transport
from .context import Context
from .probe import DEFAULT_TIMEOUT_SECONDS, Runner, Unreachable
from .report import EXIT_COULD_NOT_CHECK, Report
from .schemas import SchemasNotFound, schema_source

# The order is the dependency order, and changing it breaks later checks
# rather than merely reordering the report.
PHASES = (
    ("status", status),
    ("transport", transport),
    ("describe", describe),
    ("levels", levels),
    ("cors", cors),
    ("execution", execution),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="postern-conformance",
        description=(
            "Check a running Postern runner against the specification, and "
            "report which conformance level it meets."
        ),
        epilog=(
            "Exit status: 0 conformant, 1 a MUST rule was broken, "
            "2 the runner could not be checked at all."
        ),
    )
    parser.add_argument(
        "target",
        help=(
            "The runner's origin, e.g. http://127.0.0.1:8765. Its "
            "/postern/v0 prefix is accepted too."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Also run the agent. This spends whatever the agent spends and "
            "invokes its write_tools, and is the only way to check the run "
            "and stream response rules. Off by default."
        ),
    )
    parser.add_argument(
        "--origin",
        metavar="URL",
        help=(
            "An origin the runner is configured to allow, e.g. "
            "https://app.example.com. Without it the CORS header rules are "
            "skipped, since which origins a runner allows is its own "
            "decision (SPEC.md section 2.3)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help=f"Per-request timeout for everything but a run (default: {DEFAULT_TIMEOUT_SECONDS:g}).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Write the report as JSON on stdout.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"postern-conformance {__version__} (Postern {POSTERN_VERSION})",
    )
    return parser


def check(runner: Runner, context: Context, schema_description: str) -> Report:
    """Run every phase against one runner and return the report.

    Separate from `main` so a caller — the self-test, or anything embedding
    this — can read the individual checks rather than an exit status. A
    test that could only see the status could not tell a check that caught
    a planted fault from one that failed for its own reasons, which is the
    whole thing the self-test exists to establish.
    """
    report = Report(target=str(runner), schema_source=schema_description)

    for name, module in PHASES:
        try:
            report.add(module.run(runner, context))
        except Unreachable as exc:
            # A runner that answered `status` and then stopped answering is
            # a different finding from one that was never there, and the
            # report says which by how far it got.
            report.aborted = (
                f"{exc}\nReached the `{name}` checks before the runner "
                "stopped answering."
                if report.checks
                else str(exc)
            )
            break

    report.declared_level = context.level
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        _, source = schema_source()
    except SchemasNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_COULD_NOT_CHECK

    try:
        runner = Runner(args.target, timeout=args.timeout)
    except ValueError as exc:
        print(f"{args.target}: {exc}", file=sys.stderr)
        return EXIT_COULD_NOT_CHECK

    report = check(runner, Context(execute=args.execute, origin=args.origin), source)

    if args.as_json:
        report.write_json()
    else:
        report.write_text()

    return report.exit_status
