#!/usr/bin/env python3
"""Check that the specification, its schemas and its examples still agree.

CONTRIBUTING.md asks that a change to the specification updates the schemas
and examples alongside it. This is what makes that checkable rather than
aspirational: run it before opening a pull request.

    pip install jsonschema
    python scripts/validate.py

Five things are checked, because five different kinds of edit go wrong:

1. Every file in examples/ validates against its schema.
2. Every fenced JSON block in SPEC.md validates against its schema too.
   Without this, the document a human reads and the file a validator reads
   drift apart silently, and they drift in the direction nobody looks.
3. Rules that cost an implementer something, and rules JSON Schema cannot
   express at all, are pinned by payloads that MUST fail.
4. The agent identifier grammar (SPEC.md section 1.5) is written out in
   SPEC.md and in three schemas, so all four are asserted to be one string.
5. Every `format` the schemas declare is one this validator can actually
   assert, because jsonschema ignores the ones it has no library for.

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

# `format` is an annotation by default, and jsonschema asserts only the
# formats it has a library for — silently ignoring the rest. Both halves
# matter: without the checker nothing is asserted, and with it a format
# nobody installed a library for still is not. See _formats_are_asserted.
FORMAT_CHECKER = jsonschema.FormatChecker()
FORMAT = re.compile(r'"format":\s*"([^"]+)"')

# examples/stream.txt is an annotated SSE transcript rather than a single
# JSON document, so it has no schema of its own. Its `done` payload is the
# run response, which run-response.json already covers.
PAIRS = [
    ("describe.schema.json", "describe.json"),
    ("run-request.schema.json", "run-request.json"),
    ("run-response.schema.json", "run-response.json"),
    ("status.schema.json", "status.json"),
    ("error.schema.json", "error.json"),
    # Three error examples rather than one. The envelope is identical in each;
    # what differs is `detail`, and that is the part prose alone leaves
    # untested — a runner-side member (§4.1.3's env), a distributor-side one
    # (§5.6's access_ends_at), and, for §5.5's 404, nothing at all. The last
    # is the load-bearing one: a detail saying which of "no such agent", "not
    # entitled" and "dead token" applied would undo the rule the response
    # exists to keep.
    ("error.schema.json", "error-withdrawn.json"),
    ("error.schema.json", "error-not-found.json"),
    # Both entitlement states rather than only `active`. They differ by one
    # value and validate identically, which is the point: §4.4 and §5.4 require
    # `checked_at` and `stale_after_seconds` of a `revoked` answer too, and an
    # implementer who has only ever seen the `active` example is the one who
    # ships a bare {"state": "revoked"} and leaves a runner no deadline at
    # which to ask again.
    ("entitlement.schema.json", "entitlement.json"),
    ("entitlement.schema.json", "entitlement-revoked.json"),
    # The state §5.7 makes reachable. `unknown` carries neither of the fields
    # §4.4 requires of `active` and `revoked`, so nothing else in examples/
    # exercises a runner reporting an entitlement it cannot presently vouch
    # for — which is the case a client is most likely to render wrongly.
    ("status.schema.json", "status-unknown.json"),
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
        return "entitlement.schema.json", None
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
# `id` here is a valid identifier (§1.5) on purpose: every pin below that is
# not about identifiers has to fail for the reason it names, and an invalid
# id in the stub would be a second reason in all of them.
_AGENT = {"id": "acme/a", "name": "A", "version": "1"}
_CHECKED_AT = "2026-08-15T09:14:02Z"
_ENTITLEMENT = {
    "postern": "0.1",
    "state": "active",
    "agent_id": "acme/market-research-crew",
    "checked_at": _CHECKED_AT,
    "stale_after_seconds": 60,
    "grace_seconds": 86400,
}


def _without(member: str) -> dict:
    """The §5.3 answer missing exactly one of its required members.

    Written as a subtraction rather than five literals so that "omits exactly
    one" holds by construction: a pin that fails for two reasons stops
    guarding the rule it names, and the entitlement pins are where that is
    easiest to do by accident.
    """
    return {key: value for key, value in _ENTITLEMENT.items() if key != member}


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
        "describe.schema.json",
        "a boolean default, which no declared input type can produce",
        {
            "postern": "0.1",
            "agent": _AGENT,
            "inputs": [
                {"key": "d", "label": "D", "type": "text", "required": False,
                 "default": True}
            ],
        },
    ),
    (
        "run-request.schema.json",
        "a boolean input value, which no declared input type can produce",
        {"inputs": {"agree": True}},
    ),
    # §1.5's grammar exists so that comparison and path encoding have one
    # answer each. Each of these is a string some other identifier scheme
    # would have accepted, and accepting it here would put the divergence
    # back: an uppercase id needs a folding rule, a bare name needs a default
    # owner, and a percent-encoded one needs a decoding step §5.3.1 forbids.
    (
        "describe.schema.json",
        "an agent id carrying uppercase, which comparison would have to fold",
        {"postern": "0.1", "agent": {**_AGENT, "id": "Acme/Market-Research-Crew"},
         "inputs": []},
    ),
    (
        "describe.schema.json",
        "an agent id with no owner part",
        {"postern": "0.1", "agent": {**_AGENT, "id": "market-research-crew"},
         "inputs": []},
    ),
    (
        "describe.schema.json",
        "an agent id one character past the 128-character bound",
        {"postern": "0.1", "agent": {**_AGENT, "id": "acme/" + "a" * 124},
         "inputs": []},
    ),
    (
        "status.schema.json",
        "an agent id whose separator is percent-encoded rather than a separator",
        {"postern": "0.1", "level": 1, "state": "ready",
         "agent": {"id": "acme%2Fmarket-research-crew"}},
    ),
    # Each of these omits exactly one required field. A payload missing two
    # would still be rejected, but by whichever rule fired first — and a pin
    # that can pass for the wrong reason stops guarding the rule it names.
    (
        "status.schema.json",
        "an active entitlement with no declared staleness bound",
        {"postern": "0.1", "level": 3, "state": "ready",
         "entitlement": {"state": "active", "checked_at": _CHECKED_AT}},
    ),
    (
        "status.schema.json",
        "a revoked entitlement with no timestamp to re-check from",
        {"postern": "0.1", "level": 3, "state": "ready",
         "entitlement": {"state": "revoked", "stale_after_seconds": 60}},
    ),
    (
        "status.schema.json",
        "a revoked entitlement with no deadline to re-check after",
        {"postern": "0.1", "level": 3, "state": "ready",
         "entitlement": {"state": "revoked", "checked_at": _CHECKED_AT}},
    ),
    # Every member of the §5.3 answer is required, and each absence costs a
    # runner something it cannot recover: the version it is talking to, the
    # question that was answered, the anchor for §5.4's deadline, or the
    # deadline itself.
    (
        "entitlement.schema.json",
        "an entitlement answer with no version marker",
        _without("postern"),
    ),
    (
        "entitlement.schema.json",
        "an entitlement answer with no agent_id to match against the request",
        _without("agent_id"),
    ),
    (
        "entitlement.schema.json",
        "an entitlement answer with no timestamp to re-check from",
        _without("checked_at"),
    ),
    (
        "entitlement.schema.json",
        "an entitlement answer with no deadline to re-check after",
        _without("stale_after_seconds"),
    ),
    (
        "entitlement.schema.json",
        "an entitlement answer that leaves the offline grace to be inferred",
        _without("grace_seconds"),
    ),
    (
        "entitlement.schema.json",
        "an entitlement answer in a state only a runner reports",
        {**_ENTITLEMENT, "state": "unknown"},
    ),
    (
        "entitlement.schema.json",
        "an entitlement answer whose agent_id is percent-encoded",
        {**_ENTITLEMENT, "agent_id": "acme%2Fmarket-research-crew"},
    ),
    # §5.6 says access_ends_at is RFC 3339 so a client can say something true
    # about it, and until the checker was installed a distributor could answer
    # "soon". These three are the assertion itself: one for the member §5.6
    # names, and two for the timestamps §4.4 and §5.3 already declared and
    # nothing was reading.
    (
        "error.schema.json",
        "a withdrawal date that is not a timestamp",
        {"error": {"code": "withdrawn", "message": "x",
                   "detail": {"access_ends_at": "15/08/2027"}}},
    ),
    (
        "status.schema.json",
        "a checked_at that is not a timestamp",
        {"postern": "0.1", "level": 3, "state": "ready",
         "entitlement": {"state": "active", "checked_at": "yesterday",
                         "stale_after_seconds": 60}},
    ),
    (
        "entitlement.schema.json",
        "a checked_at that is nearly RFC 3339, with a space for the T",
        {**_ENTITLEMENT, "checked_at": "2026-08-15 09:14:02Z"},
    ),
    (
        "error.schema.json",
        "an error code outside the defined set",
        {"error": {"code": "teapot", "message": "x"}},
    ),
    (
        "error.schema.json",
        "anything riding beside error in the envelope root",
        {"error": {"code": "agent_error", "message": "x"}, "partial_output": "..."},
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


# Where each schema keeps the agent identifier. Two shapes, one grammar.
_IDENTIFIER_POINTERS = {
    "describe.schema.json": ("agent", "id"),
    "status.schema.json": ("agent", "id"),
    "entitlement.schema.json": ("agent_id",),
}


def _identifier_pattern() -> bool:
    """SPEC.md §1.5 publishes the agent identifier grammar as a regular
    expression, and three schemas carry it as a `pattern`. Four copies of one
    rule is four places to edit and three chances to forget, and the symptom of
    forgetting is the one §1.5 exists to prevent: two implementations that
    disagree about which strings are identifiers.

    Returns True when they disagree, so callers can accumulate.
    """
    carried = {}
    for name, pointer in _IDENTIFIER_POINTERS.items():
        node = _load("schemas", name)
        for step in pointer:
            node = node["properties"][step]
        carried[name] = node.get("pattern")
    if len(set(carried.values())) != 1:
        print("FAIL  the schemas do not carry one agent id pattern")
        for name, pattern in sorted(carried.items()):
            print(f"        {name}: {pattern}")
        return True

    pattern = next(iter(carried.values()))
    if pattern not in ROOT.joinpath("SPEC.md").read_text(encoding="utf-8"):
        print("FAIL  SPEC.md does not publish the agent id pattern the schemas carry")
        print(f"        {pattern}")
        return True

    print("ok    SPEC.md and all three schemas carry one agent id pattern")
    return False


def _formats_are_asserted() -> bool:
    """Every `format` the schemas declare must be one FORMAT_CHECKER checks.

    A schema declaring `date-time` against a checker with no date-time
    library accepts every string ever written and looks exactly like a schema
    that works — the specification says RFC 3339, the file says `date-time`,
    the run says ok, and nothing anywhere has looked at the value. The
    libraries are pinned in scripts/requirements.txt; this is what notices
    when one is missing, or when a schema starts using a format none of them
    covers.

    Returns True when a declared format is unchecked, so callers accumulate.
    """
    declared = set()
    for path in sorted(ROOT.glob("schemas/*.json")):
        declared |= set(FORMAT.findall(path.read_text(encoding="utf-8")))

    unchecked = sorted(declared - set(FORMAT_CHECKER.checkers))
    if unchecked:
        print(f"FAIL  schemas/ declares formats nothing asserts: {unchecked}")
        print("        pip install -r scripts/requirements.txt")
        return True

    print(f"ok    every format schemas/ declares is asserted: {sorted(declared)}")
    return False


def _load(*parts: str) -> dict:
    return json.loads(ROOT.joinpath(*parts).read_text(encoding="utf-8"))


def _check(where: str, document: dict, schema_name: str) -> bool:
    """Validate one document against its schema and its invariants.

    Returns True when the document failed, so callers can accumulate.
    """
    schema = _load("schemas", schema_name)
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, format_checker=FORMAT_CHECKER)

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
    failed = _formats_are_asserted()
    print()

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
        validator = jsonschema.Draft202012Validator(
            _load("schemas", schema_name), format_checker=FORMAT_CHECKER
        )
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

    print()
    failed |= _identifier_pattern()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
