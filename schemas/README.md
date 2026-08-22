# Schemas

Machine-readable forms of the payloads [SPEC.md](../SPEC.md) defines — one
per payload, plus the error envelope. [`examples/`](../examples) carries a
worked instance of each.

## They describe what a conforming implementation *emits*

**A client MUST NOT use these to reject a response it received.** They are
the emit-side contract, and the specification is explicit that accepting is
a wider question than emitting ([§2.1](../SPEC.md#21-errors)):

> The schema in `schemas/` enumerates the codes a conforming implementation
> *emits*, which is a narrower question than the set a client **MUST**
> accept.

Three places where that difference is load-bearing, and all three are ones a
generated parser gets wrong by default:

- **`error.code` is a closed enum.** §2.1 requires a client to treat an
  unrecognised code as a generic failure of its HTTP status class. New codes
  may be added in a minor release.
- **`error.schema.json` is closed at its root** — the only schema here that
  is. §2.1 requires a client not to reject a response for carrying a sibling
  of `error`.
- **`output.type` is a closed enum, and the one unknown a client may not
  ignore either.** §4.1.4 requires a client not to reject an output type it
  does not recognise — and, unlike the two above, not to shrug it off: it
  **MUST NOT** present `value` as text. A generated parser gets this wrong
  in both directions at once, rejecting what it should accept and, once
  relaxed, reading bytes it cannot interpret as prose.

So generating client types from these files produces a parser that rejects
exactly what the specification spends three rules forbidding it to reject —
the parser [VERSIONING.md](../VERSIONING.md#before-10) describes, where *"a
parser that rejects an unrecognised field converts every future minor
release into a breaking one for its users."* Generate from them freely;
relax both before shipping.

There are no lenient mirrors of these files, deliberately. A second set
would double the surface that has to stay in step, which is the drift
[`scripts/validate.py`](../scripts/validate.py) exists to prevent.

## Identifiers

Each schema declares an `$id` under
`https://sigrix.io/schemas/postern/0.1/`. Those are permanent names, and the
four commitments that come with them — including that a new specification
version publishes a new directory rather than editing one in place — are in
[VERSIONING.md](../VERSIONING.md#schema-identifiers). The files here are
usable without ever fetching one.

## Checking them

`scripts/validate.py` validates every example and every fenced JSON block in
SPEC.md against these, then asserts the invariants JSON Schema cannot
express — `write_tools` being a subset of `tools`, among others. Run it
before pushing; CI runs it on every pull request.

```bash
pip install -r ../scripts/requirements.txt
python ../scripts/validate.py
```

See [CONTRIBUTING.md](../CONTRIBUTING.md) for what else a change to these
files is expected to carry.
