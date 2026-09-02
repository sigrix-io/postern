# postern-conformance

Points at a running [Postern](https://github.com/sigrix-io/postern) runner
and reports which of the specification's three conformance levels it
actually meets — and which of its MUST rules the runner breaks getting
there.

```console
$ pip install postern-conformance
$ postern-conformance http://127.0.0.1:8787
```

```
Postern conformance · http://127.0.0.1:8787
schemas: checkout

  §4.4
    PASS  status answers without credentials
    PASS  status matches its schema
  §3
    PASS  declares Level 3
          Stream — describe, status, run, stream
    PASS  run is implemented at Level 3
  §2.3
    PASS  no wildcard Access-Control-Allow-Origin by default
    PASS  run rejects a non-JSON media type
  …

Declared level: 3
34 pass  0 fail  0 warn  2 skip

Conformant at Level 3.
```

Postern is four HTTP endpoints, so this checker speaks to a runner over the
wire and has no idea what it is written in. A Go, Rust or TypeScript runner
is checked exactly as well as a Python one.

## It does not run your agent unless you ask

A run may invoke tools that spend money and mutate state outside the
workspace ([§4.1.2](../../SPEC.md#412-capabilitieswrite_tools)), and an
abort is not a rollback ([§4.5](../../SPEC.md#45-the-life-of-a-run)). A
conformance checker that ran an agent to find out whether it conforms would
be charging you for the answer, and would have done so before you could
read this.

So by default it checks only rules a runner applies **before** the agent
starts — which is most of the specification:

- the level rule, in full, because a verb above the runner's level must
  refuse and so executes nothing
- every refusal path: a malformed body, a missing required input, a
  revoked entitlement, a media type the runner must not parse
- `describe` and `status` entirely, along with their schemas
- the CORS rules, none of which involve running anything

`--execute` opts into the rest — the `run` response shape, the SSE framing,
the `delta` concatenation invariant, `run_id` uniqueness, and — for a runner
declaring `capabilities.idempotent_retry` — that a key already answered is
refused rather than replayed when it arrives carrying different `inputs`.
There is no way to check those without a real run, which is why they are a
decision rather than a default.

The last of those spends nothing of its own: it presents the key the
uniqueness check already bound, and a conformant runner refuses it without
running the agent. It rides on `--execute` because the key has to have been
bound by a real run first, not because it buys another.

## Usage

```console
postern-conformance http://127.0.0.1:8787
postern-conformance http://127.0.0.1:8787 --origin https://app.example.com
postern-conformance http://127.0.0.1:8787 --execute
postern-conformance http://127.0.0.1:8787 --json
```

`--origin` names an origin the runner is configured to allow. Without it
the CORS *header* rules are skipped: which origins a runner allows is the
runner's own decision, and the specification fixes only the two ends of it
([§2.3](../../SPEC.md#23-browser-clients)). The rules that hold for *any*
origin — no wildcard default, no `Origin: null` — are checked either way.

| Exit | Meaning |
|---|---|
| 0 | No MUST rule was broken |
| 1 | At least one MUST rule was broken |
| 2 | The runner could not be checked at all |

**A SHOULD cannot fail the run.** It reports as `WARN` and the exit status
stays 0. A checker that failed a runner for declining an option the
specification left open would be ignored, and its MUSTs would be ignored
with it.

## What a PASS is worth

Two limits, both of which the tool states in its own output rather than
leaving you to discover:

- **A pass is not a proof for a rule with two right answers.** The default
  `text/plain` probe sends a body the runner must reject anyway, so a
  runner that wrongly parses `text/plain` still answers `400` and still
  passes. `--execute` is what makes that one conclusive. The self-test
  below asserts this rather than assuming it — the fault is planted, and
  the default probe is confirmed *not* to catch it.
- **`describe` being side-effect free cannot be observed from outside.**
  Two identical calls returning identical bytes is evidence, so a
  difference warns; it is not a breach this tool can stand behind.

Rules are checked against the specification's own
[`schemas/`](../../schemas) rather than restated in Python, so a schema and
this checker cannot drift. Running from a checkout uses that checkout's
schemas; an installed wheel carries a copy. Every report says which it
used.

## Proving the checks can fail

The failure mode of a conformance checker is a false green: every check
reads correctly, passes against a real implementation, and would have
passed just as happily against a runner that did none of it.

```console
$ python tools/conformance/selftest.py
postern-conformance self-test

  19 conformant baselines, none failing
  11 error codes, table agrees with the schema
  6 schemas, the build hook bundles each one
  34 planted faults, each caught by its own check

Every check can fail.
```

It runs the checker against a deliberately conformant fake runner, where
nothing may fail, and then against the same runner with exactly one rule
broken — asserting that the *named* check catches it, not merely that
something did. Standard library only; it needs no runner and no network.

## Why this is not called `postern`

[CONTRIBUTING.md](../../CONTRIBUTING.md) puts a language SDK out of scope,
and the reasoning holds: Postern is HTTP, any language can serve or call
it, and publishing a Python client under the specification's own name would
make one language the blessed one for a document whose whole claim is that
none is.

This is a test suite rather than a client library, and it deliberately
leaves the name a Python client would want free for whoever writes one
under their own.

## Changes

### 0.1.1

**A runner that reported clean under 0.1.0 may report findings here.** That
is the intent rather than a regression: the specification was clarified in
four places and the suite followed. Read a new finding as a rule that was
always there and is only now being checked.

- **§4.6 is checked at all.** A `run` missing a required input, sent to a
  runner whose environment is incomplete, earns both `bad_request` and
  `missing_credential`, and the specification did not order them — so this
  suite *skipped* §4.2's rule whenever a runner answered `424`, which is the
  ordinary state of one being brought up. §4.6 now orders them, and the
  `424` is a finding.
- **A reused `Idempotency-Key` carrying different inputs must be refused**,
  not replayed.
- **`run_id` is per execution**, quoting §4.2's own wording.
- **`capabilities.streaming` is withdrawn** and no longer checked.

### 0.1.0

First release. 5 conformant baselines, 22 planted faults.

## Status

The specification is a draft and nothing in it is stable yet, so neither is
this. It tracks Postern 0.1.

Apache-2.0, same as the specification.
