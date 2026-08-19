# Versioning and compatibility

## Where the version lives

Four places, and they move at different speeds:

| Version | Example | Changes when |
|---|---|---|
| **Specification version** | `0.1` | Any change to this document's normative content. |
| **Path prefix** | `/postern/v0/` | Only on a breaking revision. `v0` covers every `0.x`. |
| **`postern` field** in payloads | `"postern": "0.1"` | Tracks the specification version exactly. |
| **Schema `$id`** | `https://sigrix.io/schemas/postern/0.1/describe.schema.json` | Tracks the specification version exactly. A new version publishes a new directory; see below. |

A client reads the `postern` field to know what it is talking to. It **must
not** infer the specification version from the path prefix, which is
deliberately coarser.

## Before 1.0

**Nothing is stable. Any `0.x` release may break any other `0.x` release.**

This is stated plainly because the alternative — implying stability we
cannot yet promise — is how a specification acquires dependents it then has
to betray. Postern 0.1 is published early on purpose: feedback is cheapest
while changing things is still free, and that is only true if everyone knows
it is still true.

Concretely, before 1.0:

- Fields may be renamed, retyped, or removed.
- Verbs may change shape. They will not grow in number (see below).
- The path prefix stays `/postern/v0/` throughout. It is not a stability claim.
- Every breaking change is listed in [Appendix A of the
  specification](SPEC.md#appendix-a--changes) with a migration note.

If you are building on `0.x`, please [open an issue](../../issues) saying
so. The practical difference between a breaking change that is announced and
one that is discovered is knowing you exist.

## After 1.0

Semantic versioning, applied to the wire contract:

- **Major** — a conforming client of the previous major may stop working.
  New path prefix.
- **Minor** — additive only. New optional fields, new event types, new
  conformance levels. A conforming implementation of `1.n` remains
  conforming under `1.n+1`.
- **Patch** — clarification, typos, worked examples. No normative change.

Two rules make "additive only" mean something:

1. **Unknown members are ignored, never rejected.** Required of clients and
   runners in several places in the specification. A parser that rejects an
   unrecognised field converts every future minor release into a breaking
   one for its users.
2. **Optional stays optional.** Promoting an existing optional field to
   required is a major change, however obvious the field has become.

## Schema identifiers

Every schema in [`schemas/`](schemas) declares an `$id` on `sigrix.io`, at
`/schemas/postern/<specification version>/<file name>` — the table above has a
worked one. Four commitments come with that, written here rather than in the
schemas because the person who needs them is a maintainer two years from now.

**The base is a name, not an endorsement.** These identifiers resolve on
`sigrix.io` because Sigrix authored Postern and can commit to serving them for
as long as the specification exists — and an identifier that nobody serves is
worse than one shaped like a vendor. It creates no dependency in either
direction: the schemas ship in [`schemas/`](schemas) and are usable without
ever fetching one, [§5.1](SPEC.md#51-the-distributor-is-optional) makes a
distributor optional outright, and [§8](SPEC.md#8-sigrix-profile) is a profile
any distributor may ignore. Nothing in the protocol requires a Sigrix service,
and the base does not change that.

**The version in the path is the specification version**, exactly as the
`postern` field is, and unlike the `/postern/v0/` path prefix, which is
deliberately coarser. A new specification version publishes a new directory
beside the old one. It does not edit one in place.

**A published `$id` is permanent.** The document at it may be corrected; the
identifier is never reused for anything else, and never withdrawn. It is the
one thing here that cannot be walked back — an implementation that stored a
reference cannot be told the name moved — which is why the base was settled
before publication rather than after.

**They are meant to resolve.** JSON Schema does not require an `$id` to be
dereferenceable, and Postern's schemas are usable from
[`schemas/`](schemas) without ever fetching one. But publishing an
`https://` URI invites the assumption that it answers, and a 404 reads as a
broken specification rather than an unhosted one. Serving these files at
that base is therefore a maintenance obligation, and
[`scripts/check_links.py`](scripts/check_links.py) checks it weekly.

> **Not true yet.** The files are not served at that base as this is written.
> Serving them is a prerequisite for making the repository public, because a
> published `$id` cannot move afterwards. Until then the weekly link job is
> red on these URLs, on purpose and with a note saying so.

## The four-verb ceiling

`describe`, `run`, `stream`, `status`. **This number is a governance
constraint, not a stage of development.**

The reasoning is compatibility arithmetic rather than minimalism for its own
sake. Every published verb is a permanent obligation — to every agent that
implements it and every client that pins to its shape — and that obligation
does not scale down when the team maintaining it is small. A four-verb
contract that stays compatible for a decade is worth more to everyone
building on it than a forty-verb one that fractures in two years.

So a proposal to add a fifth verb is not a feature request to be triaged. It
reopens the decision that made publishing this specification responsible in
the first place, and will be treated that way: it needs to argue that the
capability cannot be expressed within the existing four, and that the
resulting maintenance load is carryable.

Extending *within* the four verbs is ordinary work and is welcome — new
optional `describe` fields, new `stream` event types, new `validation`
members. That is where the growth is supposed to go, and the
ignore-unknown-members rule above is what keeps it cheap.

## The name

`Postern` is not only what this repository is called. It is in the path
prefix every request carries (`/postern/v0/`), in the `postern` field of
every payload, and in the schema `$id` base — so it is load-bearing in the
wire format, and renaming it would break every conforming implementation at
once. It belongs here for the same reason the ceiling above does: it is
permanent, and the argument for it should outlive whoever made it.

**The descriptive name was already taken, in an adjacent area.** This first
drafted as "AEP — the Agent Execution Protocol", which is the obvious name
and the wrong one. `draft-sato-soos-aep`, *"The Agent Execution Protocol
(AEP) for Agentic AI Systems"*, is an active IETF draft specifying a
governance loop — SENSE, REASON, PLAN, ACT, OBSERVE — with authorization
boundaries and policy-driven approval at execution time. AceTeam publishes
an "Agentic Execution Protocol" under the same three letters. A third AEP
that also touches authorization would be permanently second in search for
its own name, and genuinely confusable with a governance specification that
is not this one.

**A ninth acronym would be camouflage.** The surrounding landscape already
carries MCP, A2A, ACP, ANP, AP2, UCP, OASF and KYA-OS. MCP won on being
early and well-backed rather than on its name; a new three-letter
descriptive acronym in that field is invisible.

**The infrastructure names that stick are concrete object nouns** carrying a
descriptive tagline for the search terms — Vault, Consul, Nomad, Boundary,
Waypoint, Sigstore. Postern follows that pattern, and the tagline is the
subtitle on the README. A postern is the small gate in a fortification
through which authorised people pass: present proof, pass through, then run.
Collisions are limited to a dormant API-mocking tool.

Animal names were considered and rejected on availability — Pangolin already
names three significant projects, Kestrel is ASP.NET Core's web server,
Marten a .NET document database, and Tapir a Scala HTTP-endpoint library,
which would have collided thematically as well as by name.

A proposal to rename this to something more descriptive is welcome to argue
its case. It should start from the above rather than from the premise that
nobody considered it.

## Deprecation

A deprecated element is marked in the specification, kept working for at
least one minor release, and removed no earlier than the next major. Nothing
is removed in the release that deprecates it.
