# Postern

**The open execution and entitlement protocol for packaged AI agents** — a
small HTTP contract for running one as a local process, and for checking
that whoever is running it is allowed to.

*A postern is the small gate in a fortification that authorised people pass
through. Present proof, pass through, then run.*

📄 **[Read the specification →](SPEC.md)** · Version 0.1 · Draft ·
[Apache-2.0](LICENSE)

---

## What problem this solves

You bought or downloaded an AI agent. It is a folder on your machine. Now
what?

Today the answer is different for every agent: read its README, install its
dependencies, find out what it expects as input, work out how to run it,
discover afterwards which API keys it needed. Every client that wants to
offer a nicer experience than a terminal has to hard-code that knowledge per
agent, which means nobody does it.

Postern fixes the interface, not the agent. An agent that speaks Postern can
say what it takes and produce what it returns, over four HTTP endpoints:

| Verb | Does |
|---|---|
| `describe` | What inputs does this take, what does it return, which credentials does it need, which of its tools cost money |
| `run` | Run it, give me the result |
| `stream` | Run it, show me as it goes |
| `status` | Is it healthy, am I still allowed to run it |

Anything that can call HTTP can be a client — a CLI, an IDE plugin, a web
UI, another agent. Anything that can serve HTTP can be an agent, in any
language. No SDK is required, and none is planned; if you want one for your
language, the specification is right there and pull requests are welcome.

A web UI is the one of those with a condition attached, because a browser
will not let a page read a local runner's answer unless the runner allows
the page's origin. [§2.3](SPEC.md#23-browser-clients) says what a runner
owes a browser client, and why the default is to refuse: a runner defines
no authentication, so an origin check is the only thing standing between
`run` and every page the user happens to visit.

```mermaid
flowchart LR
    C["<b>Client</b><br/>CLI · IDE plugin · web UI<br/>another agent"]
    R["<b>Runner</b><br/>one agent, one port"]
    D["<b>Distributor</b><br/>optional"]
    E["<b>Machine environment</b><br/>OPENAI_API_KEY, ..."]

    C -->|"describe · status · run · stream<br/>loopback · no auth defined · no agent id"| R
    R -->|"entitlements · bundles<br/>HTTPS · Authorization: Bearer"| D
    E -.->|"values load here, and cross<br/>neither edge above"| R
```

The dotted edge is the one that carries no protocol traffic, and it is the
subject of the next two sections. More diagrams, including the entitlement
state machine, are in [`docs/`](docs).

## What it does not do

Postern does not define a packaging format. Agents are packaged as [Agent
Plugins v1.0.0](https://agent-plugins.org) plugins — the vendor-neutral
standard governed by Amazon, Microsoft, OpenAI, Cursor, Vercel and Google.
Postern adds no files to that layout.

It also does not define tool calling (use
[MCP](https://modelcontextprotocol.io)), model APIs, agent frameworks,
orchestration between agents, or hosting.

**Four verbs is a ceiling, not a starting point.** A protocol that can be
kept compatible by a small team beats a complete one that cannot. See
[VERSIONING.md](VERSIONING.md).

## The part nobody else specifies

Agent Plugins v1.0.0 says of itself that *licensing is metadata only; no
portable verification mechanism defined.* MCP does not address it either.

So if you sell an agent, or run one you paid for, there is no standard
answer to "how does this thing check I'm entitled to it, and what happens
when I get a refund." [§5 of the specification](SPEC.md#5-entitlement) is
that answer: opaque bearer tokens, hashed at rest, a per-agent check with a
declared staleness bound, and a rule that revocation windows must be
published rather than pretended away.

Two properties of that design are worth stating up front, because they are
constraints on implementers rather than features:

- **Credentials never traverse the protocol.** An agent declares the
  environment variable *names* it needs. A bundle carrying a credential
  *value* is nonconformant. There is nowhere in Postern for a secret to travel,
  which is what makes "your keys stay on your machine" checkable instead of
  promised.
- **Not-entitled is indistinguishable from not-found.** A distributor
  answers `404`, never `403`, so the entitlement endpoint cannot be used to
  enumerate a private catalogue. This costs a legitimate caller a worse
  error message, on purpose.

An agent that is free, self-authored, or local has no distributor and skips
all of this.

## Conformance

Three cumulative levels, so an agent that cannot stream — or cannot be run
by the caller at all — is still conformant and still describable:

| Level | Name | Verbs |
|---|---|---|
| 1 | Describe | `describe`, `status` |
| 2 | Execute | + `run` |
| 3 | Stream | + `stream` |

Machine-readable schemas are in [`schemas/`](schemas), worked payloads in
[`examples/`](examples), and diagrams of the whole surface in
[`docs/`](docs).

## Status

**This is a draft, and nothing in it is stable yet.** Version 0.1 is drafted
in the open, deliberately: a specification benefits most from being read
while changing it is still free. It is not released — there is no tag to pin
to, and until there is, changes land under *Unreleased* rather than moving
the version. Breaking changes will happen before 1.0, and
[VERSIONING.md](VERSIONING.md) says which of them move what.

There is no reference implementation in this repository. There is one
elsewhere: [Sigrix](https://sigrix.io) serves the four verbs at Level 3 for a
packaged agent, and the §5 endpoints as a distributor.

It is an implementation of this document rather than a second definition of
it — where the two appear to disagree, this document is what anyone pinned to,
and the disagreement is worth an issue here.

If you are building against this, please [open an
issue](../../issues) — knowing who depends on what is what lets us avoid
breaking you.

## Contributing

Issues and pull requests are welcome. Please read
[CONTRIBUTING.md](CONTRIBUTING.md) first — in particular the part about how
quickly you can expect an answer, which is written to be accurate rather
than flattering.

## License

[Apache-2.0](LICENSE). Published by [Sigrix](https://sigrix.io).
