#!/usr/bin/env python3
"""Check that the specification, its schemas and its examples still agree.

CONTRIBUTING.md asks that a change to the specification updates the schemas
and examples alongside it. This is what makes that checkable rather than
aspirational: run it before opening a pull request.

    pip install jsonschema
    python scripts/validate.py

Nine things are checked, because nine different kinds of edit go wrong:

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
6. The specification version is mirrored in payloads, schema identifiers and
   prose, and VERSIONING.md requires them to track it exactly. They are
   asserted to be one string, so a bump is either complete or caught.
7. Every section docs/ points at is a section SPEC.md still has. The pages
   there are pictures of the specification, and a picture that cites a
   section number nobody kept is worse than no picture.
8. examples/stream.txt is read as a transcript rather than trusted as prose:
   every event payload in it validates against the schema for its event
   name, and the delta texts concatenate to the done payload's output.value
   — the one section 4.3 rule that spans events, and so the one no schema
   can reach.
9. Every line count docs/ cites is SPEC.md's real one. The pages there
   state its length as the thing a reader is deciding whether to take on,
   and every edit to SPEC.md invalidates the number.

Exit status is 0 when everything validates, 1 otherwise. This is repository
tooling, not an implementation of the protocol — there is deliberately no
reference implementation here yet.
"""

from __future__ import annotations

import json
import os
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

# examples/stream.txt is an annotated SSE transcript rather than a single JSON
# document, so it has no schema of its own — but its payloads do, and
# _stream_transcript() below validates each one where it sits rather than
# taking the transcript's word for it.
PAIRS = [
    ("describe.schema.json", "describe.json"),
    ("run-request.schema.json", "run-request.json"),
    ("run-response.schema.json", "run-response.json"),
    # Both output types rather than only `text`. `bytes` is the one an
    # implementer has never seen, and the two things it adds are exactly the
    # two prose cannot check: that `value` is really base64 of something —
    # the run-response example decodes to a valid PNG — and that
    # `media_type` rides beside `type` rather than being remembered later.
    ("describe.schema.json", "describe-bytes.json"),
    ("run-response.schema.json", "run-response-bytes.json"),
    ("status.schema.json", "status.json"),
    ("error.schema.json", "error.json"),
    # Four error examples rather than one. The envelope is identical in each;
    # what differs is `detail`, and that is the part prose alone leaves
    # untested — a runner-side member (§4.1.3's env), a distributor-side one
    # (§5.6's access_ends_at), §4.5's max_run_seconds, and, for §5.5's 404,
    # nothing at all. The 404 is the load-bearing one: a detail saying which
    # of "no such agent", "not entitled" and "dead token" applied would undo
    # the rule the response exists to keep. §4.2's idempotency conflict is the
    # other detail-less one, and for the opposite reason: everything a client
    # needs is that its key is spoken for, and echoing the first request's
    # inputs back would publish one caller's body to whoever guessed its key.
    ("error.schema.json", "error-withdrawn.json"),
    ("error.schema.json", "error-not-found.json"),
    ("error.schema.json", "error-run-timeout.json"),
    ("error.schema.json", "error-idempotency-conflict.json"),
    # Both entitlement states rather than only `active`. They differ by one
    # value and validate identically, which is the point: §4.4 and §5.4 require
    # `checked_at` and `stale_after_seconds` of a `revoked` answer too, and an
    # implementer who has only ever seen the `active` example is the one who
    # ships a bare {"state": "revoked"} and leaves a runner no deadline at
    # which to ask again.
    ("entitlement.schema.json", "entitlement.json"),
    ("entitlement.schema.json", "entitlement-revoked.json"),
    # The other distributor answer, and the only payload in this list whose
    # path this specification does not define — §5 fixes the two a runner
    # must call, and a version answer is neither, so §8 records where Sigrix
    # serves it. The shape is fixed here regardless of who serves it.
    ("version.schema.json", "version.json"),
    # The state §5.7 makes reachable. `unknown` carries neither of the fields
    # §4.4 requires of `active` and `revoked`, so nothing else in examples/
    # exercises a runner reporting an entitlement it cannot presently vouch
    # for — which is the case a client is most likely to render wrongly.
    ("status.schema.json", "status-unknown.json"),
    # The other state §5.7 produces, and the one whose numbers may be nobody's
    # but the runner's. After a `404` there is no distributor answer to take
    # `checked_at` or `stale_after_seconds` from — §5.5 requires that body to
    # be constant — so a runner reporting `revoked` supplies its own receipt
    # time and its own re-check cadence (§5.7.4). The shape here is identical
    # to one built from a distributor's `revoked` answer, deliberately: under
    # `revoked` the bound protects the runner's own operator, so nothing marks
    # which party supplied it and no client has to care. No `grace_seconds`,
    # because a `404` is an answer and no grace applies to one.
    ("status.schema.json", "status-revoked.json"),
    # The three event payloads §4.3 defines itself. `step` twice, because the
    # started/finished distinction is the one that carries a rule: latency_ms
    # is an elapsed time, so it belongs on the second and not the first, and
    # an example of each is what makes that visible rather than only asserted.
    ("stream-event.schema.json", "stream-event-start.json"),
    ("stream-event.schema.json", "stream-event-step-started.json"),
    ("stream-event.schema.json", "stream-event-step-finished.json"),
    ("stream-event.schema.json", "stream-event-delta.json"),
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


# Payloads a schema MUST accept. The mirror of MUST_REJECT, and needed for
# the same reason in the other direction: a pattern can be wrong by being
# too narrow, and nothing in a list of refusals notices when something legal
# stops fitting. `media_type` was wrong both ways at once -- it rejected
# every `x-` experimental type while accepting a subtype beginning `!`.
MUST_ACCEPT = [
    (
        "run-response.schema.json",
        "an experimental media type, which RFC 6838 permits",
        {
            "postern": "0.1",
            "run_id": "01JD8XW2Q9",
            "output": {"type": "bytes", "media_type": "x-custom/foo", "value": "iVBORw0KGgo="},
        },
    ),
    (
        "run-response.schema.json",
        "a media type carrying a facet and a structured suffix",
        {
            "postern": "0.1",
            "run_id": "01JD8XW2Q9",
            "output": {
                "type": "bytes",
                "media_type": "application/vnd.api+json",
                "value": "iVBORw0KGgo=",
            },
        },
    ),
]

MUST_REJECT = [
    (
        "stream-event.schema.json",
        "a step reporting elapsed time on a step that has only started",
        {"name": "research", "status": "started", "latency_ms": 0},
    ),
    (
        "stream-event.schema.json",
        "a step event with no status, which cannot say which edge it is",
        {"name": "research", "model_id": "gpt-4o-mini"},
    ),
    (
        "run-response.schema.json",
        "an output type outside the v0 set, which no runner may emit",
        {
            "postern": "0.1",
            "run_id": "01JD8XW2Q9",
            "output": {"type": "image", "value": "iVBORw0KGgo="},
        },
    ),
    (
        "run-response.schema.json",
        "a bytes output with no media_type, which no client could place",
        {
            "postern": "0.1",
            "run_id": "01JD8XW2Q9",
            "output": {"type": "bytes", "value": "iVBORw0KGgo="},
        },
    ),
    (
        "run-response.schema.json",
        "a media_type whose subtype does not start alphanumeric, which "
        "RFC 6838 section 4.2 forbids",
        {
            "postern": "0.1",
            "run_id": "01JD8XW2Q9",
            "output": {"type": "bytes", "media_type": "image/!weird", "value": "iVBORw0KGgo="},
        },
    ),
    (
        "run-response.schema.json",
        "a media_type carrying upper case, which a runner does not emit",
        {
            "postern": "0.1",
            "run_id": "01JD8XW2Q9",
            "output": {"type": "bytes", "media_type": "Image/PNG", "value": "iVBORw0KGgo="},
        },
    ),
    (
        "describe.schema.json",
        "a declared bytes output with no media_type",
        {
            "postern": "0.1",
            "agent": {"id": "acme/chart", "name": "Chart", "version": "1.0.0"},
            "inputs": [],
            "output": {"type": "bytes"},
        },
    ),
    (
        "describe.schema.json",
        "an idempotent_retry that is not a boolean, which promises nothing readable",
        {
            "postern": "0.1",
            "agent": {"id": "acme/a", "name": "A", "version": "1"},
            "inputs": [],
            "capabilities": {"idempotent_retry": "yes"},
        },
    ),
    (
        "status.schema.json",
        "a runner declaring it accepts zero concurrent runs",
        {
            "postern": "0.1",
            "level": 3,
            "state": "ready",
            "limits": {"max_concurrent_runs": 0},
        },
    ),
    (
        "status.schema.json",
        "an update check reporting a version it never obtained",
        {
            "postern": "0.1",
            "level": 3,
            "state": "ready",
            "update": {"state": "unreachable", "current": "1.3.0", "latest": "1.4.0"},
        },
    ),
    (
        "status.schema.json",
        "a maximum run duration of zero seconds, which no run can meet",
        {
            "postern": "0.1",
            "level": 3,
            "state": "ready",
            "limits": {"max_run_seconds": 0},
        },
    ),
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


# The specification version is mirrored in three shapes: a `postern` member,
# the version segment of a schema `$id`, and prose. VERSIONING.md requires the
# first two to track the specification version exactly, so a bump is either
# complete or wrong — there is no state in which some of these are right.
#
# The first two are found by pattern rather than listed, so a file added later
# is covered without anyone remembering to come back here. Prose has no shape
# to match on, so those three are named.
_VERSION_IN_ID = re.compile(r"/schemas/postern/([^/]+)/")
_VERSION_IN_FIELD = re.compile(r'"postern":\s*"([^"]*)"')

# VERSIONING.md writes the `$id` shape out with the version as a placeholder.
# It is documenting the form, not mirroring the value.
_VERSION_PLACEHOLDER = re.compile(r"^<.+>$")

_VERSIONED_SUFFIXES = {".json", ".md", ".txt", ".yml", ".yaml"}

_VERSION_IN_PROSE = [
    ("SPEC.md", re.compile(r"^\*\*Version (\S+) · Draft\*\*", re.MULTILINE)),
    ("README.md", re.compile(r"· Version (\S+) · Draft ·")),
    ("README.md", re.compile(r"Version (\S+) is\s+drafted\s+in the open")),
]


# Where each schema keeps the agent identifier. Two shapes, one grammar.
_IDENTIFIER_POINTERS = {
    "describe.schema.json": ("agent", "id"),
    "status.schema.json": ("agent", "id"),
    "entitlement.schema.json": ("agent_id",),
    "version.schema.json": ("agent_id",),
}


def _media_type_pattern() -> bool:
    """`describe` and `run-response` both bound `output.media_type`, and the
    two must agree.

    The same reasoning as the identifier grammar below, one field over: a
    runner declares the media type it will emit and then emits it, so a
    `describe` that admits a value `run-response` refuses would let a runner
    promise something it cannot deliver — and the two documents are edited
    at different times, by whoever is fixing whichever one they hit.

    Returns True when they disagree, so callers can accumulate.
    """
    carried = {}
    for name in ("describe.schema.json", "run-response.schema.json"):
        node = _load("schemas", name)["properties"]["output"]["properties"]["media_type"]
        carried[name] = node.get("pattern")

    if len(set(carried.values())) != 1:
        print("FAIL  describe and run-response bound media_type differently")
        for name, pattern in sorted(carried.items()):
            print(f"        {name}: {pattern}")
        return True

    print("ok    both schemas bound media_type the same way")
    return False


def _identifier_pattern() -> bool:
    """SPEC.md §1.5 publishes the agent identifier grammar as a regular
    expression, and four schemas carry it as a `pattern`. Five copies of one
    rule is five places to edit and four chances to forget, and the symptom of
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

    print("ok    SPEC.md and all four schemas carry one agent id pattern")
    return False


def _version_mirrors() -> bool:
    """One specification version, written in more places than fit in a head.

    VERSIONING.md requires the `postern` member and the schema `$id` to track
    the specification version exactly. Nothing enforced that, and the mirrors
    outnumber the places anyone thinks to look — a change list written by hand
    during review named four of the seven files under examples/ alone. The
    ones that get missed are the ones no other check reaches: examples/
    stream.txt carries a version inside an SSE payload that has no schema,
    schemas/README.md cites an `$id`, and prose mentions it three times.

    The schemas' `postern` const is the anchor rather than one more mirror to
    compare. It is the one already protected — every example validates against
    it — so a const that moved alone has failed further up this run, and
    measuring the rest against it means this check has a single opinion about
    what the version is.

    Returns True when a mirror disagrees, so callers can accumulate.
    """
    anchors = {}
    for path in sorted(ROOT.glob("schemas/*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        const = schema.get("properties", {}).get("postern", {}).get("const")
        if const is not None:
            anchors[path.name] = const

    if not anchors:
        print("FAIL  no schema declares a postern const to measure against")
        return True

    if len(set(anchors.values())) != 1:
        print("FAIL  the schemas do not agree on the specification version")
        for name, const in sorted(anchors.items()):
            print(f"        {name}: {const}")
        return True

    version = next(iter(anchors.values()))
    found = []

    for directory, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(name for name in dirnames if name != ".git")
        for filename in sorted(filenames):
            path = pathlib.Path(directory, filename)
            if path.suffix not in _VERSIONED_SUFFIXES:
                continue
            where = path.relative_to(ROOT)
            lines = path.read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, 1):
                for pattern in (_VERSION_IN_ID, _VERSION_IN_FIELD):
                    for value in pattern.findall(line):
                        if _VERSION_PLACEHOLDER.match(value):
                            continue
                        found.append((f"{where}:{number}", value))

    for name, pattern in _VERSION_IN_PROSE:
        source = ROOT.joinpath(name).read_text(encoding="utf-8")
        matches = list(pattern.finditer(source))
        if not matches:
            print(f"FAIL  {name} carries no version marker matching this check")
            print(f"        looked for: {pattern.pattern}")
            print("        Reword the file or _VERSION_IN_PROSE, not neither.")
            return True
        for match in matches:
            line = source.count("\n", 0, match.start()) + 1
            found.append((f"{name}:{line}", match.group(1)))

    drifted = sorted((where, value) for where, value in found if value != version)
    if drifted:
        print(f"FAIL  the schemas say version {version}, and these do not:")
        for where, value in drifted:
            print(f"        {where}: {value}")
        return True

    print(f"ok    {len(found)} mirrors of the specification version say {version}")
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


# docs/ carries non-normative pictures of the specification, and the section
# numbers are the only thing tying each one to the text that governs it.
SECTION_REF = re.compile(r"§(\d+(?:\.\d+)*)")
SPEC_HEADING = re.compile(r"^#{2,4}\s+(\d+(?:\.\d+)*)\.?\s", re.MULTILINE)


def _docs_cite_real_sections() -> bool:
    """Every section docs/ points at is a section SPEC.md still has.

    The pages under docs/ are non-normative, which is exactly what makes a
    stale reference there cheap to leave in and expensive to follow. A reader
    who clicks through to a numbered section and finds something else has been
    told the picture is out of date, without being told how far — and unlike
    the schemas, nothing else in this repository reads those numbers.

    Renumbering is the edit this catches. Adding a section is harmless and
    rewording one is invisible here, but §5.3.1 was inserted below a §5.3 that
    was already being cited, and the next insertion is the one that moves a
    number somebody drew a diagram around.

    Returns True when a reference resolves to nothing, so callers can
    accumulate.
    """
    headings = set(SPEC_HEADING.findall((ROOT / "SPEC.md").read_text(encoding="utf-8")))

    pages = sorted(
        path
        for path in (ROOT / "docs").rglob("*")
        if path.suffix in {".md", ".html"}
    )
    if not pages:
        print("ok    docs/ has no pages to check")
        return False

    failed = False
    for path in pages:
        cited = set(SECTION_REF.findall(path.read_text(encoding="utf-8")))
        missing = sorted(
            cited - headings, key=lambda ref: [int(part) for part in ref.split(".")]
        )
        where = path.relative_to(ROOT)
        if missing:
            failed = True
            named = ", ".join("§" + ref for ref in missing)
            print(f"FAIL  {where} cites sections SPEC.md does not have: {named}")
        else:
            print(f"ok    {where} — {len(cited)} section references resolve")

    return failed


# A length cited in prose: `1,913 lines`, or `1913 lines` once someone drops
# the comma. Three digits at least. The bound is what keeps an incidental
# "8 lines" of an example from being read as a claim about the document, and
# it costs nothing real — SPEC.md passed a thousand lines before this check
# existed, and a specification that shrank below a hundred would be a
# different document.
_DOCS_LINE_COUNT = re.compile(r"\b(\d{1,3}(?:,\d{3})+|\d{3,})\s+lines\b")


def _docs_cite_the_real_length() -> bool:
    """Every line count docs/ cites is SPEC.md's real one.

    docs/README.md states the length twice and docs/flow.html opens with it a
    third time. All three are hand-maintained, every edit to SPEC.md
    invalidates them, and until now nothing read them — so they rotted twice,
    and both repairs rode along with changes that were not about them. The
    first citation is the one doing real work: it is the reader's estimate of
    what they are about to commit to.

    Every page under docs/ is swept rather than the two that cite a length
    today, because the next citation is the one added somewhere nobody
    thought to watch.

    Matching nothing at all is a failure rather than a pass, for the reason
    _version_mirrors gives one check up: a check with nothing to assert
    reports exactly like one that holds. Rewording every citation away is
    allowed and has to be deliberate — reword this check with them.

    A count that is not SPEC.md's is reported rather than guessed at. Prose
    citing some other file's length would fail here, which is the safe
    direction: the failure is loud and the fix is one line, where a check
    tuned to allow it would be silently narrower than it reads.

    Returns True when a citation has rotted, so callers can accumulate.
    """
    length = len((ROOT / "SPEC.md").read_text(encoding="utf-8").splitlines())

    pages = sorted(
        path
        for path in (ROOT / "docs").rglob("*")
        if path.suffix in {".md", ".html"}
    )

    failed = False
    cited = 0
    for path in pages:
        where = path.relative_to(ROOT)
        source = path.read_text(encoding="utf-8")
        for match in _DOCS_LINE_COUNT.finditer(source):
            cited += 1
            claimed = int(match.group(1).replace(",", ""))
            if claimed != length:
                failed = True
                line = source.count("\n", 0, match.start()) + 1
                print(
                    f"FAIL  {where}:{line} says SPEC.md is {match.group(1)} lines; "
                    f"it is {length:,}"
                )

    if not cited:
        print("FAIL  no page under docs/ cites SPEC.md's length any more")
        print(f"        looked for: {_DOCS_LINE_COUNT.pattern}")
        print("        Reword the pages or this check, not neither.")
        return True

    if not failed:
        print(f"ok    docs/ — {cited} citations of SPEC.md's length say {length:,}")
    return failed


# examples/stream.txt is the only example that is not a JSON document, and it
# was the only one nothing checked. Its payloads are JSON all the same, and the
# rule that matters most in §4.3 — deltas concatenating to the final output —
# is invisible to every schema here, because it spans events rather than
# sitting inside one. The transcript asserts it in prose in its own Notes
# section, which is exactly the kind of claim that rots.
_SSE_EVENT = re.compile(r"^event:\s*(\S+)\s*\n^data:\s*(.+)$", re.MULTILINE)

# Which schema answers for each event name. `done` and `error` carry bodies
# defined elsewhere, which is why they are not in stream-event.schema.json.
_EVENT_SCHEMAS = {
    "start": ("stream-event.schema.json", "start"),
    "step": ("stream-event.schema.json", "step"),
    "delta": ("stream-event.schema.json", "delta"),
    "done": ("run-response.schema.json", None),
    "error": ("error.schema.json", None),
}


def _subschema(schema: dict, pointer: str | None) -> dict:
    """The whole schema, or one $def of it addressed by name.

    Written as a $ref into the document rather than by lifting the $def out,
    so a $def that refers to a sibling keeps resolving.
    """
    if pointer is None:
        return schema
    return {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": f"#/$defs/{pointer}",
    }


def _stream_transcript() -> bool:
    """Read examples/stream.txt as a transcript, not as documentation.

    Two things are asserted. Every `data:` payload validates against the
    schema for its own `event:` name — so a transcript showing a payload no
    runner may emit fails here rather than teaching it to someone. And the
    `delta` texts concatenate to `done`'s `output.value`, which is §4.3's
    load-bearing invariant and the one thing JSON Schema cannot see: it holds
    across events, so no document-shaped check can reach it.

    Returns True on failure, so callers can accumulate.
    """
    source = ROOT.joinpath("examples", "stream.txt").read_text(encoding="utf-8")
    events = _SSE_EVENT.findall(source)
    if not events:
        print("FAIL  examples/stream.txt carries no event:/data: pairs")
        print("        Reword the transcript or _SSE_EVENT, not neither.")
        return True

    failed = False
    deltas: list[str] = []
    final: str | None = None

    for name, payload in events:
        where = f"examples/stream.txt event:{name}"
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            failed = True
            print(f"FAIL  {where} is not valid JSON: {exc}")
            continue

        if name not in _EVENT_SCHEMAS:
            failed = True
            print(f"FAIL  {where} is an event name nothing here answers for.")
            print("        Add it to _EVENT_SCHEMAS, or to §4.3's table first.")
            continue

        schema_name, pointer = _EVENT_SCHEMAS[name]
        validator = jsonschema.Draft202012Validator(
            _subschema(_load("schemas", schema_name), pointer),
            format_checker=FORMAT_CHECKER,
        )
        errors = sorted(validator.iter_errors(document), key=lambda e: e.path)
        if errors:
            failed = True
            print(f"FAIL  {where} -> schemas/{schema_name}")
            for error in errors:
                location = "/".join(str(part) for part in error.path) or "(root)"
                print(f"        {location}: {error.message}")
            continue

        if name == "delta":
            deltas.append(document["text"])
        elif name == "done":
            final = document["output"]["value"]

    print(f"ok    examples/stream.txt — {len(events)} event payloads validate")

    if deltas and final is None:
        failed = True
        print("FAIL  examples/stream.txt emits deltas and never reaches done")
    elif deltas:
        joined = "".join(deltas)
        if joined != final:
            failed = True
            print("FAIL  examples/stream.txt deltas do not rebuild output.value")
            print(f"        deltas  -> {joined!r}")
            print(f"        done    -> {final!r}")
        else:
            print(
                f"ok    examples/stream.txt — {len(deltas)} deltas"
                " rebuild output.value"
            )

    return failed


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

    for schema_name, description, payload in MUST_ACCEPT:
        validator = jsonschema.Draft202012Validator(
            _load("schemas", schema_name), format_checker=FORMAT_CHECKER
        )
        errors = list(validator.iter_errors(payload))
        if errors:
            failed = True
            print(f"FAIL  {schema_name} rejects {description}: {errors[0].message}")
        else:
            print(f"ok    accepts {description}")

    for rule, description, payload in INVARIANT_MUST_FLAG:
        if rule(payload):
            print(f"ok    flags {description}")
        else:
            failed = True
            print(f"FAIL  {rule.__name__} misses {description}")

    print()
    failed |= _media_type_pattern()
    failed |= _identifier_pattern()
    failed |= _version_mirrors()

    print()
    failed |= _stream_transcript()

    print()
    failed |= _docs_cite_real_sections()
    failed |= _docs_cite_the_real_length()

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
