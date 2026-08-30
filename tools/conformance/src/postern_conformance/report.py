"""What a check produced, and how a run of them is summarised.

The distinction this module exists to hold is between a **MUST** and a
**SHOULD**. Only a MUST can fail a run. A checker that failed on SHOULDs
would be reporting a runner as nonconformant for declining an option the
specification explicitly left open, and the first thing anyone would do
about it is stop reading the output — taking the MUSTs with it.

So a SHOULD violation warns and is loud in the report, and the exit status
stays 0. That is the whole reason `Outcome.WARN` exists rather than a
severity flag on a failure.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import sys
from typing import Any, Iterable

# Exit statuses. 0/1 matches scripts/validate.py; 2 is the case that
# validator never has, because a document is always there to read and a
# runner may not be.
EXIT_CONFORMANT = 0
EXIT_NONCONFORMANT = 1
EXIT_COULD_NOT_CHECK = 2


class Outcome(enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


_GLYPH = {
    Outcome.PASS: "PASS",
    Outcome.FAIL: "FAIL",
    Outcome.WARN: "WARN",
    Outcome.SKIP: "SKIP",
}


@dataclasses.dataclass(frozen=True)
class Check:
    """One rule, checked once.

    `section` is the SPEC.md section the rule is written in, and is not
    decoration: a failure a reader cannot trace back to the sentence that
    caused it is one they have to take on trust, and this checker is not
    the authority — the document is.
    """

    section: str
    title: str
    outcome: Outcome
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.outcome is Outcome.FAIL

    def as_dict(self) -> dict[str, Any]:
        return {
            "section": self.section,
            "title": self.title,
            "outcome": self.outcome.value,
            "detail": self.detail,
        }


def passed(section: str, title: str, detail: str = "") -> Check:
    return Check(section, title, Outcome.PASS, detail)


def failed(section: str, title: str, detail: str) -> Check:
    return Check(section, title, Outcome.FAIL, detail)


def warned(section: str, title: str, detail: str) -> Check:
    return Check(section, title, Outcome.WARN, detail)


def skipped(section: str, title: str, detail: str) -> Check:
    return Check(section, title, Outcome.SKIP, detail)


@dataclasses.dataclass
class Report:
    target: str
    schema_source: str
    checks: list[Check] = dataclasses.field(default_factory=list)
    declared_level: int | None = None
    # Set when the runner could not be reached at all, or answered
    # something that left nothing further worth asking.
    aborted: str | None = None

    def add(self, check: Check | Iterable[Check]) -> None:
        if isinstance(check, Check):
            self.checks.append(check)
        else:
            self.checks.extend(check)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for check in self.checks if check.outcome is outcome)

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.failed]

    @property
    def exit_status(self) -> int:
        if self.aborted is not None:
            return EXIT_COULD_NOT_CHECK
        return EXIT_NONCONFORMANT if self.failures else EXIT_CONFORMANT

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "schema_source": self.schema_source,
            "declared_level": self.declared_level,
            "aborted": self.aborted,
            "summary": {
                outcome.value: self.count(outcome) for outcome in Outcome
            },
            "conformant": self.exit_status == EXIT_CONFORMANT,
            "checks": [check.as_dict() for check in self.checks],
        }

    def write_json(self, stream: Any = None) -> None:
        json.dump(self.as_dict(), stream or sys.stdout, indent=2)
        (stream or sys.stdout).write("\n")

    def write_text(self, stream: Any = None) -> None:
        out = stream or sys.stdout
        write = out.write

        write(f"Postern conformance · {self.target}\n")
        write(f"schemas: {self.schema_source}\n\n")

        if self.aborted is not None:
            write(f"Could not check this runner: {self.aborted}\n")
            return

        section = None
        for check in self.checks:
            if check.section != section:
                section = check.section
                write(f"  §{section}\n")
            write(f"    {_GLYPH[check.outcome]}  {check.title}\n")
            if check.detail:
                for line in check.detail.splitlines():
                    write(f"          {line}\n")

        write("\n")
        if self.declared_level is not None:
            write(f"Declared level: {self.declared_level}\n")

        write(
            "  ".join(
                f"{self.count(outcome)} {outcome.value}" for outcome in Outcome
            )
            + "\n"
        )

        if self.failures:
            write(
                f"\nNonconformant: {len(self.failures)} MUST "
                f"{'rule was' if len(self.failures) == 1 else 'rules were'} broken.\n"
            )
        else:
            level = self.declared_level
            write(
                f"\nConformant at Level {level}."
                if level is not None
                else "\nNo MUST rule was broken."
            )
            if self.count(Outcome.WARN):
                write(
                    f" {self.count(Outcome.WARN)} SHOULD "
                    f"{'rule' if self.count(Outcome.WARN) == 1 else 'rules'} "
                    "not followed — see WARN above.\n"
                )
            else:
                write("\n")
