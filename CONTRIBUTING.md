# Contributing

Thank you for looking. This document is deliberately blunt about what you
can expect, because a contribution guide that implies a service level nobody
staffed is worse than no guide at all.

## What to expect

**This specification is maintained by a very small team.** That shapes
everything below, and it is better said once here than discovered issue by
issue.

| | Realistic expectation |
|---|---|
| **Security reports** | Acknowledged within 72 hours. These jump every queue. |
| **Issues** | Read within a week. A reply may be "noted, not soon." |
| **Pull requests** | Reviewed within two weeks, often longer for anything normative. |
| **Silence** | Means the queue, not a verdict. Ping the thread. |

Merging is discretionary and stays with the maintainers. Contributions are
genuinely welcome; governance is not open. If that trade is not for you,
Apache-2.0 means you can fork this and go — no hard feelings, and please
tell us what we got wrong.

## Reporting a security issue

**Do not open a public issue.** Email **security@sigrix.io**, and expect an
acknowledgement within 72 hours.

[SECURITY.md](SECURITY.md) is the full policy: what is in scope, what is
not, which versions are supported, and what happens after you send it. It
lives in its own file because that is where GitHub points a reporter looking
for one, and a reporter who cannot find the private route uses the public
one.

The part worth repeating here: weaknesses in the *specification* are in
scope, not only bugs in something that runs. An entitlement flow that can be
bypassed, a rule that leaks catalogue contents, a token handling requirement
that is unsafe as written — those are the reports that matter most, because
they are inherited by every implementation that follows the document
faithfully.

## Before opening an issue

The tracker has a form for each of four kinds, because they are triaged
differently. Pick the one that fits and the form will ask for what that kind
needs; this section is why the four are separate.

- **A question.** Something in the specification is unclear. These are the
  most useful reports we get: ambiguity found by a reader is ambiguity
  found before it is baked into implementations.
- **A defect.** The specification is internally inconsistent, or requires
  something impossible, or two sections disagree.
- **A change.** You want Postern to do something it does not. Read the two
  sections below first.
- **"I depend on this."** Not a defect, and very welcome anyway. Knowing who
  is building on `0.x` is what lets us avoid breaking you silently. See
  [VERSIONING.md](VERSIONING.md).

There is no blank issue, and that is not a filter — every one of the four is
welcome. It is that "which of these is it" is the question the queue is
sorted by, and asking it on the way in costs you one click and saves a round
trip. A report that fits none of them is a question; file it as one and say
so.

## Proposing a change

The bar rises with how permanent the change is.

**Additive, within an existing verb** — a new optional `describe` field, a
new `stream` event type, a new `validation` member. Ordinary work, welcome.
Open an issue describing the use case; a pull request against
[SPEC.md](SPEC.md) is fine too.

**A fifth verb** — see the [four-verb
ceiling](VERSIONING.md#the-four-verb-ceiling). This reopens a governance
decision rather than requesting a feature, and needs to argue both that the
capability cannot be expressed within the existing four and that the
resulting permanent maintenance load is carryable. Please open an issue
before writing anything.

**Packaging** — out of scope. Agents are packaged as [Agent Plugins
v1.0.0](https://agent-plugins.org) plugins and Postern does not extend that
format. Distributor-specific data belongs in an `extensions` namespace you
control ([§6](SPEC.md#6-packaging)).

**A language SDK** — not something this repository will take on, and not
something you need our permission for. Postern is HTTP; any language can serve
or call it. Publish your SDK under your own name and open an issue so it can
be linked from here.

## Pull requests

The pull request template carries these four as a checklist, so they are in
front of you while you write the description rather than in a file you read
once. Here is why each is asked for.

- **One change per pull request.** A normative change bundled with typo
  fixes is hard to review and harder to revert.
- **Say what breaks.** If a change alters existing behaviour, say so in the
  description, in those words. Pre-1.0 this is allowed; unmentioned is not.
- **Update the examples and schemas.** [`examples/`](examples) and
  [`schemas/`](schemas) are normative-adjacent — a change that leaves them
  stale is incomplete. Check them before you push:

  ```bash
  pip install -r scripts/requirements.txt
  python scripts/validate.py
  ```

  It validates every example against its schema, and every fenced JSON
  block in [SPEC.md](SPEC.md) against its schema too — so the document you
  read and the files a validator reads cannot drift apart unnoticed. It then
  asserts that the rules which cost implementers something still fail when
  they are broken: `select` needing `options`, a credential never carrying a
  value, an `active` entitlement needing a declared staleness bound, the
  closed error-code set, the closed error-envelope root, and — because JSON
  Schema cannot express a subset relation between sibling arrays —
  `write_tools` being a subset of `tools`.

  A JSON block in [SPEC.md](SPEC.md) whose shape it does not recognise is a
  failure rather than a skip. If you add one, give it a mapping or an
  explicit reason to be skipped.
- **Expect the same check on your pull request.** `validate.py` runs in CI
  on every pull request, including from forks, against the same pinned
  `jsonschema` you installed above — so a stale schema is caught whether or
  not you remembered to run it. It is the only required check, and it needs
  no secrets, so nothing about your pull request has to be trusted for it to
  run.

  `scripts/check_links.py`, which checks that the URLs the specification
  cites still resolve, runs weekly on a schedule instead. Someone else's
  outage is not a reason to block your change. You can run it locally if you
  are touching links; it needs no dependencies.
- **Add an Appendix A entry** for anything normative.

## Writing style

The specification is meant to be read by someone implementing it at 2am.

- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) keywords in normative
  statements, and only there.
- **Say why, where the why is non-obvious.** Several rules in this
  specification cost implementers something — `404` instead of `403`, the
  declared staleness bound, the four-verb ceiling. Each carries its
  reasoning inline, because a rule whose cost is visible and whose benefit
  is not is a rule people quietly skip.
- Prefer a worked example to a paragraph.
- Present tense, active voice, no future promises.

## Code of conduct

[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) — the Contributor Covenant — applies
to every space this project uses.

Report conduct concerns to **conduct@sigrix.io**. That is a different address
from security reports and a different queue; neither is a fallback for the
other.

## License

Contributions are accepted under [Apache-2.0](LICENSE), the license of this
repository. Opening a pull request means you have the right to contribute
the work under it.
