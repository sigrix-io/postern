#!/usr/bin/env python3
"""Check that the specification, its schemas and its examples still agree.

CONTRIBUTING.md asks that a change to the specification updates the schemas
and examples alongside it. This is what makes that checkable rather than
aspirational: run it before opening a pull request.

    pip install jsonschema
    python scripts/validate.py

Three things are checked, because three different kinds of edit go wrong:

1. Every file in examples/ validates against its schema.
2. Every fenced JSON block in SPEC.md validates against its schema too.
   Without this, the document a human reads and the file a validator reads
   drift apart silently, and they drift in the direction nobody looks.
3. Rules that cost an implementer something, and rules JSON Schema cannot
   express at all, are pinned by payloads that MUST fail.

Exit status is 0 when everything validates, 1 otherwise. This is repository
tooling, not an implementation of the protocol — there is deliberately no
reference implementation here yet.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

try:
    import jsonschema
except ImportError:  # pragma: no cover - the message is the whole point
    sys.exit("jsonschema is not installed. Run: pip install jsonschema")

ROOT = pathlib.Path(__file__).resolve().parent.parent

# examples/stream.txt is an annotated SSE transcript rather than a single
# JSON document, so it has no schema of its own. Its `done` payload is the
# run response, which run-response.json already covers.
PAIRS = [
    ("describe.schema.json", "describe.json"),
    ("run-request.schema.json", "run-request.json"),
    ("run-response.schema.json", "run-response.json"),
    ("status.schema.json", "status.json"),
    ("error.schema.json", "error.json"),
]

FENCE = re.compile(r"^```json\n(.*?)^```", re.MULTILINE | re.DOTALL)


def _spec_blocks():
    """Yield (line number, source) for every fenced JSON block in SPEC.md."""
    text = ROOT.joinpath("SPEC.md").read_text(encoding="utf-8")
    for match in FENCE.finditer(text):
        yield text.count("\n", 0, match.start()) + 1, match.group(1)


def _classify(document: object) -> tuple[str | None, str | None]:
    """Map a SPEC.md payload to its schema, by shape rather than by position.

    Matching on shape means reordering the document does not break the check.
    Returning (None, None) means the block was not recognised, which is a
    failure rather than a skip: a silent skip here would defeat the point of
    reading SPEC.md at all.
    """
    if not isinstance(document, dict):
        return None, None
    if "error" in document:
        return "error.schema.json", None
    if "level" in document:
        return "status.schema.json", None
    if "run_id" in document:
        return "run-response.schema.json", None
    if "agent" in document and "inputs" in document:
        return "describe.schema.json", None
    if set(document) == {"inputs"}:
        return "run-request.schema.json", None
    if "agent-plugins.org" in str(document.get("$schema", "")):
        return None, "§6 plugin.json — Agent Plugins owns this schema, not Postern"
    if "state" in document and "agent_id" in document:
        return None, "§5.3 entitlement check — no schema until #22 lands"
    return None, None


def _write_tools_subset(document: dict) -> str | None:
    """SPEC.md §4.1.2 — `write_tools` MUST be the subset of `tools`.

    JSON Schema cannot express a subset relation between two sibling arrays,
    and §7 calls `write_tools` the only safety-relevant field in `describe`.
    So it is checked here or it is checked nowhere.
    """
    capabilities = document.get("capabilities") or {}
    absent = sorted(
        set(capabilities.get("write_tools") or []) - set(capabilities.get("tools") or [])
    )
    if absent:
        return f"write_tools names tools absent from tools: {absent}"
    return None


def _examples_use_declared_keys(document: dict) -> str | None:
    """SPEC.md §4.2 — `run`'s inputs map is keyed by `describe`'s input keys."""
    declared = {declaration.get("key") for declaration in document.get("inputs") or []}
    used = {
        key
        for example in document.get("examples") or []
        for key in (example.get("inputs") or {})
    }
    undeclared = sorted(used - declared)
    if undeclared:
        return f"examples use input keys describe never declares: {undeclared}"
    return None


INVARIANTS = {
    "describe.schema.json": [_write_tools_subset, _examples_use_declared_keys],
}

# Rules that cost an implementer something are the ones most likely to be
# quietly relaxed by a well-meaning edit, so each is pinned by a payload
# that MUST fail. See SPEC.md sections 4.1.1, 4.1.3, 4.4 and 2.1.
_AGENT = {"id": "a", "name": "A", "version": "1"}
MUST_REJECT = [
    (
        "describe.schema.json",
        "a select input that declares no options",
        {
            "postern": "0.1",
            "agent": _AGENT,
            "inputs": [
                {"key": "d", "label": "D", "type": "select", "required": False}
            ],
        },
    ),
    (
        "describe.schema.json",
        "a credential carrying a value rather than only a name",
        {
            "postern": "0.1",
            "agent": _AGENT,
            "inputs": [],
            "credentials": [{"env": "OPENAI_API_KEY", "value": "sk-secret"}],
        },
    ),
    (
        "status.schema.json",
        "an active entitlement with no declared staleness bound",
        {"postern": "0.1", "level": 3, "state": "ready", "entitlement": {"state": "active"}},
    ),
    (
        "status.schema.json",
        "a revoked entitlement with no timestamp to re-check from",
        {"postern": "0.1", "level": 3, "state": "ready", "entitlement": {"state": "revoked"}},
    ),
    (
        "error.schema.json",
        "an error code outside the defined set",
        {"error": {"code": "teapot", "message": "x"}},
    ),
]

# The invariants above are code rather than schema, so they need pinning of
# their own for the same reason: a rule with no failing case is a rule that
# can be deleted without anything going red.
INVARIANT_MUST_FLAG = [
    (
        _write_tools_subset,
        "write_tools naming a tool that tools omits",
        {"capabilities": {"tools": ["read"], "write_tools": ["write"]}},
    ),
    (
        _examples_use_declared_keys,
        "an example using an input key describe never declared",
        {"inputs": [{"key": "segment"}], "examples": [{"inputs": {"depth": "quick"}}]},
    ),
]


def _load(*parts: str) -> dict:
    return json.loads(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def _check(where: str, document: dict, schema_name: str) -> bool:
    """Validate one document against its schema and its invariants.

    Returns True when the document failed, so callers can accumulate.
    """
    schema = _load("schemas", schema_name)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema)

    problems = [
        f"{list(error.path)}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    ]
    problems += [
        message
        for message in (rule(document) for rule in INVARIANTS.get(schema_name, []))
        if message
    ]

    if problems:
        print(f"FAIL  {where}")
        for problem in problems:
            print(f"        {problem}")
        return True
    print(f"ok    {where} -> schemas/{schema_name}")
    return False


def main() -> int:
    failed = False

    for schema_name, example_name in PAIRS:
        failed |= _check(
            f"examples/{example_name}", _load("examples", example_name), schema_name
        )

    print()
    for line, source in _spec_blocks():
        where = f"SPEC.md:{line}"
        try:
            document = json.loads(source)
        except json.JSONDecodeError as exc:
            failed = True
            print(f"FAIL  {where} is not valid JSON: {exc}")
            continue

        schema_name, skipped = _classify(document)
        if skipped:
            print(f"skip  {where} — {skipped}")
        elif schema_name:
            failed |= _check(where, document, schema_name)
        else:
            failed = True
            print(f"FAIL  {where} matches no known payload shape.")
            print("        Add a rule to _classify(), or an explicit skip reason.")

    print()
    for schema_name, description, payload in MUST_REJECT:
        validator = jsonschema.Draft202012Validator(_load("schemas", schema_name))
        if list(validator.iter_errors(payload)):
            print(f"ok    rejects {description}")
        else:
            failed = True
            print(f"FAIL  {schema_name} accepts {description}")

    for rule, description, payload in INVARIANT_MUST_FLAG:
        if rule(payload):
            print(f"ok    flags {description}")
        else:
            failed = True
            print(f"FAIL  {rule.__name__} misses {description}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
