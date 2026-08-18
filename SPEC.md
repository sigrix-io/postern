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

---

## 2. Transport

A runner **MUST** serve HTTP/1.1 over a TCP port. It **SHOULD** bind
loopback (`127.0.0.1`) by default.

All paths are prefixed with the protocol version: `/postern/v0/…`. The prefix
changes only on a breaking revision.

Request and response bodies are `application/json; charset=utf-8`, except
`stream`, which is `text/event-stream` (§4.3).

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
| `bad_request` | 400 | R · D | Malformed request — a bad body, or an input that failed `describe`'s validation. |
| `not_found` | 404 | R · D | No such agent — **or** the caller is not entitled to it (§5.5). The one code that means different things on each side; see below. |
| `not_entitled` | 403 | R | The caller is known and is not entitled. Only for a local runner reporting its *own* state; distributors **MUST NOT** use it (§5.5). |
| `withdrawn` | 410 | D | The caller was entitled, and the agent has since been withdrawn (§5.6). |
| `missing_credential` | 424 | R | A credential named by `describe` is absent from the environment. |
| `agent_error` | 500 | R | The agent ran and failed. |
| `not_implemented` | 501 | R | The verb is defined by this specification but sits above the runner's conformance level (§3). Retrying will not help. |
| `unavailable` | 503 | R · D | The runner or distributor is not ready. Retrying may help. |

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
take an `{agent_id}`, because a distributor answers for a catalogue while a
runner only ever answers for itself.

Serving several agents means running several runners. A client that wants a
catalogue holds a list of ports; a client that wants two agents to work
together calls both. Composition is the client's — the addressing form of
the orchestration non-goal in §1.2.

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

### 4.2 `POST /postern/v0/run`

Executes the agent and returns the final result. A Level 1 runner does not
implement it, and **MUST** answer `501` with code `not_implemented` (§3).

Request:

```json
{"inputs": {"segment": "B2B SaaS observability", "depth": "standard"}}
```

`inputs` is a map keyed by `describe`'s input keys. A runner **MUST** reject
a request omitting a `required` input, or failing a declared `validation`,
with `bad_request` — and **SHOULD** name the offending key in `message`.

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
  "credentials": {"satisfied": true, "missing": []}
}
```

`state` is `ready`, `running`, or `degraded`. `entitlement.state` is
`active`, `revoked`, `unknown`, or `not_required` (§5.1).

`entitlement.stale_after_seconds` is **REQUIRED** whenever
`entitlement.state` is `active`. It declares how long the runner may
continue to rely on the cached answer before re-checking, and is the honest
upper bound on how long a revoked entitlement can keep working (§5.4).

`entitlement.checked_at` is **REQUIRED** whenever `entitlement.state` is
`active` or `revoked`. Both are answers a distributor actually gave, and
neither is terminal — a revoked entitlement may later be restored (§5.4), so
a runner holding `revoked` with no timestamp has no basis for ever asking
again. It is omitted for `not_required`, where no check took place.

A runner **MUST** report the `checked_at` it received from the distributor
(§5.3) unchanged, and **MUST NOT** re-stamp it with its own clock.
Re-stamping discards the anchor and silently restores the stacking that
§5.3 exists to prevent, while every field still validates.

`status` **MUST** answer at Level 1, and **MUST NOT** require credentials.

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
GET  {distributor}/postern/v0/entitlements/{agent_id}
Authorization: Bearer <token>
```

```json
{
  "state": "active",
  "agent_id": "acme/market-research-crew",
  "checked_at": "2026-08-15T09:14:02Z",
  "stale_after_seconds": 60
}
```

`state` is `active` or `revoked`. A distributor **MUST** resolve the token
to a buyer and answer only for that buyer; there **MUST NOT** be a
parameter, header or path segment by which a caller can widen the answer
beyond the buyer the token identifies.

A distributor **MAY** serve this from a cache, and **MUST** declare the
cache bound as `stale_after_seconds`.

`checked_at` is **REQUIRED**, an RFC 3339 timestamp, and means *the moment
the distributor last consulted the authority* — not the moment it answered.
A distributor serving from a cache reports the age of the underlying read,
not the age of the response.

That definition is what makes the declared window honest. Without it the
distributor's cache age is invisible to the caller, a runner can only stamp
its own clock on receipt, and the two caches run back to back — so the real
worst case is their sum while `stale_after_seconds` claims to be the whole
of it.

### 5.4 Revocation

A distributor **MUST** revoke entitlement when the purchase behind it is
reversed — refund, chargeback, or dispute — and **MUST** be able to restore
it if the reversal is itself reversed.

Revocation is **not** required to be instantaneous, and a specification that
demanded it would be widely and quietly violated. What is required is that
the window is *declared*: a distributor **MUST NOT** report a
`stale_after_seconds` shorter than the longest staleness any of its caches
can actually produce. A runner **MUST** re-check on the first request after
`checked_at + stale_after_seconds`.

Because `checked_at` is the distributor's own read time rather than the
runner's receipt time (§5.3), that deadline is anchored upstream: the
distributor's cache and the runner's cache expire together instead of in
sequence, and `stale_after_seconds` is the whole window rather than half of
it.

A runner **MUST NOT** cache an entitlement answer for longer than the
distributor declared, and **MUST NOT** persist an `active` answer across
restarts.

### 5.5 Not-entitled is indistinguishable from not-found

A distributor answering an entitlement check or a bundle request for an
agent the caller is not entitled to **MUST** answer `404` with code
`not_found`, and **MUST NOT** answer `403`.

A `403` confirms the agent exists. Over an unauthenticated-but-guessable
identifier space that turns the entitlement endpoint into an enumeration
oracle for the distributor's private catalogue. The cost of this rule is a
worse error message for a legitimate caller who mistyped an id; that is the
right trade.

The local runner reporting its *own* state to its *own* client is the one
place `not_entitled` (403) is correct — there is nothing to enumerate.

### 5.6 Bundle retrieval

```
GET  {distributor}/postern/v0/bundles/{agent_id}
Authorization: Bearer <token>
```

- `200` — the bundle, `application/zip`, conforming to §6. The response
  **SHOULD** carry a `Digest: sha-256=<base64>` header.
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
  *token* may not.

---

## 8. Sigrix profile

*This section is normative for [Sigrix](https://sigrix.io) as a distributor
and informative for everyone else. Postern is usable with no reference to it.*

- Namespace: `org.sigrix`, carrying `agent_id` and `listing_url`.
- Tokens are 32 random bytes, URL-safe base64, stored as SHA-256. One active
  token per buyer; rotation revokes every predecessor.
- `stale_after_seconds` is 60.
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

**0.1** — First public draft. Four verbs, entitlement flow, Agent Plugins
v1.0.0 packaging. Nothing is stable yet; see
[VERSIONING.md](VERSIONING.md).
