#!/usr/bin/env python3
"""Check that every example in examples/ validates against its schema.

CONTRIBUTING.md asks that a change to the specification updates the schemas
and examples alongside it. This is what makes that checkable rather than
aspirational: run it before opening a pull request.

    pip install jsonschema
    python scripts/validate.py

Exit status is 0 when everything validates, 1 otherwise. This is repository
tooling, not an implementation of the protocol — there is deliberately no
reference implementation here yet.
"""

from __future__ import annotations

import json
import pathlib
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
        "error.schema.json",
        "an error code outside the defined set",
        {"error": {"code": "teapot", "message": "x"}},
    ),
]


def _load(*parts: str) -> dict:
    return json.loads(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def main() -> int:
    failed = False

    for schema_name, example_name in PAIRS:
        schema = _load("schemas", schema_name)
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(
            validator.iter_errors(_load("examples", example_name)),
            key=lambda e: list(e.path),
        )
        if errors:
            failed = True
            print(f"FAIL  examples/{example_name}")
            for error in errors:
                print(f"        {list(error.path)}: {error.message}")
        else:
            print(f"ok    examples/{example_name} -> schemas/{schema_name}")

    print()
    for schema_name, description, payload in MUST_REJECT:
        validator = jsonschema.Draft202012Validator(_load("schemas", schema_name))
        if list(validator.iter_errors(payload)):
            print(f"ok    rejects {description}")
        else:
            failed = True
            print(f"FAIL  {schema_name} accepts {description}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
