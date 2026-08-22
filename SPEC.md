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
| `not_found` | 404 | R · D | No such agent — **or** the caller is not entitled to it, **or** the token does not resolve (§5.5). The one code that means different things on each side; see below. |
| `not_entitled` | 403 | R | The caller is known and is not entitled. Only for a local runner reporting its *own* state; distributors **MUST NOT** use it (§5.5). |
| `withdrawn` | 410 | D | The caller was entitled, and the agent has since been withdrawn (§5.6). |
| `missing_credential` | 424 | R | A credential named by `describe` is absent from the environment. |
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

A runner **MUST** serve exactly one agent. None of `describe`, `run`,
`stream` or `status` carries an agent identifier, so a client **MAY** treat
a runner's port as that agent's address. Only the distributor paths in §5
address an agent by identifier (§1.5), because a distributor answers for a
catalogue while a runner only ever answers for itself.

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
| `Access-Control-Allow-Headers` | `Content-Type`, plus `Idempotency-Key` where the runner honours it (§4.2) |
| `Vary` | `Origin` |

on any 2xx status; `204` is the usual choice.

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
    "streaming": true,
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

#### 4.1.1 `inputs`

An ordered array of input declarations. Each **MUST** carry `key`, `label`,
`type` and `required`.

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
`run`, and **MAY** require confirmation. This is the only safety-relevant
field in `describe` and the reason `tools` is not a flat list.

#### 4.1.3 `credentials`

Declares credentials by **environment variable name only**.

A `describe` response **MUST NOT** contain a credential value. A conforming
agent bundle **MUST NOT** contain a credential value. Runners load
credentials from the environment of the machine they run on.

This is the property that makes "your keys stay on your machine" checkable
rather than promised: there is nowhere in the protocol for a secret to
travel, and a bundle carrying one is nonconformant.

#### 4.1.4 `output`

Declares what the agent returns: a `type`, and an **OPTIONAL** `example`.
§4.2's `run` response carries the same `type` beside the `value` it actually
produced, and so does a stream's `done` payload (§4.3).

`type` is `text` in v0, and that is a decision rather than an accident of
the examples — the same decision §4.1.1 records for inputs, made for the
same reason. `output.value` therefore carries a string, everywhere it
appears. A second type, and the value shape it implies, can be added later:
additive for a runner, which need never emit it, and free to withdraw
nothing. What it costs a *client* is the subject of the rest of this
section.

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

**What a second type would owe.** Whoever adds one says what `value`
carries for it, and what §4.3's `delta` means in its presence: that
invariant is text-shaped — every `delta.text` concatenated in order equals
`output.value` — so a non-text output needs either a translation of it or an
explicit exemption. `describe.output.example` is a string today and needs
the same answer. None of that is settled here. What is settled is that a
client written against this section survives the addition, which is the
property that has to exist first.

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
before reading the body at all (§2.3).

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

`run_id` **MUST** be unique within the runner's lifetime and **SHOULD** be
stable enough to correlate with `stream` events and logs.

`run` is not idempotent. A runner **MAY** honour an `Idempotency-Key`
request header; behaviour when it does not is to execute again.

### 4.3 `POST /postern/v0/stream`

Takes the **same request body as `run`** and returns
`text/event-stream`.

Events are Server-Sent Events with a named `event:` and a JSON `data:`
payload. Five event types are defined:

| Event | Payload | Notes |
|---|---|---|
| `start` | `{"run_id": "…"}` | **MUST** be first. |
| `step` | `{"name": "…", "model_id": "…", "status": "started\|finished", "latency_ms": N}` | **OPTIONAL**, zero or more. |
| `delta` | `{"text": "…"}` | **OPTIONAL**, zero or more. Incremental output. **If any `delta` is emitted**, concatenating every `delta.text` in order **MUST** equal the final `output.value`; a runner that cannot produce incremental text emits none. |
| `done` | The full `run` response body (§4.2) | **MUST** be last on success. |
| `error` | The error body (§2.1) | **MUST** be last on failure. |

A stream **MUST** end with exactly one `done` or one `error`. A client
**MUST** ignore unrecognised event names rather than aborting, which is how
this list grows without a version bump.

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

`limits` is **OPTIONAL** and carries the bounds §4.5 puts on a run in
flight. Both members are **OPTIONAL** in turn: `max_run_seconds` is the
maximum duration the runner will let a run reach, **REQUIRED** where it
imposes one at all and absent where it does not, and `max_concurrent_runs`
is how many runs it will have in flight at once.

They live in `status` rather than in `describe` because they belong to the
deployment and not to the agent. Two runners serving the same agent may
answer differently, and the same runner may answer differently after its
operator reconfigures it — neither of which is a fact about what the agent
takes as input, which is what `describe` is for.

`max_concurrent_runs` is at least `1`. A runner that will run nothing says
so with its `level` (§3) and a `501`, which tells a client that retrying is
pointless; a `0` here would say the same thing in a second vocabulary, and
in one a client would reasonably read as a temporary condition.

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
thing it can do with it.

**An abort is not a rollback**, and a client **MUST NOT** read one as
undoing anything. Whatever the agent did before it stopped is done: the
money is spent, and every `write_tools` entry (§4.1.2) is a thing that may
already have happened. Postern can stop an agent; nothing here can reverse
one. That is also what makes a retry after a disconnect a genuinely
different request from the first attempt, and the case `run`'s
`Idempotency-Key` (§4.2) exists for — a client that disconnects, reconnects
and asks again without one has asked for the work twice, and **SHOULD**
expect to be charged for it twice.

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

**Postern defines no `401`.** No status in this specification means
"authenticate and try again", because saying that is itself an answer — it
confirms the token was once real. §7's requirement that a rotated token's
predecessor stop resolving is discharged here: it stops resolving by
answering `404`, on the next request, like a token that never existed.

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
exists to prevent. So a runner reporting `revoked` after a `404` uses its
own receipt time and its own re-check cadence, and **SHOULD** reuse the last
`stale_after_seconds` the distributor gave it. §4.4's rule against
re-stamping is not engaged, because it forbids discarding an anchor the
distributor supplied, and here there is none to discard.

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

- **Bearer tokens over TLS only.** A distributor **MUST** serve over HTTPS.
  A runner **MUST** refuse to send a token over plaintext HTTP.
- **Loopback binding.** A runner binding a non-loopback interface exposes
  `run` to its network with no authentication defined by this specification.
  Runners that do so **MUST** require authentication of their own; Postern does
  not specify it, because a runner reachable from off-machine is outside the
  threat model this version addresses.
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

---

## Appendix A · Changes

**Unreleased** — corrections made before first publication.

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

**0.1** — First public draft. Four verbs, entitlement flow, Agent Plugins
v1.0.0 packaging. Nothing is stable yet; see
[VERSIONING.md](VERSIONING.md).
