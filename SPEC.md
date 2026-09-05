# Postern

**The open execution and entitlement protocol for packaged AI agents.**

**Version 0.1 · Draft**

Postern is a small HTTP contract for running a packaged AI agent as a local
process, and for checking that whoever is running it is allowed to.

*A postern is the small gate in a fortification that authorised people pass
through. That is the shape of this protocol: present proof, pass through,
then run.*

It has four verbs — `describe`, `run`, `stream`, `status` — and one
entitlement flow. That is the whole protocol, and keeping it that size is a
design constraint rather than an accident of being early (see
[VERSIONING.md](VERSIONING.md)).

---

## 1. Scope

### 1.1 What Postern specifies

1. **An execution surface.** How a client discovers what an agent takes as
   input, runs it, watches it run, and checks its health.
2. **An entitlement flow.** How a runner proves to a distributor that the
   person running an agent is entitled to it, and how that entitlement is
   withdrawn.

### 1.2 What Postern does not specify

Postern deliberately does not define a packaging format. Packaged agents
conform to [Agent Plugins v1.0.0](https://agent-plugins.org) — see §6.

It also does not define: model selection, prompt formats, agent frameworks,
orchestration between agents, tool protocols (use
[MCP](https://modelcontextprotocol.io)), hosting, deployment shape, payment,
or how a distributor decides who is entitled to what. A Postern server is a
process that answers on a port. Where that process runs, and what it wraps,
is out of scope.

**"Orchestration between agents" means the choreography, not the call.** An
agent may itself be a Postern client, and a system in which one agent calls
another is two ordinary Postern relationships rather than an exception to
this list — §2.2 says what that looks like in addressing terms. What is out
of scope is how agents discover one another, negotiate, hand off, share
state, or delegate authority between themselves. Postern assumes you already
have the agent and have already decided to call it.

### 1.3 Relationship to adjacent specifications

Postern is a narrow layer in a crowded stack, and it is easier to say what
it is by saying what it sits beside. Nothing below is a competitor; each
answers a different question.

| Specification | Answers | Postern's relationship |
|---|---|---|
| **[Agent Plugins v1.0.0](https://agent-plugins.org)** | How is an agent packaged? | Adopted verbatim. Postern defines no packaging (§6). |
| **[MCP](https://modelcontextprotocol.io)** | How does an agent reach tools and context? | Complementary. A Postern agent may use MCP internally; `describe` reports the tools it exposes. |
| **A2A** | How do two agents collaborate? | Orthogonal. Postern is one client talking to one agent. |
| **ACP / ANP** | How are agent messages routed and agents discovered? | Orthogonal. Postern assumes you already have the agent. |
| **OpenAI-compatible chat APIs** | How is one model call made? | Below Postern. A single `run` may make many. |
| **AP2, and agent-payment schemes generally** | How does an agent *make* a purchase? | The mirror image. Postern is about being licensed to run an agent, not about an agent buying something. |
| **Agent-identity work (DIF, KYA-OS)** | Is this agent who it claims to be? | Adjacent, different subject. Postern authorises the *human* running the agent. |

Agent Plugins v1.0.0 states that *licensing is metadata only; no portable
verification mechanism defined*. §5 of this document is the mechanism that
statement leaves open.

### 1.4 Terminology

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHOULD**,
**SHOULD NOT**, **MAY** and **OPTIONAL** are to be interpreted as described
in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

Three roles appear throughout:

- **Agent** — the packaged thing being run.
- **Runner** — the process that loads an agent and serves Postern. Also the
  party that holds an entitlement token.
- **Client** — anything that speaks Postern to a runner: a CLI, a UI, an IDE,
  another agent.
- **Distributor** — the party that issues entitlement tokens, answers
  entitlement checks and serves agent bundles. A marketplace, typically.
  A runner with no distributor is valid; see §5.1.

### 1.5 Agent identifiers

An **agent identifier** names one agent. The same identifier appears as
`agent.id` in `describe` (§4.1) and `status` (§4.4), as `agent_id` in an
entitlement answer (§5.3), and as the path addressing an agent on a
distributor (§5.3, §5.6). One agent, one identifier, spelled one way in all
four places.

```abnf
agent-id = part "/" part
part     = alnum [ *( alnum / "-" / "." ) alnum ]
alnum    = %x30-39 / %x61-7A   ; 0-9 a-z
```

The same grammar, as the regular expression the schemas carry:

```
^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?/[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$
```

An identifier **MUST** match it and **MUST NOT** exceed 128 characters.
`acme/market-research-crew`, used throughout this document, is valid under
it.

The owner part is what makes a name unique within a distributor without
having to be unique in the world. An identifier is unique within one
distributor; two distributors **MAY** issue the same identifier for
different agents, and an agent with no distributor (§5.1) still has one,
which is not required to be unique anywhere.

**Comparison is octet-for-octet**, once the grammar has been checked. There
is no case folding, because the grammar admits no uppercase. There is no
Unicode normalisation, because it admits nothing outside ASCII. There is no
collapsing of repeated separators, and no equivalence between `-` and `.`.
An implementation **MUST NOT** normalise a string into validity: `Acme/x` is
not another spelling of `acme/x`, and `acme/x ` is not `acme/x`. A string
either matches or is not an identifier at all.

Each exclusion removes a rule that two implementations could apply
differently, and an identifier that compares differently on two
implementations is an entitlement check that silently answers the wrong
question:

- **Uppercase**, because admitting it forces a case-folding rule at every
  comparison, in a comparison that decides whether a purchase is honoured.
- **`_`**, because the registries that admit both `_` and `-` fold one into
  the other, and a fold is the thing this grammar exists to avoid.
- **Everything outside ASCII**, because it brings normalisation forms and
  confusable characters with it.

A leading or trailing `-` or `.` is excluded by the grammar rather than by a
rule beside it, which is also what stops a part being `.` or `..` — the two
strings a URL path resolves away before a server sees them.

One length bound rather than two. A per-part bound would have to be written
here *and* expressed in the schema pattern, and a rule written twice is a
rule that can disagree with itself. 128 characters is the ceiling a
distributor is entitled to reject above, before an identifier reaches a
lookup or a storage layer.

Every character the grammar admits is unreserved in a URL path
([RFC 3986](https://www.rfc-editor.org/rfc/rfc3986#section-2.3)) except the
`/`, which is the separator it looks like. An identifier therefore appears
in a path exactly as it is written, and percent-encoding never arises;
§5.3.1 states what follows for the two distributor endpoints.

**An identifier names an agent; it does not classify one.** Nothing in the
grammar encodes a listing type, a tier, a plan, or any other distinction
internal to a distributor, and a distributor **MUST NOT** require one to be
encoded there. Where a distributor dispatches on such a distinction, it
resolves it on its own side from an identifier that does not carry it.

The alternative was to encode the type, which makes that dispatch free and
total. It was rejected because it puts a distributor's own catalogue model
into a public URL, and because re-typing a listing would then change its
identifier — an identifier §5.2's tokens, §6's bundles and every client's
stored state all point at. The cost of resolving instead is a step that can
miss, and that cost is paid in §5.5.

---

## 2. Transport

A runner **MUST** serve HTTP/1.1 over a TCP port. It **SHOULD** bind
loopback (`127.0.0.1`) by default.

All paths are prefixed with the protocol version: `/postern/v0/…`. The prefix
changes only on a breaking revision.

Request and response bodies are `application/json; charset=utf-8`, except
`stream`, which is `text/event-stream` (§4.3). That is a statement about
encoding here and a **MUST** about refusal in §2.3, for a reason that has
nothing to do with parsing: the media type of a `run` body is what decides
whether a browser asks permission before sending it.

A runner **MAY** additionally be launched as a subprocess and discovered
through a launch specification (`command`, `args`, `env`), the same shape
MCP uses for stdio servers. The port it binds is then reported on stdout as
a single line, `POSTERN_PORT=<port>`, before any other output. Discovery is
the only thing this changes: the protocol itself is unchanged.

### 2.1 Errors

Every non-2xx response body **MUST** be:

```json
{
  "error": {
    "code": "not_entitled",
    "message": "This agent requires a purchase.",
    "detail": null
  }
}
```

`code` is a stable machine-readable token; `message` is human-readable and
**SHOULD** be safe to show a user verbatim. Defined codes:

| Code | HTTP | Side | Meaning |
|---|---|---|---|
| `bad_request` | 400 | R · D | Malformed request — a bad body, an input that failed `describe`'s validation, or an agent identifier that does not match §1.5's grammar (§5.3.1). |
| `unauthorized` | 401 | R | The runner requires inbound authentication of its own (§7) and the request did not satisfy it. Only for a runner that binds a non-loopback interface; distributors **MUST NOT** use it (§5.5). |
| `not_found` | 404 | R · D | No such agent — **or** the caller is not entitled to it, **or** the token does not resolve (§5.5). The one code that means different things on each side; see below. |
| `not_entitled` | 403 | R | The caller is known and is not entitled. Only for a local runner reporting its *own* state; distributors **MUST NOT** use it (§5.5). |
| `idempotency_conflict` | 409 | R | An `Idempotency-Key` the runner has already answered, presented with different `inputs` (§4.2). |
| `withdrawn` | 410 | D | The caller was entitled, and the agent has since been withdrawn (§5.6). |
| `missing_credential` | 424 | R | A credential named by `describe` is absent from the environment, on a request that is otherwise valid (§4.6). |
| `agent_error` | 500 | R | The agent ran and failed. |
| `not_implemented` | 501 | R | The verb is defined by this specification but sits above the runner's conformance level (§3). Retrying will not help. |
| `unavailable` | 503 | R · D | The runner or distributor is not ready. Retrying may help — a runner refusing a run because another is in flight answers this (§4.5). |
| `run_timeout` | 504 | R | The run reached the runner's declared maximum duration and was stopped (§4.5). |

**Side** says which half of the protocol emits a code: `R` for a runner
(§4), `D` for a distributor (§5). A code marked for one side only is not
merely unusual on the other — it is unconstructible there, and a client
receiving it has been told something about the responder rather than about
the request.

`not_found` is the exception, because the two sides have different things to
miss. A distributor emits it for an agent that is absent from the caller's
catalogue *or* present and not entitled — the two are deliberately
indistinguishable (§5.5). A runner has no agent identifier to miss (§2.2),
so its only use of `404` is a path it does not implement, which says nothing
about the agent it serves.

A client **MUST** treat an unrecognised `code` as a generic failure of its
HTTP status class, and **SHOULD** show `message` to the user. New codes may
be added in a minor release; a client that rejects a code it does not
recognise converts that addition into a breaking change for its own users.
The schema in [`schemas/`](schemas) enumerates the codes a conforming
implementation *emits*, which is a narrower question than the set a client
**MUST** accept.

Nothing sits beside `error`. The envelope's root has exactly one member, and
a conforming implementation **MUST NOT** emit a sibling for it —
[`error.schema.json`](schemas/error.schema.json) is closed at the root, and
it is the only schema here that is.

The reason is one extension point rather than two, and it withholds nothing:
`error` is open and `detail` takes arbitrary structure, so anything an
implementation wants to attach to a failure still has somewhere to go. What
the closed root buys is that the whole failure is under one key, and that
every future addition to this envelope lands inside `error`, where unknown
members are already ignored rather than rejected. That is also why closing
it costs no forward compatibility — there is no top-level addition to block,
because there is nowhere a top-level addition would need to go.

Like the code enum, the closed root constrains writing rather than reading.
A client that receives a sibling of `error` **MUST NOT** reject the response
for it. Emit the shape exactly; accept more than the shape.

### 2.2 One agent per runner

A runner **MUST** serve exactly one agent. No runner *path* carries an
agent identifier — `describe`, `run`, `stream` and `status` are addressed
by nothing but the runner's origin — so a client **MAY** treat a runner's
port as that agent's address. Only the distributor paths in §5 address an
agent by identifier (§1.5), because a distributor answers for a catalogue
while a runner only ever answers for itself.

The *bodies* do carry one, and must: `describe` and `status` both report
`agent.id` (§4.1, §4.4), which is what lets a client confirm that the port
it holds is the agent it meant. One runner serving one agent is a rule
about what a port answers for, not a reason to leave the answer unnamed.

Serving several agents means running several runners. A client that wants a
catalogue holds a list of ports; a client that wants two agents to work
together calls both. Composition is the client's — the addressing form of
the orchestration non-goal in §1.2.

### 2.3 Browser clients

A client running in a browser is subject to the same-origin policy, and the
other client kinds in §1.4 are not. A web UI served from
`https://app.example.com` — or from a local dev server on some other port —
that calls `http://127.0.0.1:8765/postern/v0/describe` is making a
cross-origin request, and a runner that says nothing about CORS is
unreachable from that client while answering every one of its requests
correctly.

Two mechanisms are involved, and the difference between them is the whole
shape of this section:

- `describe` and `status` are `GET`s a browser sends without asking
  permission. The runner receives them and answers them; the browser then
  **discards the answer** unless it carries `Access-Control-Allow-Origin`.
  The call happened. Only the reading of it was refused.
- `run` and `stream` are `POST`s carrying `application/json`, which is not
  something a browser will send cross-origin unasked. It sends a preflight
  `OPTIONS` first and **never sends the `POST` at all** unless that
  preflight is answered permissively.

So a cross-origin read is stopped *after* it has run and a cross-origin
`run` is stopped *before*, which is survivable only because the two verbs on
the wrong side of that line are reads: §4.1 requires `describe` to be
side-effect free, and `status` reports state rather than changing any.
Postern's side-effecting verbs are the ones that preflight. The rest of this
section is about not giving that up.

**Answering the preflight.** A runner **MUST** answer `OPTIONS` on
`/postern/v0/run` and `/postern/v0/stream`. It **SHOULD** answer `OPTIONS`
on `describe` and `status` too, for a client that sends a request header
outside the browser's safelist and so preflights its `GET` as well.

A preflight **MUST** be side-effect free and **MUST NOT** require
credentials or an entitlement. It is not the verb behind it, and its answer
does not depend on the runner's conformance level: a Level 1 runner
preflighted for `run` answers the preflight like any other, so that the
`POST` behind it arrives and can be refused `501` with `not_implemented`
(§3) — a readable answer the client can act on, where a refused preflight
would leave it with an opaque failure that names nothing.

Where the runner allows the origin, that answer carries:

| Header | Value |
|---|---|
| `Access-Control-Allow-Origin` | the requesting origin, echoed octet-for-octet |
| `Access-Control-Allow-Methods` | `POST, OPTIONS` — `GET, OPTIONS` for `describe` and `status` |
| `Access-Control-Allow-Headers` | `Content-Type`, plus `Idempotency-Key` where the runner honours it (§4.2), plus `Authorization` where the runner requires its own inbound authentication (§7) |
| `Vary` | `Origin` |

on any 2xx status; `204` is the usual choice.

Naming `Idempotency-Key` there is a **MUST** rather than a courtesy for a
runner that declares `capabilities.idempotent_retry` (§4.2). A browser
cannot send a header its preflight did not admit, so the promise would
otherwise hold for every client kind except the one that has to ask
permission to take it up — and the runner would look, to that client alone,
like one ignoring a header it never received.

Naming `Authorization` is the same **MUST** for the same reason, and only for
a runner that requires inbound authentication of its own (§7). Unadmitted, it
is the one header a browser client cannot present, so such a runner would
refuse every request from a page `401` while answering every other client
kind — a failure that reads as a wrong credential and is a missing preflight
header. A runner requiring nothing **SHOULD NOT** name it: `Authorization` is
not on the browser's safelist, so admitting it preflights a `describe` that
would otherwise have gone without one, for a credential the runner does not
read.

`Access-Control-Allow-Origin` and `Vary: Origin` **MUST** ride the actual
response as well, and not only the preflight. The two are refused
separately: a preflight authorises the request, and a `run` whose response
arrives without the header is discarded by the browser exactly as an
unpermitted one would be — the agent having run.

`Vary` is not decoration, and it earns its place on the actual response
rather than on the preflight. A browser keys its preflight cache by origin
already; a shared cache sitting between the page and the runner keys on the
URL, so a runner that echoes an origin without `Vary: Origin` invites that
cache to hand the first caller's permission to the second.

No `Access-Control-Expose-Headers` is required, because Postern puts nothing
in a response header a client has to read. `Content-Type` is legible to a
page already, and every other answer this protocol gives is in the body.

`Access-Control-Max-Age` is **OPTIONAL** and worth sending. Without it a
browser preflights every single `run`, which doubles the request count on
the one verb a user is already waiting on.

**Which origins to allow is the runner's decision.** Postern specifies only
the two ends of it. A runner **MUST NOT** allow an origin it was not
configured to allow, and **MUST NOT** ship `Access-Control-Allow-Origin: *`
as a default.
A wildcard is a configuration an operator may legitimately choose; it is not
one a runner may choose on their behalf. §7 gives the reasoning at length,
and the short form is that a runner defines no authentication, so the origin
check is the entirety of its access control against a browser.

A runner refusing an origin **SHOULD** answer the preflight `204` with no
`Access-Control-Allow-Origin`, rather than an error status. The browser
blocks the call either way and the page can read the body of neither, so
§2.1's envelope buys nothing here — while a `403` invites whoever reads the
network log to go looking for an entitlement problem that does not exist.

A runner **SHOULD NOT** send `Access-Control-Allow-Credentials`. Postern
defines no cookie and no browser-presented token, so the header can only
admit ambient credentials this protocol never asked for.

`Origin: null` **MUST NOT** be treated as an origin a configuration can
name. Sandboxed documents, `file://` pages and several redirect chains all
send it, so allowing `null` allows all of them at once: it is a wildcard
wearing the shape of one specific origin.

**A preflight only holds if `run` refuses a request that skips it.** What
makes `run` preflight is `application/json`. A browser sends a cross-origin
`POST` with no preflight at all when the `Content-Type` is one of the three
its safelist admits — and `text/plain` is one of them, and a JSON body
labelled `text/plain` is still a JSON body.

A runner that parses whatever it is handed therefore has no preflight at
all. A page on any origin posts `text/plain` to `/postern/v0/run`, the
browser sends it without asking anyone, and the agent runs — spending money
and invoking `write_tools` (§4.1.2) — before any origin decision has been
reached. That the page cannot read the response is no consolation: the side
effect was the attack, and it has already happened.

A runner **MUST** therefore reject a `run` or `stream` request whose
`Content-Type` media type is not `application/json`, answering `400` with
`bad_request`, and **MUST** do so before executing the agent. Parameters do
not enter into it — `application/json` and `application/json; charset=utf-8`
are the same media type, and §2 requires a client to send the second without
making the first nonconformant to receive.

This is the one rule here that binds a runner nobody will ever point a
browser at. It is a **MUST** anyway, because the runner does not get to know
that, and it costs a client already sending the header §2 requires exactly
nothing.

**Two things a browser client should expect.** `stream` cannot be consumed
with `EventSource`: that API issues a `GET` and sets no request headers,
while `stream` is a `POST` carrying a JSON body (§4.3). A browser client
reads the events out of `fetch`'s response body itself. The wire format in
§4.3 is unchanged — only the reader is.

And an allowed origin may not be the last word. Browsers separately restrict
requests from a public origin to a loopback or private address, under a
mechanism of their own that is still moving at the time of writing: Chrome
preflights such a request with `Access-Control-Request-Private-Network` and
wants `Access-Control-Allow-Private-Network: true` in reply, and is
reshaping that into a user-granted permission. A runner **MAY** answer that
header. A client **MUST NOT** assume an allowed origin settles the question,
and neither party can settle it here — it is the browser's policy about the
local network rather than Postern's about its own protocol.

None of this reaches §5. A distributor's endpoints are called by a runner
and never by a page — a browser holds no token (§7) — so a distributor
carries no CORS obligation under this specification.

---

## 3. Conformance

A conforming runner implements one of three cumulative levels.

| Level | Name | Required verbs |
|---|---|---|
| 1 | **Describe** | `describe`, `status` |
| 2 | **Execute** | + `run` |
| 3 | **Stream** | + `stream` |

A runner **MUST** report its level in `status` (§4.4). A client **MUST NOT**
assume a level it has not read from `status` or inferred from a successful
call.

Level 1 exists so that an agent which cannot be executed by the caller —
unentitled, missing credentials, or simply a catalogue entry — can still
describe itself. This is what lets a client render an agent it cannot yet
run.

A runner **MUST** answer a verb above its declared level with `501` and code
`not_implemented` (§2.1), rather than degrading to a lesser behaviour. The
rule is stated once here rather than restated per verb, so that it holds for
every verb — including any added later, and including a client that read
`level` and called above it anyway.

The code matters as much as the status. A runner's level is a permanent,
discoverable property, so "this runner will never serve this verb" is not
the same answer as "this runner is not ready just now", and `unavailable`
would invite a retry that can never succeed.

---

## 4. The execution surface

### 4.1 `GET /postern/v0/describe`

Returns the agent's input and output contract. **MUST** be side-effect free,
and **MUST** be answerable without credentials and without an entitlement.

```json
{
  "postern": "0.1",
  "agent": {
    "id": "acme/market-research-crew",
    "name": "Market Research Crew",
    "version": "1.3.0",
    "summary": "Researches a market segment and returns a positioning brief."
  },
  "inputs": [
    {
      "key": "segment",
      "label": "Market segment",
      "type": "text",
      "required": true,
      "default": null,
      "validation": {"max_length": 200}
    },
    {
      "key": "depth",
      "label": "Depth",
      "type": "select",
      "required": false,
      "default": "standard",
      "validation": {"options": ["quick", "standard", "exhaustive"]}
    }
  ],
  "output": {
    "type": "text",
    "example": "## Positioning brief\n\nThe mid-market segment…"
  },
  "capabilities": {
    "idempotent_retry": true,
    "tools": ["serper_search", "file_read", "file_write"],
    "write_tools": ["file_write"]
  },
  "credentials": [
    {
      "env": "OPENAI_API_KEY",
      "purpose": "Runs the agents in this crew.",
      "signup_url": "https://platform.openai.com/api-keys"
    }
  ],
  "examples": [
    {"inputs": {"segment": "B2B SaaS observability"}, "output": "## Positioning brief…"}
  ]
}
```

`agent.id` is the identifier defined in §1.5. It is the same string the
distributor paths in §5.3 and §5.6 address, which is what lets a client go
from an agent it has described to an entitlement check for it.

`capabilities` describes the **agent**. Whether a runner serves `stream` is
not a fact about the agent but about the deployment, and §3 already makes it
discoverable as `level` in `status` — normatively, and with a **MUST NOT**
against assuming a level read from anywhere else.

A `capabilities.streaming` boolean was published in an earlier draft of this
section and is **withdrawn**. It was the second vocabulary for a fact §3
already stated, and nothing bound the two together, so `{"level": 2}` beside
`{"streaming": true}` was a payload no rule refused and no client could act
on: reading it and calling `stream` is assuming a level not read from
`status`, which is the one thing §3 forbids in those words. A field a
conforming client may not act on is decoration, and describing it would have
frozen the contradiction rather than settling it. The same reasoning keeps
`limits` in `status` rather than here (§4.4), and kept `0` out of
`max_concurrent_runs`.

Withdrawing it breaks no runner. `capabilities` is an open object, so one
still emitting `streaming` validates exactly as before — the field simply no
longer means anything, and a client reading it was already reading something
§3 told it not to trust.

#### 4.1.1 `inputs`

An ordered array of input declarations. Each **MUST** carry `key`, `label`,
`type` and `required`.

**`key` is `[A-Za-z0-9_.-]+`** — ASCII letters and digits, underscore, dot
and hyphen, one character or more. `label` is the human-facing name and is
free text; the two exist so neither has to do the other's job, and it is
`label` carrying the human's that lets the key stay this narrow.

The narrowness is for the client, which renders a key as the *name* of a
thing: a form field, a command-line flag, a column heading, a variable in a
config file. Each of those escapes a space or a quote differently and some
cannot escape one at all, so a key needing escape is a key that renders
differently in every client that meets it. Excluding whitespace and
everything outside ASCII also makes two keys that look alike *be* alike —
no trailing space, no non-breaking space, and no Cyrillic `а` beside a Latin
`a` in a list a person has to read.

Its length is deliberately unbounded where an agent identifier's is capped
(§1.5), and the difference is what the string crosses: an identifier is
handed to a distributor in a request path (§5.3), while a key is the
runner's own name for its own field and travels only between that runner and
a client already talking to it. The grammar binds the declaration and
reaches `run` through it, since `inputs` there is a map keyed by `describe`'s
input keys (§4.2) — so there is nothing separate for a client to check, and
nothing a conforming one can send that this does not admit.

`type` is one of `text`, `number`, `select`. A runner **MUST NOT** emit a
type outside this set in v0; a client **MUST** treat an unrecognised type as
`text` rather than failing.

Those three types fix the value space of `run`'s `inputs` map (§4.2) and of
`default`: `text` and `select` carry a string, `number` carries a number,
and `null` means no value was supplied. Nothing declarable in v0 produces a
boolean, and the schemas do not admit one. A fourth type — and the value
shape it implies — can be added later, which is additive; withdrawing a
value shape a runner had already relied on would not be, which is why the
narrower set is the one published first.

`describe.schema.json` enforces that pairing on `default`, which it can
because the type and the default sit in one object. It cannot on `run`'s
`inputs`: the values there are in a different document from the
declarations that type them, so `run-request.schema.json` admits the union
of the three value spaces and the per-input check stays the runner's, which
§4.2 already requires of it. A `default` disagreeing with its own `type` was
never conforming under the sentence above; it now fails validation as well
as prose.

`validation` is an open object. Recognised members: `max_length`, `min`,
`max`, `pattern`, `options` (**REQUIRED** when `type` is `select`).
Unrecognised members **MUST** be ignored rather than rejected.

**The key forward-compatibility property of this specification is that
`inputs` is an envelope.** Postern fixes that an agent declares a list of
typed, labelled, individually-validated inputs. It does not fix *how a given
agent arrives at that list* — whether it exposes one free-text brief, a
dozen configured fields, or both is the agent's business, and it may change
between agent versions without breaking any client. Clients render the
envelope. This is deliberate, and it is why `run` takes a map rather than a
positional argument (§4.2).

The reserved key `prompt` denotes a single free-text brief where an agent
has one. Reserving it lets a client offer a familiar single-box interface
for the common case without special-casing any particular agent.

#### 4.1.2 `capabilities.write_tools`

`tools` lists every tool the agent can invoke. `write_tools` **MUST** be the
subset of those that spend money, mutate state outside the workspace, or are
otherwise not safely repeatable.

A client **SHOULD** surface `write_tools` to the user before the first
`run`, and **MAY** require confirmation. It is the reason `tools` is not a
flat list.

`capabilities.idempotent_retry` (§4.2) is the other half of the same warning
and the only other safety-relevant field here: `write_tools` says what an
agent does that nothing can undo, and `idempotent_retry` says whether asking
twice does it twice. A client with a reason to surface the first has the same
reason to read the second before it retries.

#### 4.1.3 `credentials`

Declares credentials by **environment variable name only**.

A `describe` response **MUST NOT** contain a credential value. A conforming
agent bundle **MUST NOT** contain a credential value. Runners load
credentials from the environment of the machine they run on.

This is the property that makes "your keys stay on your machine" checkable
rather than promised: there is nowhere in the protocol for a secret to
travel, and a bundle carrying one is nonconformant.

**Each entry carries `env`, and OPTIONALLY `purpose` and `signup_url`.**
`env` is the environment variable's name, never its value. `purpose` says in
one line what the agent does with it, and `signup_url` points at where a
buyer obtains one — both written for a person reading a listing before they
install anything, and neither read by a runner.

**A conforming runner emits no other member**, and
[`describe.schema.json`](schemas/describe.schema.json) closes the object to
say so. It is the only closed *object* in these schemas outside the error
envelope's root (§2.1) — `error.code` and `output.type` are closed enums,
a different thing — and it is what makes the sentence above true rather than
aspirational. An open object *is* somewhere in the protocol for a secret to
travel: `value` beside `env` would be schema-valid, and so would every other
spelling of the leak this section forbids.

The closure catches the structural half of that and not the whole of it. A
value written into `purpose` is a conforming shape carrying a nonconformant
string, which no schema can see — only reading the field finds it, which is
why a checker reads it. What the closure removes is the easier mistake, and
the likelier one: a runner that serialises its own credential record and
ships the value beside the name without noticing. It removes it at the parse
boundary rather than by review.

**The cost is a member added here later.**
[VERSIONING.md](VERSIONING.md#before-10) promises a minor release adds only
optional fields, and this closure does not take that back: these schemas
describe what a conforming runner *emits*, not what a client must accept.
[`schemas/README.md`](schemas/README.md) states that posture and the four
places it is load-bearing, this being one. A future member is therefore
additive for runners, and for any client that does not use an emit-side
schema as an acceptance filter; it breaks only one that does — the parser
VERSIONING already describes, and already declines to design around.

#### 4.1.4 `output`

Declares what the agent returns: a `type`, and an **OPTIONAL** `example`.
The block itself is **REQUIRED** — §4.1's first sentence promises an input
*and output* contract, `run` and `stream` both **MUST** carry an `output`
with a `type` (§4.2, §4.3), and this is the only place a client can learn
what that type will be before it asks. A `describe` omitting it leaves the
client the one thing this section says it may not do: meet a `type` it has
no declaration for.
§4.2's `run` response carries the same `type` beside the `value` it actually
produced, and so does a stream's `done` payload (§4.3).

`type` is `text` or `bytes`. `text` is the ordinary one and the one §4.1.1
records the matching decision for on the input side; `bytes` is defined at
the end of this section, for an agent whose result is a file rather than
prose. `output.value` carries a JSON string either way, so the envelope has
one shape regardless. A third type can be added later on the same terms:
additive for a runner, which need never emit it, and free to withdraw
nothing. What an unrecognised one costs a *client* is the subject of the
rest of this section.

**An unrecognised `output.type` is the one unknown in this protocol a client
may not ignore.** Every other extensible surface tells a client to carry on
regardless: an unrecognised error `code` is a generic failure of its status
class (§2.1), an unrecognised `stream` event name is skipped (§4.3), an
unrecognised input `type` is treated as `text`, and an unrecognised
`validation` member is dropped (§4.1.1). None of those rules transfers here.
Each governs something a client is entitled to ignore, and this is not that:
`type` is what says how to read `value`, so a client that ignores it has not
tolerated an unknown — it has misread a known.

§4.2 already makes this argument, about a field it declined to add:

> A signal a client must not miss cannot ride in a field a client is
> entitled to ignore

The input side is the instructive contrast, because it looks like the same
question and is not. Falling back to `text` for an unrecognised *input* type
is safe: the client renders a text box, the user types into it, and the
**runner** validates what comes back — answering `bad_request` if it is
wrong (§4.2). There is a second reader downstream. On the output side the
client is the last reader, nothing checks its interpretation, and guessing
`text` for bytes that are not text renders them as prose: silently, with no
error anywhere, and looking for all the world like an agent that returned
gibberish.

So a client receiving an `output.type` it does not recognise:

- **MUST NOT** present `value` as text.
- **MUST NOT** report the run as having failed. §2.1 routes every failure
  through a non-2xx envelope, so a `200` carrying an output type the client
  cannot read is a run that *succeeded* beside a client that cannot render
  it. Those are two different facts, and the second is the one the user
  needs.
- **SHOULD** say which type it was given, rather than only that something
  went unrendered. It is the one piece of information that tells a user
  whether to reach for a different client.
- **MAY** pass `value` on unchanged to something that does understand it. A
  client composing two agents (§2.2) relays a result it never has to read
  itself.

The same rule reaches `describe`, one step earlier and with a different
consequence. A catalogue that reads a declared output type it does not
recognise can still render the agent — its name, inputs, credentials and
tools are all unaffected — and **MUST NOT** describe it as returning text.
Rendering an agent and rendering it accurately are different things, and
Level 1 (§3) exists for the second.

**`bytes` is the second type**, for an agent whose result is a rendered
chart, a short PDF, a generated image — a file rather than prose. It
carries two obligations beyond `text`:

- `value` is the artifact **base64-encoded**, standard alphabet with
  padding ([RFC 4648](https://www.rfc-editor.org/rfc/rfc4648) §4). It
  remains a JSON string, so no envelope changes shape to accommodate it.
- `media_type` sits beside `type` and is **REQUIRED** when `type` is
  `bytes`: an [RFC 6838](https://www.rfc-editor.org/rfc/rfc6838) media
  type, `image/png` or `application/pdf`. It is an open string rather than
  an enum deliberately — closing it would need a specification revision per
  format, which is exactly the cost the receive-side rule above exists to
  avoid paying.

  Open is not unshaped. Both halves follow §4.2's `restricted-name` —
  alphanumeric first, then any of `!#$&-^_.+` — which is what admits a
  facet and a structured suffix (`application/vnd.api+json`) and an
  experimental type (`x-custom/foo`) without admitting a subtype beginning
  `!`.

  **A runner emits it in lower case.** RFC 6838 names are case-insensitive,
  so `image/png` and `IMAGE/PNG` are one type — and a client that compares
  the field octet-for-octet, which is the obvious thing to do to a JSON
  string, would read them as two. Fixing the case on the emit side costs a
  runner nothing and spares every client the comparison rule. **A client
  MUST NOT reject a response over the case of this field**: the constraint
  is on what a runner sends, and §2.1's posture on unrecognised values
  applies here too. Compare case-insensitively and carry on.

A `run` response carrying one:

```json
{
  "postern": "0.1",
  "run_id": "01JD9YB4R2",
  "output": {
    "type": "bytes",
    "media_type": "image/png",
    "value": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA…"
  }
}
```

A client that knows `bytes` and not the media type is better placed than one
meeting an unknown `type`: it knows the value is an artifact rather than
prose, so it can offer to save it under that name instead of declining to
render anything. It **MUST NOT** present it as text, for the reason already
given.

**A `bytes` run emits no `delta`.** §4.3's invariant is that concatenated
`delta.text` equals `output.value`, and base64 fragments satisfy it only in
a way that is useless to the client rendering them — the stream prints the
encoding. So a runner producing a `bytes` output **MUST NOT** emit `delta`
at all. Progress on such a run rides on `step`, which reports it without
pretending to be the output.

**`example` stays text-only.** `describe.output.example` is a string, and a
runner **MUST NOT** emit one for a `bytes` output. An inline artifact would
inflate a document every catalogue listing fetches, to show what
`media_type` already names.

**Size is declared, not solved.** Base64 costs a third on top of the
artifact and both ends hold the whole of it in memory: this envelope moves a
chart, not a corpus. A runner that bounds what it will return **MUST**
declare the bound as `limits.max_output_bytes` in `status` (§4.4), measured
on the artifact rather than on its encoding. Where an agent's real output is
larger than that, §1.2's tools remain the honest route — the file is written
where the user can already reach it, and the protocol is not asked to carry
it.

**A third type would owe what this one just paid**: what `value` carries,
what `delta` means in its presence, whether `example` reaches it, and what
bounds it. What is settled here is that a client written against this
section survives every such addition, which is the property that had to
exist first.

### 4.2 `POST /postern/v0/run`

Executes the agent and returns the final result. A Level 1 runner does not
implement it, and **MUST** answer `501` with code `not_implemented` (§3).

Request:

```json
{"inputs": {"segment": "B2B SaaS observability", "depth": "standard"}}
```

`inputs` is a map keyed by `describe`'s input keys. A runner **MUST** reject
a request omitting a `required` input, or failing a declared `validation`,
with `bad_request` — and **SHOULD** name the offending key in `message`. It
**MUST** reject a body that is not `application/json` with the same code,
before reading the body at all (§2.3). This check precedes the runner's
inspection of its own environment, so a request that is both malformed and
unservable is answered `bad_request` (§4.6).

Response:

```json
{
  "postern": "0.1",
  "run_id": "01JD8XW2Q9",
  "output": {"type": "text", "value": "## Positioning brief…"},
  "usage": {
    "input_tokens": 4210,
    "output_tokens": 918,
    "cost_usd": 0.001182,
    "steps": [
      {"name": "research", "model_id": "gpt-4o-mini", "input_tokens": 2100,
       "output_tokens": 400, "latency_ms": 3120}
    ]
  }
}
```

The response body carries no `status` field. Every failure routes through
§2.1's error envelope on a non-2xx status, so a `run` body exists only where
the run succeeded, and a field whose one legal value is `ok` repeats what
the status line already said.

It is not withheld as a place to grow one, either. The case such a field
would be reserved for — a run that finished but returned a partial or
truncated result — cannot be carried by adding a value to it, because a
client that does not recognise the new value reads an incomplete result as a
complete one. A signal a client must not miss cannot ride in a field a
client is entitled to ignore (see [VERSIONING.md](VERSIONING.md)), so that
change needs a mechanism of its own whenever it is wanted, and loses nothing
by not having a placeholder now.

`usage` **SHOULD** be present when the runner can determine it.
`usage.cost_usd` is the runner's best estimate in US dollars and is
advisory — a client **MUST NOT** treat it as a billed amount.

`run_id` **MUST** be unique per execution within the runner's lifetime and
**SHOULD** be stable enough to correlate with `stream` events and logs.

Per execution rather than per response, which is the distinction a replay
makes visible. A replayed answer (below) carries the `run_id` of the
execution it replays, because that is the run it reports: one execution has
one identifier however many times it is reported. Minting a fresh one for
the replay would name an execution that never happened — no agent ran under
it, no `stream` emitted it, and the runner's own logs have no line for it —
which defeats the correlation the **SHOULD** above exists for.

`run` is not idempotent. A runner **MAY** honour an `Idempotency-Key`
request header; behaviour when it does not is to execute again.

**A runner that honours it says so**, as `capabilities.idempotent_retry` in
`describe` (§4.1) — an **OPTIONAL** boolean. `true` is a promise about the
agent rather than about the response: a request carrying an
`Idempotency-Key` the runner has already answered **MUST NOT** execute the
agent a second time, and **MUST** answer with the result of the first
execution, whether that was a success or the error the agent produced
(§2.1). A client wanting a genuine second attempt asks with a new key, which
is what it would have done with no header at all. A request refused before
the agent ran — a `bad_request` here, a `501` under §3 — executed nothing
and so binds no key. On `stream` a replayed result arrives as `start` then
`done`, a shape §4.3 already admits: `delta` is optional, and a replay has
no incremental text to produce.

**A key identifies a request, not merely a caller's wish to retry one.** A
runner **MUST** treat a key as bound to the `inputs` it was first answered
for, and **MUST** refuse a request carrying that key with different `inputs`,
answering `409` with code `idempotency_conflict` (§2.1) rather than replaying
the first execution.

Taking the key at its word is the cheaper rule and the one this section used
to imply, and it fails in the way §4.1.4 argues hardest against: the second
request is answered with a result computed for inputs the caller never sent,
at `200`, in a well-formed envelope, with neither side able to detect it — a
client that cannot tell a wrong answer from a right one, arriving through a
header it added in order to be careful. §4.1.2 is the sharp case as usual.
An agent whose `write_tools` spend money is the one a client retries
deliberately, and the one where being handed an earlier run's output is
worst.

`bad_request` is the near miss and misleads. The body is well-formed and
every input valid, so there is nothing in it to fix; and `400` is already
what a failed `validation` answers, so a client could not tell "your inputs
are wrong" from "that key is spoken for" — two refusals whose remedies are
opposite, one correcting the body and the other sending a new key.

Inputs are compared **by value on the decoded map**, not on the bytes that
carried it. A client that re-serialises the same request — different key
order, different whitespace — has sent the same request, and comparing bytes
would manufacture a conflict out of a JSON encoder's choices.

A `409` executes nothing, so it binds no key, exactly like the refusals
above: the first execution's answer remains the one that key replays, and a
client that meant to send different inputs sends them under a new key.

**How long a key is remembered is the runner's to choose**, and a client
**MUST NOT** assume any particular window. Nothing remembers forever, and a
runner that forgets after a second satisfies every word of the replay rule,
so a client cannot otherwise tell whether its retry is still inside the
promise or is buying a second execution. A runner **SHOULD** declare a
window it can state as `status.limits.idempotency_retention_seconds` (§4.4).
A bound nobody published is one a client discovers by being charged twice.

A client **MUST** read absent and `false` identically — a retry executes
again, which is what this section already said of a runner that does not
honour the header. The field is there for a runner to make the promise
rather than to deny it, which is also what keeps it additive: a client
written before it existed reads every runner as absent, and where that is
wrong it is wrong in the direction that costs nothing, budgeting for a
second execution that never happens. A runner **MAY** still honour the
header without declaring it — the **MAY** above is unchanged — and nothing
may be built on that: an undeclared courtesy is one no client is entitled to
read, which is what leaves the declaration carrying the whole of the
promise. A Level 1 runner (§3) has no `run` to be idempotent about and
**SHOULD NOT** declare the field at all.

**What the key saves is narrower than it looks**, and §4.5 is why. A
disconnected client is a cancelled run there: the runner aborts the agent
and discards the output, so there is no completed first execution for a
retry to be answered with, and one executes again whether it carries a key
or not. What a key recovers is the other disconnect — the agent had
finished and the answer was lost on the way back, the money already spent
and every `write_tools` entry (§4.1.2) already invoked. It declines to buy a
completed run twice. It does not resume an abandoned one.

Declaring it matters precisely because a client cannot tell those two apart.
A connection dropping mid-`run` looks identical whether the agent was
halfway through or writing its last byte, and the client holds no `run_id`
to ask about — §4.5 says why a `run` client never learns one. So
`idempotent_retry` does not tell a client which of the two it suffered. It
tells it whether asking again is capable of being free, which is the
question a client warned about `write_tools` is actually asking.

A runner declaring `true` **MUST** name `Idempotency-Key` in the
`Access-Control-Allow-Headers` of its preflight answers (§2.3).

### 4.3 `POST /postern/v0/stream`

Takes the **same request body as `run`** and returns
`text/event-stream`.

Events are Server-Sent Events with a named `event:` and a JSON `data:`
payload. Five event types are defined:

| Event | Payload | Notes |
|---|---|---|
| `start` | `{"run_id": "…"}` | **MUST** be first. |
| `step` | `{"name": "…", "model_id": "…", "status": "started\|finished", "latency_ms": N}` | **OPTIONAL**, zero or more. |
| `delta` | `{"text": "…"}` | **OPTIONAL**, zero or more. Incremental output. **If any `delta` is emitted**, concatenating every `delta.text` in order **MUST** equal the final `output.value`; a runner that cannot produce incremental text emits none, and one producing a `bytes` output (§4.1.4) emits none by rule. |
| `done` | The full `run` response body (§4.2) | **MUST** be last on success. |
| `error` | The error body (§2.1) | **MUST** be last on failure. |

A stream **MUST** end with exactly one `done` or one `error`. A client
**MUST** ignore unrecognised event names rather than aborting, which is how
this list grows without a version bump.

`start` carries `run_id`, `delta` carries `text`, and a `step` carries at
least `name` and `status` — one saying which step, the other which edge of
it. `model_id` is absent for a step that calls no model.

**`done` repeats `start`'s `run_id`**, and a runner **MUST NOT** report two
identifiers for one run. That is how a client correlates a stream with its
result and with the runner's logs, and it is the only correlation a stream
offers: the response began `200 text/event-stream` before any of this was
decided (§4.5), so there is no header or status left to carry it. A stream
naming one run at its start and another at its end tells a client something
false about which run it watched, and does so on an answer that is
otherwise correct in every particular.

The `delta` invariant is text-shaped, which is why §4.1.4 forbids the event
outright for a `bytes` output rather than reinterpreting it: base64
fragments would satisfy the concatenation rule while giving a client that
renders the stream nothing but the encoding to print. Such a run reports its
progress with `step`, which was never claiming to be the output.

**Where the deltas and `done` disagree, a client prefers `done`.** The
concatenation rule binds what a runner emits, and nothing binds what a client
does when it is broken — so a client that accumulated deltas, rendered them,
and then read a different `output.value` has met a runner in breach of it with
no move of its own stated anywhere. It **SHOULD** prefer `done`'s
`output.value`: §4.2 makes the run response the result, and the deltas were a
preview of it.

A **SHOULD**, because a client cannot always comply. One writing deltas to
standard output as they arrive has already emitted them and a scrolled
terminal cannot be taken back, and a rule a client has to break to stay useful
is one that gets broken quietly. So a client able to replace what it rendered
**SHOULD**, and one that is not **MAY** say the streamed text was superseded.
Text that changes under a user after it finished arriving is worth a word
either way — the alternative is a user shown two answers and told nothing
about either.

What is not optional is the other half. A client **MUST NOT** report the run
as having failed on that ground alone: §4.1.4 draws the same line for an
output type a client cannot read, and for the same reason — the run succeeded
and the client's rendering of it was wrong, which are two different facts.
Reporting the first sends a user to file a bug against an agent that ran
correctly, and costs them the result, which arrived intact in `done`.

None of this reaches the emit side. The invariant is a **MUST** on the runner
still, and a receive-side rule says what a breach costs the user rather than
licensing one.

`latency_ms` is the step's elapsed time, and is reported on `finished`. A
runner **MUST NOT** emit it on a `started` step, where there is nothing yet
to measure; a client receiving one anyway **MUST** ignore it rather than
reject the event. That asymmetry is the ordinary one — emit exactly the
shape, accept more than it — and it is what keeps a meaningless field from
becoming a conformance argument.

[`stream-event.schema.json`](schemas/stream-event.schema.json) is the
machine-readable form of those three payloads. `done` and `error` are not in
it, because they carry bodies §4.2 and §2.1 already define. Nor is the SSE
framing — the ordering rules above, and exactly one `done` or `error`
last — which spans events and so lives here rather than in any schema.

A Level 2 runner **MUST** answer `stream` with `501` and code
`not_implemented` (§3), rather than falling back to a single-shot response —
a client that asked for a stream and silently got one event cannot tell the
difference between "not supported" and "finished instantly".

### 4.4 `GET /postern/v0/status`

Liveness, conformance level, and entitlement state.

```json
{
  "postern": "0.1",
  "level": 3,
  "state": "ready",
  "agent": {"id": "acme/market-research-crew", "version": "1.3.0"},
  "entitlement": {
    "state": "active",
    "checked_at": "2026-08-15T09:14:02Z",
    "stale_after_seconds": 60
  },
  "credentials": {"satisfied": true, "missing": []},
  "limits": {"max_run_seconds": 900, "max_concurrent_runs": 1}
}
```

`state` is `ready`, `running`, or `degraded`. `entitlement.state` is
`active`, `revoked`, `unknown`, or `not_required` (§5.1).

`agent` and `entitlement` are **REQUIRED**, which the rest of this section
assumed and never said. Every *top-level* member it marks, it marks
**OPTIONAL** — `limits`, `update` — and the two it marks **REQUIRED** are
conditional members inside `entitlement`, so these two were unmarked rather
than decided. `agent` carries the identifier
§1.5 says appears here, and without it §2.2's identity rule cannot be
checked at all: a runner omitting it is not caught disagreeing with its own
`describe`, it simply cannot be asked. `entitlement` carries the state §5.1
**MUST**s a runner with no distributor to report as `not_required`, and
omitting the block is not a quieter way of saying that — it is
indistinguishable from a runner that has not implemented entitlement,
which is the one thing a client reads this to find out. Only `agent.id` is
required within the block; `version` sits beside it in the example above
and nothing obliges it.

`entitlement.stale_after_seconds` is **REQUIRED** whenever
`entitlement.state` is `active` or `revoked` — wherever a check actually
happened, and so wherever `checked_at` is required too. It declares how long
the runner may continue to rely on the cached answer before re-checking. It
bounds how long a revoked entitlement can keep working, together with any
grace the distributor declared for an unreachable check (§5.4, §5.7).

Requiring it for `revoked` as well is what makes that bound evaluable in
both directions. A timestamp with no duration beside it tells a runner when
it was refused and never when to ask again, so the restoration §5.4 obliges
a distributor to support could not be observed. It is the same bound either
way; what changes is who it protects — under `active`, how long a revoked
entitlement can keep working, and under `revoked`, how long a restored one
stays unusable.

`entitlement.state` is `unknown` when the runner cannot presently vouch for
the entitlement: it is inside a declared grace period, or it has never
obtained an answer at all. §5.7 is the only thing that produces that state,
and the two shapes of it are told apart by whether `checked_at` is
there — an agent still running with a deadline, or one that cannot start.

`entitlement.grace_seconds` is **OPTIONAL**, and carries the bound the
distributor declared (§5.3) where the runner has been told one. A client
needs it beside `checked_at` to say when an agent running through an outage
will stop.

`entitlement.checked_at` is **REQUIRED** whenever `entitlement.state` is
`active` or `revoked`. Both are answers a distributor actually gave, and
neither is terminal — a revoked entitlement may later be restored (§5.4), so
a runner holding `revoked` with no timestamp has no basis for ever asking
again. It is omitted for `not_required`, where no check took place.

A runner **MUST** report the `checked_at` it received from the distributor
(§5.3) unchanged, and **MUST NOT** re-stamp it with its own clock.
Re-stamping discards the anchor and silently restores the stacking that
§5.3 exists to prevent, while every field still validates. The one answer
that carries no such value is a `404`, which cannot: there is nothing to
discard there, and §5.7.4 says what a runner reports instead.

`limits` is **OPTIONAL** and carries the bounds a runner puts on a run.
Each member is **OPTIONAL** in turn: `max_run_seconds` is the maximum
duration the runner will let a run reach, **REQUIRED** where it imposes one
at all and absent where it does not; `max_concurrent_runs` is how many runs
it will have in flight at once; and `max_output_bytes` is the largest
artifact it will return from a `bytes` output (§4.1.4), measured before
base64 rather than after, and likewise **REQUIRED** where it bounds one.
`idempotency_retention_seconds` is the last and the odd one out: it bounds a
promise rather than a run — how long the runner replays an `Idempotency-Key`
(§4.2) — and a retry arriving after it has lapsed is answered by a fresh
execution rather than refused.

They live in `status` rather than in `describe` because they belong to the
deployment and not to the agent. Two runners serving the same agent may
answer differently, and the same runner may answer differently after its
operator reconfigures it — neither of which is a fact about what the agent
takes as input, which is what `describe` is for.

`max_concurrent_runs` is at least `1`. A runner that will run nothing says
so with its `level` (§3) and a `501`, which tells a client that retrying is
pointless; a `0` here would say the same thing in a second vocabulary, and
in one a client would reasonably read as a temporary condition.

`update` is **OPTIONAL** and reports what a runner learned when it asked its
distributor whether a newer version of the agent exists. It is present only
where such a check actually ran: a runner with no version check configured
omits it entirely, which is a different fact from a check that ran and found
no distributor to ask.

`update.state` is `not_required`, `unreachable`, `current` or
`update_available`. `not_required` mirrors `entitlement`'s own state (§5.1)
and means no distributor is configured; `unreachable` means one is and could
not be asked. The last two are the answer itself — the version the runner is
running and the version the distributor reports are equal, or they are not.

`update.current` is the runner's own `describe.agent.version`, present
whenever it is knowable and `unreachable` included: a runner always knows
what it is running, whatever it could not reach. `update.latest` is the
version the distributor reported, and is present only under `current` and
`update_available`, those being the only states in which one was obtained.

**An unreachable check is not a failure.** A runner **MUST NOT** refuse to
start, or refuse a run, because it could not determine whether a newer
version exists. That is the posture §5.7 already takes for an entitlement a
runner cannot re-check, and for the same reason: the machine may have no
network, and an agent that has already been pulled is an agent that already
works. A client reads `unreachable` as *not known*, never as *out of date*.

**How a runner obtains `latest` is the distributor's to define**, and this
specification adds no path for it. §5 fixes the two distributor paths a
runner must call to serve its agent at all — the entitlement check and the
bundle — and a version answer is neither: nothing else here depends on one,
and a runner that never asks is fully conforming. A distributor offering the
answer publishes how in its own profile, and §8 records Sigrix's.

It belongs in `status` rather than `describe` for the reason `limits` does,
one paragraph up: which version this runner happens to be running, against a
distributor it happens to be configured for, is a fact about the deployment.
`describe` answers for the agent.

`status` **MUST** answer at Level 1, and **MUST NOT** require credentials.

### 4.5 The life of a run

§4.2 and §4.3 say what a run is asked for and what it answers with. Neither
says what becomes of one already in flight, and three questions fall out of
that: what happens when the caller goes away, whether a runner may give up
on a slow agent, and whether two runs may overlap.

None of them is academic, because §4.1.2 establishes that a run may invoke
tools that spend money and mutate state outside the workspace. Left
unstated, whether closing a laptop lid stops that spending is decided
per implementation, and a client cannot even ask.

**A disconnected client is a cancelled run.** A runner **SHOULD** abort the
agent when the client disconnects, on `run` and `stream` alike, and
**SHOULD NOT** treat the disconnect as a reason to carry on to completion.
Where it cannot abort promptly — a model call or an MCP tool call it does
not control is in flight — it **SHOULD** abort at the next point it does
control, rather than waiting for the run to end on its own.

This is a **SHOULD** rather than a **MUST** for the reason §5.4 gives about
instantaneous revocation: a runner cannot always interrupt what it is
inside, and a requirement that cannot be met is one that gets quietly
ignored, taking the rest of the rule with it. What is not optional is the
part a runner does control — there is no callback in this protocol and no
verb that delivers a result late, so a runner **MUST NOT** deliver the
output of an abandoned run anywhere else, and discarding it is the only
thing it can do with it. A runner honouring `Idempotency-Key` (§4.2) and
answering a retry that carries the key of the run which produced that output
is not the exception it looks like: that is the same request asked again,
answered synchronously to whoever asked it, rather than the late delivery
down some other channel this rule forbids.

**An abort is not a rollback**, and a client **MUST NOT** read one as
undoing anything. Whatever the agent did before it stopped is done: the
money is spent, and every `write_tools` entry (§4.1.2) is a thing that may
already have happened. Postern can stop an agent; nothing here can reverse
one. That is also what makes a retry after a disconnect a genuinely
different request from the first attempt: a client that disconnects,
reconnects and asks again has asked for the work twice, and **SHOULD**
expect to be charged for it twice. An `Idempotency-Key` (§4.2) does not
change that here, and this is the case it can do least about — the run it
would deduplicate against is the one this section just aborted, its output
discarded, so nothing is stored to answer with. What it saves is the retry
whose first attempt finished, which from the client's side looks exactly
like this one.

**`run_id` is not a handle.** It correlates a stream's events with its own
`done` payload and with the runner's logs, and that is the whole of it: no
verb takes one, so a client cannot present a `run_id` later and ask what
became of it. This is a consequence of the four-verb ceiling
([VERSIONING.md](VERSIONING.md)) rather than an oversight, and it is what
makes abandonment simple to reason about — a run nobody is listening to has
no observer left to report to.

The `run` case makes the point sharper than `stream` does. `run_id` reaches
a client only in the response body, so a client that disconnects from a
`run` never learns the identifier of the run it started, and has nothing to
correlate with even in the runner's own logs. A `stream` client at least
received `start` (§4.3).

A dropped `stream` that a client reopens is a **new run**, not a
resumption. Postern defines no replay of missed events and reads no
`Last-Event-ID`, so a reconnecting client starts an agent again — with
everything the paragraph above says about double spending. A client
reconnecting out of habit, because that is what an SSE client usually does,
is the way this costs someone money.

**A runner MAY give up on a slow agent.** Where it imposes a maximum run
duration it **MUST** declare it as `limits.max_run_seconds` in `status`
(§4.4), and **MUST NOT** declare a bound longer than the shortest one it can
actually enforce — a limit a reverse proxy applies first makes the runner's
own number a fiction, in the same way §5.4 forbids a `stale_after_seconds`
shorter than a distributor's real cache. Absent, the field means the runner
imposes no limit of its own.

Exceeding it is answered `504` with code `run_timeout` (§2.1), which is a
new code rather than either of the two that nearly fit. `agent_error` says
the agent ran and failed, which sends a user to report a bug against an
agent that was working; `unavailable` says the runner is not ready and
invites a retry, when the runner was perfectly ready and an identical
request will reach the same deadline again. The client's next move differs
from both — run it again with less to do, or find a runner with a longer
limit — which is the test for whether a code is worth adding.

The body **SHOULD** carry the bound that was exceeded as
`error.detail.max_run_seconds`, the same integer `status` declares. It rides
inside `detail` because the envelope's root is closed (§2.1), for the reason
§5.6 puts `access_ends_at` there — a client that is told which limit stopped
the run can say something true about it, where one told only that something
did has to guess.

On `stream` the timeout arrives as an `error` **event** carrying that body,
not as a status code: the response began `200 text/event-stream` when the
first event was written, and nothing after that can change it. The stream
then ends, satisfying §4.3's exactly-one-`done`-or-`error` rule normally.
A disconnect is the one ending that satisfies it with neither, and that is
not a violation — the rule governs what a runner writes to a live
connection, and there is no longer one. §4.3's `delta` reconstruction rule
is conditioned on a final `output.value` in the same way: a stream that
emitted deltas and then timed out has produced no final output for them to
add up to, and has broken nothing.

**Whether runs may overlap is the runner's to decide**, and its answer is
discoverable rather than assumed. A runner **MAY** refuse a `run` or
`stream` while another is in flight, answering `503` with `unavailable`
(§2.1) — which fits without a new code, because the runner genuinely is not
ready and retrying genuinely may help, and because the client's move is the
same one `unavailable` already asks for. A runner that permits overlap
**SHOULD** declare how much as `limits.max_concurrent_runs`.

Postern requires no `Retry-After` and a client is not obliged to read one. A
runner **MAY** send the header as ordinary HTTP, but the protocol keeps
nothing a client must read in a response header (§2.3) — a browser client
cannot see one without being granted it explicitly, so a rule depending on
it would hold for every client kind except the one §2.3 is about.

**`status.state` observes; `limits` promises.** `running` means at least one
run is in flight when `status` was answered. It does not promise the next
`run` will be refused — a runner permitting overlap reports `running` while
accepting more — and `ready` does not promise the next one will be accepted.
The bound is `limits.max_concurrent_runs`, and even that is a ceiling rather
than a reservation.

So a client **MUST** be prepared for `503` on `run` or `stream` whatever
`status` last told it. Reading `status` and starting a run are two calls
rather than one, and the slot can go to somebody else in between; a client
that treats a `ready` it read a moment ago as an admission ticket has built
a race into itself.

---

### 4.6 The order of refusals

§4.2 and §4.3 say when a runner refuses, and §2.1 names the codes it refuses
with. Neither says which refusal wins when one request earns more than one,
and a `run` earns several routinely: a request omitting a `required` input,
sent to a runner whose environment is missing a credential `describe`
declares, is described correctly by both §4.2's `bad_request` and §2.1's
`missing_credential`. Send that same request to a runner whose entitlement
has lapsed and a third applies, §5.7.4's `not_entitled` — which is the case
that makes this a table rather than a sentence, since it is the one whose
answer no amount of fixing the request changes.

A runner **MUST** answer these in order:

| | Check | Refusal | Stated in |
|---|---|---|---|
| 1 | The verb sits above the runner's declared level | `501` `not_implemented` | §3 |
| 2 | The entitlement is not in force | `403` `not_entitled` or `503` `unavailable` | §5.7.4 |
| 3 | The media type is not `application/json` | `400` `bad_request` | §2.3 |
| 4 | A `required` input is absent, or a declared `validation` fails | `400` `bad_request` | §4.2 |
| 5 | A credential `describe` declares is absent from the environment | `424` `missing_credential` | §2.1 |

Steps 1 and 3 were already ordered and are repeated here only so the
sequence can be read in one place: §3 states its rule for every verb, and
§2.3 requires the media-type check *"before reading the body at all"*. What
this section adds is **2 before 3**, and **4 before 5**.

Between steps 3 and 5 the rule is that **a runner decides what the request
says before it inspects what it holds.** That sentence governs those steps
and not step 2, which is neither: an entitlement is not a property of the
request, and it is not the runner's own deployment either — it is whether
this runner may serve this caller at all.

**Step 2 comes before the request checks because a refusal it produces
applies to every request, whatever the request says.** §5.7.4 draws the line
this rests on: a runner that has been told no *"does not pretend the answer
might change on the next request."* A `400` is exactly that pretence — it
names something the caller can fix and so invites a retry, and on a revoked
runner no retry can succeed. Answering the entitlement first tells the
caller the one thing that is true of every request it might send.

That is the reason, and it is worth separating from one that does not hold.
Gating entitlement first discloses *less* about the agent's inputs, but not
usefully: §4.1 requires `describe` to be answerable "without credentials and
without an entitlement", so any caller already has the input schema. The
ordering is not a disclosure control and should not be defended as one.

Steps 1 and 3 to 4 read the request against the runner's own published
contract, so every conforming runner answers them identically. Step 5
depends on how one machine happens to be deployed. Ordering the
deployment-dependent answer last buys two things a client and an implementer
both need.

**A malformed request gets the same answer everywhere.** A client that sends
one learns what is wrong with it, rather than learning something about the
operator's machine and discovering the real problem on the next attempt.
Reversed, a client fixes its credentials, retries, and only then hears that
its inputs were never valid — two round trips to learn two things, in the
order that helps least.

**And §4.2 stays testable on a runner that is not fully configured**, which
is the ordinary state of one being brought up for the first time. Under the
reverse order a runner missing any credential answers `424` to every `run`,
so the rule §4.2 states as a **MUST** cannot be exercised at all until the
operator finishes a task unrelated to it.

The disclosure difference is real but small, and worth stating at its true
size rather than as a threat: `describe` already publishes *which*
credentials an agent needs, so step 5 discloses only whether they are
currently set. A browser client cannot read that answer cross-origin anyway
(§2.3), and a local process that can reach the runner can usually read the
environment directly. Ordering the request checks first means a caller sends
a well-formed, complete request before it learns even that much, which is a
reasonable default rather than a mitigation.

`missing_credential` has no other producer. It is the one code in §2.1's
table that no other section of this specification requires, and step 5 is
the rule that emits it; before this section it was a code the protocol
defined and never asked anyone to send.

**Step 5 is a check a runner performs, not only one it orders.** The
**MUST** above binds each row as well as the sequence: where `describe`
declares a credential and the runner's environment does not carry it, a
conforming runner answers `424` rather than starting the agent and
reporting whatever the agent's own failure turns out to be.

That is worth stating because the obligation could be read off the table
two ways, and the weaker reading — that the table orders a check a runner
*may* perform, so one that never inspects its environment simply never
reaches the condition — left two conforming runners answering one request
differently. A `424` names the variable to set; the `500` `agent_error`
that follows a run started without it names nothing. A client could not
tell which kind of runner it held until it met an unset credential, and
nothing said it might have to.

**The check is available to every runner, which is what makes this a
MUST rather than a SHOULD.** §4.1.3 has `describe` declare credentials by
environment variable name, and §4.1 requires every runner to answer
`describe` — so a runner already holds the list, and reading its own
environment against it needs no capability it lacks.

The optionality that suggests otherwise is a different thing.
`status.credentials` (§4.4) is **OPTIONAL**, and it governs whether a
runner *publishes* which credentials are satisfied, not whether it checks
one before a run. A runner may perform step 5 and report no credential
state at all. A runner whose `describe` declares no credentials has
nothing to check and passes the step vacuously.

§4.5's capacity refusal is deliberately **not** placed in this sequence. A
runner that cannot start another run has nothing to gain by validating one
first, and **MAY** answer `503` with `unavailable` at any point before the
agent starts. It shares a status and a code with step 2's unreachable case
and is a different refusal: that one says this runner cannot establish it
may serve you, this one says it cannot serve anyone right now. Neither is
distinguishable from the other by status alone, which is what `status`
(§4.4) is for.

---

## 5. Entitlement

### 5.1 The distributor is optional

An agent may be free, self-authored, or locally developed. A runner with no
distributor configured **MUST** report `entitlement.state` as
`not_required`, and **MUST NOT** refuse to run on entitlement grounds.

Everything in the rest of §5 applies only when a distributor is configured.

### 5.2 Tokens

A distributor issues each buyer an **entitlement token**.

- A token **MUST** be opaque to the holder — no claims, no parseable
  structure. It is a bearer secret, not a document.
- A token **MUST** carry at least 128 bits of entropy from a
  cryptographically secure source.
- A distributor **MUST NOT** store a token in recoverable form. Store a
  cryptographic hash and compare hashes.
- A token **SHOULD** be scoped to a buyer rather than to a single agent.
  Per-agent tokens multiply the revocation surface without adding
  protection, since the entitlement check (§5.3) is per-agent regardless.
- A token **SHOULD NOT** expire. Rotation and revocation are the controls;
  expiry adds a failure mode — an agent that stops working on a timer —
  without adding a control the distributor did not already have.

A runner presents its token as `Authorization: Bearer <token>` on every
request to a distributor. Tokens are never sent to a client, and never
appear in a Postern response body.

### 5.3 The check

```
GET  {distributor}/postern/v0/entitlements/{owner}/{name}
Authorization: Bearer <token>
```

```json
{
  "postern": "0.1",
  "state": "active",
  "agent_id": "acme/market-research-crew",
  "checked_at": "2026-08-15T09:14:02Z",
  "stale_after_seconds": 60,
  "grace_seconds": 86400
}
```

Every member above is **REQUIRED**.
[`entitlement.schema.json`](schemas/entitlement.schema.json) is the
machine-readable form.

`postern` carries the specification version, as it does in every payload a
runner returns. This response was the one success payload in the protocol
without it, and a distributor's version is inferable from nothing else:
[VERSIONING.md](VERSIONING.md) makes the field the only sanctioned way to
know what you are talking to, and makes the `/postern/v0/` prefix
deliberately coarser than the version it stands beside. An error envelope
still carries no version, because its root is closed (§2.1) — a failure has
no contract to interpret.

`state` is `active` or `revoked`. A distributor **MUST** resolve the token
to a buyer and answer only for that buyer; there **MUST NOT** be a
parameter, header or path segment by which a caller can widen the answer
beyond the buyer the token identifies.

`agent_id` **MUST** be the identifier the request addressed (§5.3.1),
octet-for-octet. It is an echo of the question, not the result of a lookup:
a distributor answering with a different identifier has answered a different
question, and a runner **SHOULD** treat a mismatch as a failed check rather
than reconcile it.

A token that does not resolve — unknown, revoked, or superseded by rotation
— is answered under §5.5 rather than distinguished. There is no third state
here: a check either answers for a buyer or answers `404`.

A distributor **MAY** serve this from a cache, and where one exists
`stale_after_seconds` **MUST** declare its bound. A distributor answering
from a fresh read sends the field all the same: it is not only a cache
declaration, and the requirement above is not conditional on there being a
cache. §5.4 obliges a runner to re-check after
`checked_at + stale_after_seconds`, and §4.4 obliges it to report the bound
in `status` for `active` and `revoked` alike, so a distributor omitting it
makes its runner nonconformant and leaves a revoked entitlement with no
stated moment at which it stops being honoured.

`grace_seconds` declares how long a runner may keep going past that window
when it cannot reach the distributor at all (§5.7). `0` is a valid
declaration and means *stop at the window*.

`checked_at` is an RFC 3339 timestamp, and means *the moment the
distributor last consulted the authority* — not the moment it answered.
A distributor serving from a cache reports the age of the underlying read,
not the age of the response.

That definition is what makes the declared window honest. Without it the
distributor's cache age is invisible to the caller, a runner can only stamp
its own clock on receipt, and the two caches run back to back — so the real
worst case is their sum while `stale_after_seconds` claims to be the whole
of it.

#### 5.3.1 Addressing the agent

An identifier occupies **two path segments**, not one:
`acme/market-research-crew` is addressed as
`…/entitlements/acme/market-research-crew`, with its `/` serving as the path
separator it looks like. §5.6's bundle path works identically.

The percent-encoded spelling is not an alternative to it. A distributor
**MUST NOT** decode `%2F` into the separator, and **MUST NOT** treat an
encoded form as another spelling of an identifier. §1.5's grammar admits no
character that a path requires encoding for, so a conforming request to
either distributor endpoint carries no percent-encoding at all, and a
distributor needs no decoding step to serve one.

This is stated rather than left to routing because the encoded form is
exactly where implementations diverge: `%2F` in a path is rejected before
the application sees it by some servers, silently decoded by others, and
normalised away by several HTTP client libraries. A specification admitting
both spellings would have chosen, for its implementers, a `404` that nobody
can debug.

A request carrying anything other than exactly two segments after
`entitlements/` matches no route, and `404` is the right answer to it. No
identifier could have matched that path, so the answer says nothing about
the catalogue.

An identifier that fills two segments and does not match §1.5's grammar is
answered `400` with `bad_request` — **not** `404`. This is the one distributor
answer §5.5 does not cover, and it is safe for the reason §5.5 exists to
protect: it is computed from the request string alone. A distributor
**MUST** be able to produce it without consulting its catalogue, **MUST
NOT** vary it by whether a corrected form of the identifier exists, and
**MUST NOT** correct the identifier and answer for the correction.

What that buys is the one diagnosis §5.5 otherwise makes impossible. A
caller who typed `Acme/Market-Research-Crew` is told the string is wrong,
rather than being told — indistinguishably — that they may not own it.

### 5.4 Revocation

A distributor **MUST** revoke entitlement when the purchase behind it is
reversed — refund, chargeback, or dispute — and **MUST** be able to restore
it if the reversal is itself reversed.

Revocation is **not** required to be instantaneous, and a specification that
demanded it would be widely and quietly violated. What is required is that
the window is *declared*: a distributor **MUST NOT** report a
`stale_after_seconds` shorter than the longest staleness any of its caches
can actually produce. A runner **MUST** re-check on the first request after
`checked_at + stale_after_seconds`. That rule binds a `revoked` answer as
much as an `active` one: restoration is only ever observed because a runner
asks again, so the deadline is what makes the restore obligation above
reachable rather than nominal.

Because `checked_at` is the distributor's own read time rather than the
runner's receipt time (§5.3), that deadline is anchored upstream: the
distributor's cache and the runner's cache expire together instead of in
sequence, and `stale_after_seconds` is the whole window rather than half of
it.

Where the distributor declares a grace period (§5.7), the window this
bounds is `stale_after_seconds + grace_seconds` rather than
`stale_after_seconds` alone. Both terms are the distributor's own, so the
sum is knowable to it before it publishes either; what is required is that
neither is understated.

A runner **MUST NOT** cache an entitlement answer for longer than the
distributor declared. It **MAY** persist one across a restart, and where it
does it **MUST** persist `checked_at` alongside and evaluate the deadlines
against that value on load. A restart is not a new window: the answer is as
old afterwards as it was before.

Persisting is safe only because `checked_at` is the distributor's own read
time. An answer with no trustworthy expiry has to be discarded on restart,
which is what this specification required of an `active` answer until the
check response carried one (§5.3). An answer that carries its own expiry
does not: discarding it shortens nothing, since a runner that can reach the
distributor re-checks anyway, and it costs exactly the case §5.7 exists
for.

### 5.5 Not-entitled is indistinguishable from not-found

A distributor answering an entitlement check or a bundle request for an
agent the caller is not entitled to **MUST** answer `404` with code
`not_found`, and **MUST NOT** answer `403`.

A `403` confirms the agent exists. Over an unauthenticated-but-guessable
identifier space that turns the entitlement endpoint into an enumeration
oracle for the distributor's private catalogue. The cost of this rule is a
worse error message for a legitimate caller who mistyped an id; that is the
right trade.

**The same holds for the token.** A distributor **MUST NOT** distinguish an
unknown, revoked, or superseded token from a valid one presented for an
agent its buyer is not entitled to. Both answer `404` with `not_found`. The
enumeration argument applies to tokens exactly as it applies to agents: a
caller who can tell "this token is dead" from "you may not have this agent"
can sort guesses into two piles, and two piles is all an enumeration needs.

**A distributor answers no `401`.** No status it may send means
"authenticate and try again", because saying that is itself an answer — it
confirms the token was once real. §7's requirement that a rotated token's
predecessor stop resolving is discharged here: it stops resolving by
answering `404`, on the next request, like a token that never existed.

`unauthorized` (401) in §2.1's table is a runner's, and it refuses a
different credential for a different reason. A runner binding a non-loopback
interface requires inbound authentication of its own (§7): not a distributor
token, not presented to a distributor, and not a scheme this specification
defines. Nor does it have anything to enumerate — a runner serves exactly one
agent and carries no identifier in any of its paths (§2.2), so a caller told
that its credential was refused has learned only what the URL it already held
would tell it. The rule above protects a catalogue; a runner has none.

This costs a legitimate caller the same way the agent rule does. A runner
holding a malformed or long-revoked token is told `404` for as long as it
keeps asking, with nothing in the protocol to say that a new token is the
remedy. Telling a buyer their token needs replacing is the distributor's
job, out of band, where it can be done to a buyer rather than to anyone
holding a guess.

The local runner reporting its *own* state to its *own* client is the one
place `not_entitled` (403) is correct — there is nothing to enumerate.

**A distributor's own routing failures are invisible under this rule too.**
A distributor that resolves an identifier to something internal before it
can answer — a listing type, a shard, a catalogue partition (§1.5) — has a
resolution step that can miss, and a miss produces `404`: byte for byte the
answer a correct refusal produces. A buyer who owns the agent is told what a
stranger is told, and no status, no error `code` and no field anywhere in
this protocol separates the two.

So this class of bug will never be reported by a client, and a distributor
**MUST** cover each branch of that resolution with a test of its own, out of
band — one test per branch, not one per happy path. The failure worth naming
is a branch that does not exist at all: a listing type nobody wrote a case
for authenticates normally and then `404`s a buyer who owns the thing, and
every test written against the endpoint's success path still passes.

### 5.6 Bundle retrieval

```
GET  {distributor}/postern/v0/bundles/{owner}/{name}
Authorization: Bearer <token>
```

The identifier is addressed exactly as in §5.3.1: two path segments, never
percent-encoded, and `400` with `bad_request` for a string that does not
match §1.5's grammar.

- `200` — the bundle, `application/zip`, conforming to §6. The response
  **SHOULD** carry a representation digest
  ([RFC 9530](https://www.rfc-editor.org/rfc/rfc9530)):

  ```
  Repr-Digest: sha-256=:IAtqOIW3wX6iOiAGisKhISlQIEGkXVPSgiHZn2g1/7c=:
  ```

  `Repr-Digest` rather than `Content-Digest`, because what a client verifies
  is the bundle it keeps rather than the bytes of one hop: a content-coding
  or a range request changes the second and leaves the first alone, and a
  large download plausibly uses both. The colons are structured-field
  syntax rather than decoration. RFC 9530 obsoletes RFC 3230's
  `Digest: sha-256=<base64>`, which this specification carried until now.

- `404` — no such agent, or not entitled (§5.5).
- `410` with code `withdrawn` — previously entitled, and the agent has since
  been withdrawn. The body **SHOULD** carry the date access ends as
  `error.detail.access_ends_at`, an RFC 3339 timestamp, so a client can say
  something true about it. The envelope's root is closed (§2.1), so it rides
  inside `detail` rather than beside `error`.

A withdrawal answer in full:

```json
{
  "error": {
    "code": "withdrawn",
    "message": "This agent was withdrawn. Your access ends on 2027-08-15.",
    "detail": {"access_ends_at": "2027-08-15T00:00:00Z"}
  }
}
```

A distributor **SHOULD** rate-limit bundle retrieval per token and per
source address, and **SHOULD** count a rejected request against both buckets
rather than only the one that rejected it.

### 5.7 When the distributor cannot be reached

§5.4 obliges a runner to re-check once its answer expires. This section says
what happens when it tries and nothing answers, which is the common case the
rest of §5 leaves undefined: bought software, a distributor having a bad
afternoon, and no rule saying whether the agent runs.

**Unreachable** means a transport failure — DNS, TLS, a refused connection,
a timeout — or a `5xx`, or a response whose body is not a valid check answer
(§5.3). A `404` is **not** unreachable. It is an answer, and it is handled
at the end of this section.

#### 5.7.1 The declared grace

The check response carries `grace_seconds` (§5.3). While the distributor is
unreachable, a runner **MAY** go on running the agent past
`checked_at + stale_after_seconds`, and **MUST** stop on entitlement grounds
once `checked_at + stale_after_seconds + grace_seconds` has passed. For the
whole of that period it **MUST** report `entitlement.state` as `unknown`:
the answer it holds has expired and it has not been able to replace it,
which is precisely what that state means. This is the only thing in the
protocol that produces it.

A runner **SHOULD** keep attempting the check for the whole of the grace
period rather than waiting it out. The answer that ends grace early is also
the answer that renews the entitlement.

`grace_seconds` is **REQUIRED**, and `0` is a valid declaration meaning
*stop at the window*. A distributor that wants strictness says so, rather
than leaving it to be inferred from an absent field — the same reasoning
that makes `stale_after_seconds` required whether or not there is a cache.

**Why any grace at all.** A distributor outage is a failure the buyer did
not cause and cannot fix. A protocol that answers it by disabling everything
everyone bought converts one party's downtime into everybody's.

**Why it is bounded.** Going offline is the one thing a holder can always
do. An unbounded grace is a revocation model with a trivial bypass, and
§5.4's obligations would be nominal.

**Why the distributor declares it.** The same reason it declares
`stale_after_seconds`: the party carrying the revocation risk sets the
bound, and the party that would benefit from a longer one is running the
agent on hardware it controls. A bound chosen by the party it constrains is
a preference.

§5.4 calls `stale_after_seconds` the honest upper bound on how long a
revoked entitlement can keep working. With a grace period declared, that
bound is `stale_after_seconds + grace_seconds`, and this specification says
so rather than leaving the second term to be discovered. Both numbers are
the distributor's own, so the sum is knowable to it before it publishes
either.

#### 5.7.2 A restart is not a new window

A runner **MAY** persist a check answer across a restart. Where it does, it
**MUST** persist `checked_at` with it and evaluate both deadlines against
that value on load. A restart **MUST NOT** yield a fresh window, a fresh
grace period, or a later `checked_at` than the distributor gave.

That is what makes an offline restart survivable at all. Without it a runner
that reboots with no network holds nothing, can obtain nothing, and cannot
tell an entitlement it had five minutes ago from one it never had — so the
machine that worked before the power cut does not work after it, for a
reason unrelated to whether anybody is entitled to anything.

#### 5.7.3 A runner that has never been told anything

Grace counts from `checked_at`, and a runner that has never completed a
check does not have one. It therefore **MUST NOT** run the agent on
entitlement grounds, however long it has been trying.

- `status` reports `unknown` with no `checked_at`.
- `run` and `stream` answer `503` with `unavailable` (§2.1) — retrying may
  genuinely help, once the network returns. `not_entitled` would assert
  something no distributor has said.

A check that answered `404` has completed, whatever it said, so a runner
holding one is in §5.7.4 rather than here — including where that `404` was
the first answer it ever got.

The two shapes of `unknown` are told apart by that timestamp: `unknown` with
a `checked_at` is a runner inside grace, still running, with a deadline;
`unknown` without one is a runner that cannot start. A client can say which
without a further field, and the distinction costs nothing in practice —
retrieving the bundle required reaching the distributor (§5.6), so a runner
that has never reached it has nothing to run either.

#### 5.7.4 A `404` is an answer, not an outage

A runner that receives `404` from the check **MUST** stop honouring the
entitlement immediately. No grace applies, because nothing failed: the
distributor was reached and declined to vouch for this buyer.

- `status` reports `revoked`.
- `run` and `stream` answer `403` with `not_entitled` (§2.1) — the one place
  that code is correct, a local runner reporting its own state to its own
  client.

`revoked` is reported even though the runner cannot tell a withdrawn
entitlement from one that never existed, or from a token that no longer
resolves. §5.5 makes those three deliberately indistinguishable, and that
indistinguishability reaches the runner's vocabulary too. What is common to
all three — and all a client can act on — is that the entitlement is not in
force. A runner **SHOULD NOT** tell the user more than that.

§4.4 requires `checked_at` and `stale_after_seconds` wherever the state is
`revoked`, and a `404` carries neither: §5.5 requires that body to be
constant, and attaching fields to it would rebuild the oracle the rule
exists to prevent. So a runner reporting `revoked` after a `404` supplies
both itself — `checked_at` is its own receipt time, and
`stale_after_seconds` its own re-check cadence. It **SHOULD** reuse the last
`stale_after_seconds` the distributor gave it in place of that cadence;
where it has never been given one, its own stands. §4.4's rule against
re-stamping is not engaged, because it forbids discarding an anchor the
distributor supplied, and here there is none to discard.

That last case is not exotic. A first check answering `404` is what a token
revoked before its runner ever ran produces, and what a runner pointed at
the wrong distributor sees; there is no earlier answer anywhere to reuse.
A runner that omitted the field instead would answer `status` with a payload
§4.4 and `status.schema.json` both reject.

A runner supplying that number itself is safe here in a way it would not be
under `active`. §4.4 calls it the same bound either way and says what does
change: who it protects — under `active`, how long a revoked entitlement
keeps working, and under `revoked`, how long a restored one stays unusable.
The first is the distributor's risk, so §5.7.1's reasoning applies and the
party carrying it sets the bound, a longer one being exactly what a holder
would choose. The second falls on the runner's own operator, who is the
party waiting for that restore and gains nothing by overstating it. So a
client reads the field the same way either way — when this runner will ask
again — and nothing needs to mark which party supplied the number.

**Every case, in one table.** `describe` and `status` are unaffected
throughout: §4.1 requires `describe` to answer without an entitlement and
§4.4 requires `status` to answer at Level 1, so a runner that cannot run its
agent still says what it is and what is wrong. Only `run` and `stream`
stop.

| Situation | `entitlement.state` | `run` and `stream` |
|---|---|---|
| Answered `active`, within the window | `active` | Run. |
| Answered `revoked` | `revoked` | `403` `not_entitled` |
| Answered `404` | `revoked` | `403` `not_entitled` |
| Unreachable, still within the window | `active` | Run. |
| Unreachable, past the window, within grace | `unknown`, with `checked_at` | Run. |
| Unreachable, past the window and grace | `unknown`, with `checked_at` | `503` `unavailable` |
| Unreachable, never checked at all | `unknown`, no `checked_at` | `503` `unavailable` |
| No distributor configured (§5.1) | `not_required` | Run. |

The rule underneath the table is worth stating on its own, because it is the
one an implementer will apply to a case this table does not list:
**unreachable answers `unavailable`, refused answers `not_entitled`.** A
runner that cannot find out says so and invites a retry; a runner that has
been told no does not pretend the answer might change on the next request.

*Where* in a request these refusals fall is §4.6, step 2: ahead of the media
type, the inputs and the environment, and behind only the level check. That
placement follows from the sentence above — a `400` invites the retry the
second half of it forbids.

---

## 6. Packaging

A bundle **MUST** be a valid [Agent Plugins
v1.0.0](https://agent-plugins.org) plugin: a root `plugin.json` carrying
`$schema` set to
`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`, plus whatever
`skills/` and `mcp.json` the agent needs.

Postern adds no files to that layout and changes none of it.

Distributor-specific data — entitlement identifiers, catalogue URLs,
verification records — **MUST** ride the `extensions` member under a
reverse-domain namespace the distributor controls, which is the mechanism
Agent Plugins sanctions for exactly this:

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
  "name": "market-research-crew",
  "version": "1.3.0",
  "extensions": {
    "com.example.marketplace": {
      "agent_id": "acme/market-research-crew",
      "listing_url": "https://example.com/listings/market-research-crew"
    }
  }
}
```

A runner **MUST** ignore an `extensions` namespace it does not recognise.
Two distributors' namespaces coexisting in one bundle is valid.

---

## 7. Security considerations

- **Bearer tokens over TLS only, except on loopback.** A distributor
  **MUST** serve over HTTPS, and a runner **MUST** refuse to send a token
  over plaintext HTTP. One exception applies to both halves, because a rule
  relaxed on one side and absolute on the other would license a runner to
  speak plaintext only to a peer that may not answer it: a distributor
  reachable only on loopback **MAY** serve plaintext, and a runner **MAY**
  send a token where the peer address of the connection carrying it is a
  loopback address (`127.0.0.0/8`, `::1`).

  The exception is here because the rule without one does not survive
  contact with someone building a distributor. Developing against
  `http://127.0.0.1:8080` is ordinary, and there is no network on that path
  to intercept — anything positioned to read loopback traffic is already
  running code on the machine, where the runner's own configuration holds
  the token anyway. A **MUST** with no room for a legitimate case is not
  obeyed but routed around: a flag that turns the check off, a self-signed
  certificate with verification disabled, a fork. Each is wider than the
  exception it stands in for, and each outlives the afternoon it was added
  for. §5.4 declines to demand instantaneous revocation on the same
  reasoning. It is for that reason not an operator opt-in either — a switch
  that has to be on for ordinary local development is on in every
  developer's configuration, and that is the habit which reaches
  production, whereas an exception narrow enough to need no switch leaves
  nothing to leave on.

  **The condition is the address, not the name.** `localhost` is a name and
  a resolver decides what it means; `127.0.0.1` needs no resolver at all. So
  a runner **MUST NOT** decide this by matching the hostname it was
  configured with, and **MUST** evaluate it against the address it is
  actually connected to — resolving a name to loopback and then opening a
  connection leaves a window in which the second answer differs from the
  first.

  A runner **SHOULD** report taking the exception to its operator, in a
  startup line naming the base it is about to talk to in plaintext.
  Deliberately not a field in `status`: a client cannot fix a distributor
  base URL, and the person who can is not reading `status`.
- **Loopback binding.** A runner binding a non-loopback interface exposes
  `run` to its network with no authentication defined by this specification.
  Runners that do so **MUST** require authentication of their own; Postern does
  not specify it, because a runner reachable from off-machine is outside the
  threat model this version addresses.

  The *scheme* is unspecified; the *refusal* is not. A request that fails such
  a runner's own authentication **MUST** be answered `401` with `unauthorized`
  in §2.1's envelope, so that a client meets one error shape across this
  protocol rather than a second one at its edge — and so that a client can tell
  a credential it must fix from a path that does not exist. The credential
  **MUST NOT** appear in `describe` or `status`: §4.1.3 keeps a *provider* key
  out of the protocol, and a runner that answered with its own inbound token
  would have published, to an unauthenticated reader of `status`, the value
  that reader was missing. A runner requiring one also names `Authorization` in
  its preflight (§2.3), for the reason given there.

  None of this reaches a loopback runner. A runner that requires nothing
  answers exactly as it did before — the bundle that ships to a buyer's own
  machine is the same bundle — and §2.3's origin check remains the entirety of
  its access control against a browser.
- **A browser is a client the user did not choose.** The bullet above is
  about who can reach the port. Every page the user visits can reach it — a
  loopback runner is one `fetch` away from any origin on the web, and what
  has been keeping those calls out is the same-origin policy rather than the
  network. So `Access-Control-Allow-Origin: *` on a runner does not widen
  the exposure above; it opens a second one, granted to every origin on the
  web instead of to the local network, against a surface with no
  authentication and a `write_tools` list (§4.1.2) at the end of it. §2.3 is
  the answer, and it defaults to refusing for this reason. Note what the
  browser does and does not buy there: a cross-origin `describe` or `status`
  is *served* and then withheld from the page, which costs nothing only
  because both are side-effect free, while `run` and `stream` are stopped
  before they are served — but only for as long as they preflight, which is
  why §2.3 obliges a runner to *refuse* a body that is not
  `application/json` rather than merely to expect one.
- **Credentials never traverse the protocol.** §4.1.3 is a security
  property, not a convenience. A `describe` or bundle carrying a credential
  value is nonconformant, and a client encountering one **SHOULD** refuse to
  proceed.
- **`write_tools` is advisory to the client and load-bearing for the user.**
  Postern cannot enforce that a runner's declared `write_tools` is complete. A
  distributor that verifies agents **SHOULD** verify this field.
- **Token rotation invalidates immediately.** A rotated token's predecessor
  **MUST** stop resolving on the next request, not at the end of a cache
  window. Revocation of *entitlement* may lag (§5.4); revocation of a
  *token* may not. Stopping means answering `404` with `not_found`,
  indistinguishably from a token that never existed (§5.5) — there is no
  `401` to fall back on.

---

## 8. Sigrix profile

*This section is normative for [Sigrix](https://sigrix.io) as a distributor
and informative for everyone else. Postern is usable with no reference to it.*

- Namespace: `org.sigrix`, carrying `agent_id` and `listing_url`.
- Tokens are 32 random bytes, URL-safe base64, stored as SHA-256. One active
  token per buyer; rotation revokes every predecessor.
- `stale_after_seconds` is 60, and `grace_seconds` is 86400 — long enough
  to ride out an outage, short enough that a refunded buyer is not still
  running a week later.
- Withdrawn listings answer `410` with a twelve-month tail from the
  withdrawal date for buyers who owned them.
- A version answer for §4.4's `update` is served at
  `GET /postern/v0/versions/{owner}/{name}`, and reads no bearer token: it
  names no buyer and carries only the identifier it was asked about and a
  version string, so there is nothing in it to protect and §5.5's
  indistinguishability rule has nothing to hide. It answers for the listing
  types Sigrix can resolve a version for and `404`s for the rest, which a
  runner reports as `unreachable` rather than as an update. The payload is
  [`version.schema.json`](schemas/version.schema.json): the shape is fixed
  here even though the path is not, so a second distributor offering the
  same answer answers it the same way.

---

## Appendix A · Changes

**Unreleased** — corrections made before the first tagged release.

- §4.3 states that `done` repeats `start`'s `run_id`, and that a runner
  **MUST NOT** report two identifiers for one run. The rule was asserted in
  `stream-event.schema.json` — whose `start` description has always said it
  carries *"the `run_id` that the `done` payload repeats"* — and
  demonstrated in `examples/stream.txt`, where both name `01JD8XW2Q9`. The
  prose said only that `start` carries `run_id`, so the correlation was
  documented everywhere except the document that binds it. It spans two
  events, which is why neither schema can reach it and why it is asserted
  the way §4.3's `delta` concatenation rule already is (§4.3, §4.5).
- `status.agent`, `status.entitlement` and `describe.output` are
  **REQUIRED**, which the sections reasoning about them assumed and the
  schemas did not carry. Every top-level member §4.4 marks, it marks
  **OPTIONAL** — `limits`, `update` — and the two it marks **REQUIRED** are
  conditional members inside `entitlement`, so `agent` and `entitlement`
  themselves were unmarked rather than decided, and
  `status.agent` required nothing at all inside it, admitting `{"agent":
  {}}` while `describe` required `id`, `name` and `version`. Each omission
  cost something stated elsewhere: §5.1 **MUST**s a runner with no
  distributor to report `entitlement.state` as `not_required`, and saying
  nothing is indistinguishable from a runner that has not implemented
  entitlement; §1.5's "one agent, one identifier, spelled one way in all
  four places" is false of a `status` that names none, and §2.2's identity
  rule cannot be checked against a runner that omits it — such a runner is
  not caught disagreeing with its own `describe`, it cannot be asked;
  `run` and `stream` both **MUST** carry an `output` with a `type`, and
  §4.1's `describe` is the only place a client can learn that type before
  it asks. Only `agent.id` is required within `status.agent`. No example,
  fenced block or reference-runner path in this repository emitted a
  document any of this now refuses (§1.5, §2.2, §4.1.4, §4.4, §5.1).
- §2.2 says no runner *path* carries an agent identifier, where it used to
  say none of the four verbs did. The narrower claim was false as written —
  `describe` carries `agent.id` and §1.5 says so — and only the addressing
  reading supports the conclusion drawn from it, that a client **MAY** treat
  a runner's port as its agent's address. The next sentence, contrasting
  with distributor paths that *address* an agent by identifier, always meant
  the same thing (§1.5, §2.2).
- `describe.schema.json` enforces the pairing §4.1.1 already stated between
  an input's `type` and its `default`. The sentence fixing the value space —
  *text and select carry a string, number carries a number* — was prose
  only, so `{"type": "number", "default": "not a number"}` validated
  cleanly, as did a numeric default on a text input. Nothing in the
  repository violated it, which is why it went unseen. `null` stays legal
  under every type, since it is what says no value was supplied. The two new
  branches are keyed positively on the types they constrain, never
  negatively on the ones they do not: this section anticipates a fourth
  type, and a branch reading *anything that is not `number`* would constrain
  it the moment it arrived. `run-request.schema.json` deliberately does not
  follow — the values there sit in a different document from the
  declarations that type them, so it admits the union of the three value
  spaces and §4.2 leaves the per-input check to the runner (§4.1.1, §4.2).
- §4.1.1 states the grammar an input `key` has to satisfy.
  `describe.schema.json` has enforced `[A-Za-z0-9_.-]+` from the first
  commit and §4.1.1 said only that a declaration **MUST** carry the member,
  so a key with a space in it was refused with no sentence to cite — and
  nothing asserted the pattern either way, which by `validate.py`'s own
  doctrine made it a rule deletable without anything going red. The reason
  is now stated with it: a client renders a key as the *name* of a thing
  and `label` carries the human-facing name, so the key does not have to,
  and excluding whitespace and non-ASCII keeps two keys that look alike
  alike. Its length stays unbounded, unlike an agent identifier's, because
  a key crosses no trust boundary — it travels between one runner and a
  client already talking to it, never to a distributor. The grammar binds
  the declaration and reaches `run` through §4.2's "map keyed by
  `describe`'s input keys" rather than being restated there (§1.5, §4.1.1,
  §4.2, §5.3).
- §4.1.3 states what a `credentials[]` entry carries, and what its closure
  is for. `describe.schema.json` has always closed that object, and it was
  the only statement of the entry's shape anywhere — §4.1.3 described the
  rule and never the record. The closure is not a list of today's members:
  §4.1.3's own claim that there is *nowhere in the protocol for a secret to
  travel* is true only while the object is closed, since an open one would
  make `value` beside `env` schema-valid, along with every other spelling
  of the leak the section forbids. It catches the structural half and not
  the whole of it — a value written into `purpose` is a conforming shape
  carrying a nonconformant string, which only reading the field finds. The
  cost is named too: a member added here later is additive for runners and
  for any client that does not use an emit-side schema as an acceptance
  filter, and breaks only one that does. It is the only closed object in
  these schemas outside `error.schema.json`'s root, which
  [`schemas/README.md`](schemas/README.md) now records as a fourth place
  the emit/accept difference is load-bearing rather than as three
  (§2.1, §4.1.3).
- A runner **MUST** perform the credential check, not merely order it.
  §4.6 placed the environment check last and gave `missing_credential` its
  producing rule, but bound only the sequence — so a runner that never
  inspected its environment never reached the condition, started the agent,
  and answered `agent_error`. Two conforming runners therefore answered one
  request differently, a `424` naming the variable to set against a `500`
  naming nothing, and a client could not tell which it held. It is a
  **MUST** rather than a **SHOULD** because every runner can perform it:
  `describe` declares credentials by environment variable name (§4.1.3) and
  every runner answers `describe` (§4.1), so the list is already in hand.
  `status.credentials` staying **OPTIONAL** is not the same obligation — it
  governs publishing the satisfied set, not checking one before a run
  (§4.1.3, §4.4, §4.6).
- Added `unauthorized` (401), the answer a runner gives when it requires
  inbound authentication of its own and a request does not satisfy it (§2.1,
  §7). §7 has always obliged a runner binding a non-loopback interface to
  authenticate its callers while specifying no scheme for it, which left the
  *refusal* undefined too — so such a runner had to answer either a code
  meaning something else or one outside §2.1's table, and a client met a
  second error shape at exactly the deployment where it had least context.
  The scheme stays unspecified; only the refusal is fixed. §5.5's "Postern
  defines no `401`" is narrowed to the distributor it was always about: its
  reasoning is that a `401` confirms a token was once real and so sorts
  guesses into piles, which needs a catalogue to enumerate, and a runner
  serving one agent behind an identifier-free path space (§2.2) has none.
  §2.3 gains `Authorization` in the preflight's `Access-Control-Allow-Headers`
  for such a runner — a browser cannot send a header its preflight did not
  admit, so without it a page is the one client kind that could never
  authenticate — and a runner requiring nothing **SHOULD NOT** name it, since
  the header is off the safelist and admitting it preflights a `describe`
  that would otherwise go without one (§2.1, §2.3, §5.5, §7).
- A runner's refusals are ordered: it decides what the request says before
  it inspects what it holds, so a `run` that both omits a `required` input
  and meets a runner missing a credential is answered `bad_request` rather
  than `missing_credential` (§4.6). Both were correct under the previous
  text and nothing chose between them, which left §4.2's **MUST**
  untestable on any runner whose environment was incomplete — the ordinary
  state of one being brought up — and made a malformed request's answer
  depend on the operator's deployment. `missing_credential` gains the
  producing rule it never had: it was the only code in §2.1's table that no
  section required, defined and never asked for. §4.5's capacity refusal is
  deliberately left unordered (§2.1, §4.2, §4.6).
- A client **MUST** tolerate an error `code` it does not recognise, so that
  adding a code stays an additive change (§2.1).
- Added `not_implemented` (501). A Level 2 runner answers `stream` with it
  rather than with `unavailable`, which is now 503 only (§2.1, §4.3).
- Added `withdrawn` (410), so the withdrawn-agent response in §5.6 has a
  code and can be constructed at all (§2.1, §5.6).
- The entitlement check response now carries `checked_at`, defined as the
  moment the distributor last consulted the authority rather than the moment
  it answered. A runner propagates it unchanged and **MUST NOT** re-stamp it,
  so the distributor's cache and the runner's cache share one deadline
  instead of stacking (§5.3, §5.4).
- `entitlement.checked_at` is now **REQUIRED** in `status` when the
  entitlement state is `active` or `revoked` (§4.4).
- The `delta` reconstruction rule applies only when a `delta` is emitted, so
  a Level 3 runner that cannot produce incremental text stays conformant by
  emitting none (§4.3).
- A runner serves exactly one agent, stated normatively rather than left to
  be inferred from the absence of an identifier in its paths. `not_found`'s
  "no such agent" meaning is distributor-side only; on a runner the code can
  only mean an unimplemented path. Each code in the §2.1 table now says
  which side emits it (§2.1, §2.2).
- The error envelope's root is closed by design — nothing sits beside
  `error`, so the envelope has one extension point rather than two. The
  schema already asserted this; §2.1 now states it, with the reason and with
  the fact that it constrains what an implementation emits rather than
  licensing a client to reject what it receives (§2.1).
- The §5.6 `410` body carries the date access ends as
  `error.detail.access_ends_at`. The closed root leaves `detail` as the only
  place it can go, and the specification previously left it unplaced (§5.6).
- The subprocess discovery line is `POSTERN_PORT=<port>`, replacing the
  mixed-case form (§2).
- Removed `verification` from the `org.sigrix` member list (§8).
- A runner answers *any* verb above its declared level with `501` and
  `not_implemented`. The rule was previously stated only for a Level 2
  runner asked to `stream`, leaving a Level 1 runner asked to `run` with no
  defined answer; it now sits in §3, so it also covers any level added later
  (§3, §4.2, §4.3).
- Narrowed input values to what the three declared types can produce.
  `run`'s `inputs` map and an input's `default` no longer admit a boolean,
  which none of `text`, `number` or `select` yields. Adding a fourth type
  later is additive; withdrawing a value shape a runner had relied on would
  not be (§4.1.1).
- Removed `status` from the `run` response. Its only legal value was `ok`,
  because §2.1 routes every failure through a non-2xx error envelope, and
  the partial-result case it might have grown into cannot be carried by a
  value an older client would read as a complete result (§4.2).
- §5.5's indistinguishability rule covers token state, not only agents. An
  unknown, revoked, or superseded token answers `404` with `not_found`, the
  same as a valid token presented for an agent the buyer may not have, and
  Postern defines no `401` — a status meaning "authenticate and try again"
  would confirm the token was once real. §5.3's success rule gains the
  failure branch it presupposed, and §7's "stop resolving" now names the
  answer it stops with (§2.1, §5.3, §5.5, §7).
- `entitlement.stale_after_seconds` is now **REQUIRED** for `revoked` as
  well as `active`, matching `checked_at`: it is required wherever a check
  actually happened. Without it a runner held a timestamp and no deadline,
  so §5.4's re-check rule could not be evaluated for a `revoked` answer and
  the restoration §5.4 obliges a distributor to support could never be
  observed (§4.4, §5.4).
- `agent_id` has a grammar: two parts of lowercase ASCII alphanumerics, `-`
  and `.`, joined by one `/`, bounded at 128 characters and compared
  octet-for-octet with no folding or normalisation of any kind (§1.5). It was
  previously only a non-empty string, and the canonical
  `acme/market-research-crew` did not fit the single path segment the
  distributor endpoints gave it. It now occupies two segments and is never
  percent-encoded — the grammar admits no character a path requires encoding
  for — and a string that fills two segments without matching the grammar is
  answered `400`, an answer a distributor **MUST** be able to produce without
  consulting its catalogue, which is why it does not weaken §5.5 (§5.3.1,
  §5.6). The identifier carries no listing type, so a distributor dispatching
  on one resolves it itself and **MUST** test each branch out of band: §5.5
  makes a missing branch indistinguishable from a correct refusal, so no
  client will ever report it (§5.5). `agent.id` carries the pattern and the
  bound in `describe.schema.json` and `status.schema.json` (§4.1, §4.4).
- The entitlement check has a schema, and its response carries `postern`
  like every other success payload in the protocol. It was the only one
  without a version marker, and a distributor's version is inferable from
  nothing else — [VERSIONING.md](VERSIONING.md) forbids reading it off the
  path prefix. Freezing the shape settled two things the prose had left
  loose: `stale_after_seconds` is sent whether or not the distributor
  caches, because §5.4's re-check deadline and §4.4's `status` report both
  need it and neither is conditional on a cache existing; and `agent_id`
  echoes the identifier the request addressed, octet-for-octet, so a
  mismatch is a failed check rather than something to reconcile. The
  `validate.py` skip over the §5.3 block is gone with it — that payload was
  checked by nothing until now (§5.3).
- `Digest: sha-256=<base64>` becomes
  `Repr-Digest: sha-256=:<base64>:` on a bundle response. RFC 3230 was
  obsoleted by [RFC 9530](https://www.rfc-editor.org/rfc/rfc9530) before
  this specification shipped, and the replacement is a structured field, so
  the colons are syntax rather than decoration. `Repr-Digest` rather than
  `Content-Digest` because a client verifies the bundle it keeps, not the
  bytes of one hop (§5.6).
- A runner has defined behaviour when the distributor cannot be reached
  (§5.7). The check response declares `grace_seconds` beside
  `stale_after_seconds`, and a runner whose answer has expired with nothing
  answering keeps running until
  `checked_at + stale_after_seconds + grace_seconds`, reporting `unknown` —
  the state §4.4 has always listed and nothing in §5 produced. The honest
  upper bound in §5.4 is now the sum of the two rather than the first alone,
  and is stated as such; both terms are the distributor's own, so it can
  evaluate the sum before publishing either. `0` is a valid grace and means
  *stop at the window*, so strictness is declared rather than inferred from
  an absent field. §8 puts Sigrix's at 86400 (§4.4, §5.3, §5.4, §5.7, §8).
- §5.4's rule against persisting an `active` answer across a restart is
  replaced. A runner **MAY** persist an answer, provided it persists
  `checked_at` with it and evaluates the deadlines against that value on
  load; a restart yields no fresh window. The old rule was written when the
  check returned no timestamp at all, so a persisted answer had no
  trustworthy expiry and discarding it was the only bound available. With
  the anchor returned and propagated unchanged (§5.3), discarding shortens
  nothing — a runner that can reach the distributor re-checks anyway — and
  costs the case §5.7 exists for, where a machine reboots with no network
  and cannot tell an entitlement it held five minutes ago from one it never
  had (§5.4, §5.7).
- A `404` from the check is an answer rather than an outage: no grace
  applies, the runner stops at once, reports `revoked`, and answers `run`
  and `stream` with `403` `not_entitled`. It reports `revoked` even though
  §5.5 stops it distinguishing a withdrawn entitlement from one that never
  existed or a token that no longer resolves — what the three have in common
  is all a client can act on. A runner that has never completed a check does
  not run at all, reports `unknown` with no `checked_at`, and answers `503`
  `unavailable`. The rule under both: unreachable answers `unavailable`,
  refused answers `not_entitled` (§5.7).
- Browser clients have a defined answer: a runner **MUST** answer the
  `OPTIONS` preflight on `run` and `stream`, and the origin policy behind it
  is the operator's, defaulting to refusal rather than to
  `Access-Control-Allow-Origin: *`. The specification named a web UI as a
  client kind and said nothing about CORS, so a fully conforming runner
  could be unreachable from one — while the obvious remedy, a wildcard,
  would hand `run` and its `write_tools` to every page the user visits.
  A runner **MUST** now also reject a `run` or `stream` body whose
  `Content-Type` is not `application/json`: `application/json` is what makes
  the request preflight at all, and a runner accepting `text/plain` executes
  the agent for any origin without one, which is the whole of the preceding
  rule undone (§2.3, §7).
- A run in flight has a defined life (§4.5). A runner **SHOULD** abort the
  agent when the client disconnects, on `run` and `stream` alike, and
  **MUST NOT** deliver an abandoned run's output anywhere else — there being
  no callback and no verb that takes a `run_id`, which is also why an abort
  cannot be reported and a reopened `stream` is a new run rather than a
  resumption. An abort is not a rollback: §4.1.2's `write_tools` name things
  that may already have happened, and a retry without an `Idempotency-Key`
  buys the work twice. Previously nothing said whether closing a laptop lid
  stopped an agent from spending money (§4.2, §4.3, §4.5).
- Added `run_timeout` (504), and with it a runner's right to impose a maximum
  run duration. `agent_error` and `unavailable` both nearly fit and both
  mislead — one reports a working agent as broken, the other invites a retry
  into the same deadline. A runner imposing a limit **MUST** declare it as
  `status.limits.max_run_seconds` and **MUST NOT** declare one longer than it
  can enforce, and the refusal **SHOULD** carry it as
  `error.detail.max_run_seconds` (§2.1, §4.4, §4.5).
- Concurrency is the runner's to decide and discoverable rather than assumed:
  it **MAY** refuse an overlapping run with `503` `unavailable`, needing no
  new code because the client's move is the one that code already asks for,
  and **SHOULD** declare `status.limits.max_concurrent_runs`.
  `status.state: "running"` observes that a run is in flight and promises
  nothing about admission — a client **MUST** be ready for `503` whatever
  `status` last said, since the slot can go elsewhere between the two calls
  (§4.4, §4.5).
- `output` has a section of its own (§4.1.4). `text` is the v0 output type
  by decision rather than by accident of the examples, matching what §4.1.1
  already said for inputs — and an unrecognised `output.type` now has a
  receive-side rule, which is the part that changes the contract rather than
  recording it. It is deliberately not the rule the other four extensible
  surfaces use: an error `code`, a `stream` event name, an input `type` and a
  `validation` member are all things a client may ignore, and `output.type`
  is what says how to read `value`, so ignoring it misreads a known rather
  than tolerating an unknown. A client **MUST NOT** present `value` as text,
  **MUST NOT** report the run as failed — a `200` it cannot render is a run
  that succeeded — and **SHOULD** name the type it was given. The rule has to
  exist before a second output type can, or the addition breaks every client
  written against the closed set: the ordering the error-code enum already
  paid for (§2.1, §4.1.1, §4.1.4).
- `stream`'s event payloads have schemas, and its rules about them are
  stated rather than implied by a table cell. A `step` carries at least
  `name` and `status`; `latency_ms` is an elapsed time, so it is reported on
  `finished` and a runner **MUST NOT** emit it on a `started` step, where
  there is nothing yet to measure — a client receiving one anyway ignores it
  rather than rejecting the event.
  [`stream-event.schema.json`](schemas/stream-event.schema.json) covers the
  three payloads this specification defines itself; `done` and `error` carry
  bodies §4.2 and §2.1 already define, and the SSE framing spans events, so
  neither is expressible there (§4.3).
- The plaintext-token prohibition has a loopback exception, on both halves:
  a distributor reachable only on loopback may serve plaintext, and a runner
  may send its token when the peer address is loopback — the one case where
  the network the TLS rule exists to protect is not there. The condition is
  the address connected to rather than the hostname configured, because a
  name is resolved by something the runner does not control, and resolving
  before connecting leaves a gap between the two answers. A runner
  **SHOULD** say when it takes the exception, to its operator rather than in
  `status` (§7).

- `output.type` gains `bytes`, for an agent whose result is a file rather
  than prose. `value` carries the artifact base64-encoded and stays a JSON
  string, so no envelope changes shape; `media_type` is **REQUIRED** beside
  it and is an open RFC 6838 string, because an enum would need a
  specification revision per format. A `bytes` run emits no `delta` — §4.3's
  invariant is text-shaped, and base64 fragments would satisfy it while
  giving a client nothing but the encoding to print — so it reports progress
  with `step` instead. `describe.output.example` stays text-only, and a
  runner bounding what it returns declares `limits.max_output_bytes` in
  `status`, measured before base64. Additive: a client written against
  §4.1.4's receive-side rule survives it (§4.1.4, §4.3, §4.4).
- A runner whose first-ever check answers `404` reports `revoked` with its
  own re-check cadence as `stale_after_seconds`. That fallback was already
  the rule, but reachable only by reading "its own re-check cadence" as the
  field. The clause that did name the field attached a **SHOULD** — reuse
  the distributor's last value — which a first check cannot satisfy, so the
  one case a plain misconfiguration produces was the one left unstated, and
  the conformant reading was the harder of the two to find. §5.7.4 also now
  answers whether a client can tell a runner-supplied number from a
  distributor's: it cannot, and does not need to, because the bound protects
  the runner's own operator under `revoked` where it protects the
  distributor under `active`, and only the second party gains by
  overstating it. §5.7.3 says that a `404` is a completed check and so not
  its case, and `status.schema.json`'s two descriptions carry the same
  exception (§5.7.3, §5.7.4).
- The `delta` concatenation invariant gains the receive-side rule it was
  missing: where the accumulated deltas and `done`'s `output.value` disagree,
  a client **SHOULD** prefer `done`, and **MUST NOT** report the run as
  having failed on that ground. It was the one place a client could be
  surprised with nothing stated for it — every other one has a rule, and
  §4.1.4's is the near neighbour, separating a run that succeeded from a
  client that rendered it wrongly. A **SHOULD** rather than a **MUST**
  because a client writing deltas to standard output has already emitted
  them. The invariant itself is unchanged and still binds the runner (§4.3).
- A runner that honours an `Idempotency-Key` declares it, as
  `capabilities.idempotent_retry` in `describe`. §2.3 already varied a
  browser client's preflight by whether the runner honours the header, so
  the one answer was being advertised in a CORS header to a client with no
  protocol-level way to ask for it, and §4.5 had since made being charged
  twice a documented outcome of an ordinary disconnect. Declaring it forced
  fixing what honouring means, which the specification had never said: a
  repeat key **MUST NOT** execute the agent again and **MUST** be answered
  with the result of the first execution, a produced error included, while a
  request refused before the agent ran binds no key. Absent and `false` read
  identically, so a client written before the field is right about every
  runner that had not made the promise. §4.5 stops naming the key as the
  remedy for the disconnect it can do least about — the run it would
  deduplicate against was aborted and its output discarded — and says that
  answering a retry carrying that run's key is not the late delivery its
  discard rule forbids. A runner declaring the field **MUST** admit the
  header in its preflight, or the promise holds for every client kind except
  the browser (§2.3, §4.1.2, §4.2, §4.5).
- `run_id` is unique **per execution** rather than per response, so a
  replayed idempotent answer carries the `run_id` of the execution it
  replays. The uniqueness **MUST** predates the replay rule by some distance
  and the two were never read together: a strict reader of the older sentence
  is pushed toward minting a fresh identifier for the replay, which names an
  execution that never ran and so has no line in any log — defeating the
  correlation the same sentence's **SHOULD** exists for. Nothing an
  implementer builds under either reading fails, which is why this needed
  saying rather than leaving to sense (§4.2).
- An `Idempotency-Key` identifies a request rather than a caller, and
  `idempotency_conflict` (409) is what a runner answers when one is presented
  with different `inputs`. #89 keyed the replay rule on the header alone,
  which answers the second request with a result computed for inputs the
  caller never sent — at `200`, in a valid envelope, undetectable on either
  side. That is the failure §4.1.4 argues hardest against, reached through a
  header a client adds in order to be careful, and worst on exactly the agent
  §4.1.2 warns about. `bad_request` nearly fits and misleads: nothing in the
  body needs fixing, and `400` already answers a failed `validation`, so a
  client could not tell "your inputs are wrong" from "that key is spoken for"
  — refusals whose remedies are opposite. Inputs are compared by value on the
  decoded map, so re-serialising a request cannot manufacture a conflict, and
  a `409` executes nothing and so binds no key. Retention is the runner's to
  choose and a client **MUST NOT** assume a window, since a runner forgetting
  after a second satisfies every word of the replay rule; a runner that can
  state one **SHOULD** declare `status.limits.idempotency_retention_seconds`,
  the one member of `limits` bounding a promise rather than a run (§2.1,
  §4.2, §4.4).
- `capabilities.streaming` is **withdrawn**. It appeared in §4.1's example
  and in `describe.schema.json` — the one property there carrying no
  `description` — and no prose ever defined it, which left `capabilities`
  documenting one of its two booleans once #89 gave `idempotent_retry` a
  treatment. Defining it was the alternative and would have frozen a
  contradiction: §3 makes `level` in `status` the authority and forbids
  assuming a level read from anywhere else, so a client acting on
  `streaming` breaks a **MUST**, and a client that may not act on a field
  has decoration. Nothing bound the two, so `{"level": 2}` beside
  `{"streaming": true}` was a payload no rule refused. This is the same
  refusal of a second vocabulary that removed `run`'s `status` field and
  kept `0` out of `max_concurrent_runs`, and pre-1.0 is the only cheap
  moment for it — VERSIONING.md's additive-only rule binds after. It breaks
  no runner: `capabilities` is open, so one still emitting the field
  validates unchanged and merely means nothing by it. §4.1 now says
  `capabilities` describes the agent and `level` the deployment, which is
  the line that keeps the field from being re-proposed. The conformance
  checker's `streaming`/`level` agreement warning goes with it — that rule
  was the tool's own inference from §3, with no sentence to cite (§3, §4.1).
- `status` gains an **OPTIONAL** `update` block, reporting what a runner
  learned when it asked its distributor whether a newer version of the agent
  exists: a `state` of `not_required`, `unreachable`, `current` or
  `update_available`, with the running version as `current` and the reported
  one as `latest`. It is present only where a check ran, so a runner
  configured for none omits it — a different fact from a check that ran and
  found no distributor. An unreachable check is explicitly not a failure: a
  runner **MUST NOT** refuse to start or to run because it could not tell,
  which is §5.7's posture for an entitlement it cannot re-check, and a client
  reads `unreachable` as *not known* rather than as *out of date*. It sits in
  `status` rather than `describe` for the reason `limits` does — the version
  a runner happens to be running, against a distributor it happens to be
  configured for, is a fact about the deployment. **No distributor path is
  added**: §5 fixes the two a runner must call to serve its agent at all, a
  version answer is neither, and a runner that never asks conforms fully — so
  how `latest` is obtained is the distributor's to publish, and §8 records
  Sigrix's, unauthenticated because it names no buyer (§4.4, §8).
- `output.media_type` is bounded by the grammar it always claimed. Both
  schemas carried a pattern that was wrong in each direction at once: it
  refused every experimental type, `x-custom/foo` among them, because the
  type half admitted no `-`, while accepting a subtype beginning `!`, which
  §4.2 of RFC 6838 forbids. Both halves are that RFC's `restricted-name`
  now. §4.1.4 also states what the pattern used to imply by accident — a
  runner emits the field in lower case, so two runners naming one format
  agree octet-for-octet, and a client **MUST NOT** reject a response over
  its case (§4.1.4).
- §4.6 places the entitlement refusals, which it previously left out of its
  sequence entirely. They are step 2 — behind the level check, ahead of the
  media type, the inputs and the environment — so a runner that has been told
  no answers that rather than a `400` naming something the caller could fix,
  which §5.7.4 already forbids it to imply. The general sentence is narrowed
  to the steps it was always about: *what the request says before what the
  runner holds* governs steps 3 to 5, and an entitlement is neither. Both
  orders conformed before, so a conformance checker could assert neither
  (§4.6, §5.7.4).
- `version.schema.json` fixes the shape of a version answer — `postern`, the
  `agent_id` echoed octet-for-octet, and a `version` string compared for
  equality only, with no ordering implied. It is the source of §4.4's
  `status.update.latest`, and the first schema here whose *path* this
  specification does not define: §5 fixes the two distributor paths a runner
  must call to serve its agent at all, a version answer is neither, and §8
  records where Sigrix serves it. Fixing the shape without fixing the path is
  the point — a second distributor offering the same answer answers it the
  same way, and a runner reads both with one parser. It joins
  `entitlement.schema.json` as a distributor payload the conformance checker
  does not bundle, since a runner never emits one (§4.4, §8).

**0.1** — First public draft. Four verbs, entitlement flow, Agent Plugins
v1.0.0 packaging. Nothing is stable yet; see
[VERSIONING.md](VERSIONING.md).
