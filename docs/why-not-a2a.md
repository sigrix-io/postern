# Why not A2A?

> [!NOTE]
> **Non-normative.** Nothing on this page adds to the protocol, constrains an
> implementation, or is safe to build against. Where a claim here and
> [SPEC.md](../SPEC.md) disagree, the specification is right.
>
> It is also a *positioning* argument, and those date faster than
> specifications do. Every statement about another project is as of
> **September 2026**, read from that project's own published text. Where one is
> wrong, or has moved since, please
> [open an issue](https://github.com/sigrix-io/postern/issues) — a comparison
> nobody corrects is a comparison nobody read.
>
> Other projects are **named rather than linked**, deliberately. Their
> documentation changes host more often than this page will be edited, and
> `scripts/check_links.py` runs weekly against every URL written here — a
> comparison page is a poor reason to turn that job into a triage queue for
> other people's site moves. Each one is findable by the name given.

---

## The question this page exists for

> *Why would I expose this instead of an A2A Agent Card and `message/send`?*

[§1.3](../SPEC.md#13-relationship-to-adjacent-specifications) answers it in one
word — *orthogonal* — and that word is true of the question A2A asks and false
of the decision an adopter makes. An adopter is not choosing between two
philosophies. They have one agent, one afternoon, and a list of protocols that
each claim to run it.

So here is the long answer, including the parts that do not flatter this
specification.

---

## The short version

**If all you need is to execute an agent, use A2A.** It is governed by the
Linux Foundation, it has more verbs, richer streaming, a task lifecycle with
identifiers, cancellation, push notifications, signed Agent Cards and a
published extension mechanism. Postern deliberately has none of that, and
[VERSIONING.md](../VERSIONING.md) explains the four-verb ceiling as a
maintenance decision rather than a design ideal.

**Postern is not the execution layer you pick instead.** It is the
*entitlement and local-execution* layer you bolt onto whatever surface you
already expose. The honest one-line positioning is:

> Postern answers "is the person running this agent allowed to, and what
> happens when they get a refund" — a question no adjacent specification
> answers at all.

Everything below is the evidence for that sentence, and the boundaries of it.

---

## What the four verbs are

Postern's execution surface ([§4](../SPEC.md#4-the-execution-surface)) is four
verbs and nothing else, arranged in three cumulative conformance levels
([§3](../SPEC.md#3-conformance)):

| Verb | Level | Answers |
|---|---|---|
| [`describe`](../SPEC.md#41-get-posternv0describe) | 1 | What does this agent take, return and require? |
| [`status`](../SPEC.md#44-get-posternv0status) | 1 | Is it alive, at what level, and is the entitlement in force? |
| [`run`](../SPEC.md#42-post-posternv0run) | 2 | Execute once, answer when finished. |
| [`stream`](../SPEC.md#43-post-posternv0stream) | 3 | Execute once, narrate as it goes. |

That is the whole client-facing protocol. The comparison below asks, of each
adjacent specification, whether it covers those four — and then the question
none of them cover.

---

## Coverage

**✓** covers it · **~** covers part of it, or covers a near neighbour ·
**—** does not address it

| Specification | `describe` | `status` | `run` | `stream` | Entitlement model |
|---|:--:|:--:|:--:|:--:|:--:|
| **A2A** | ✓ | ~ | ✓ | ✓ | — |
| **MCP** | ~ | — | ~ | ~ | — |
| **ACP** (IBM/BeeAI) | ✓ | ~ | ✓ | ✓ | — |
| **AG-UI** | — | — | ~ | ✓ | — |
| **Agent Protocol** | ~ | ✓ | ✓ | ✓ | — |
| **LangGraph Platform** | ~ | ✓ | ✓ | ✓ | — |
| **[Agent Plugins v1.0.0](https://agent-plugins.org)** | — | — | — | — | — |
| **ANP** | ~ | — | — | — | — |
| **AP2** | — | — | — | — | — |
| **OpenAI-compatible chat APIs** | — | — | ~ | ✓ | — |

**The last column is the point of the table.** It is empty for every row, and
that is not an oversight on their part — each of them is answering a different
question, and most say so. Agent Plugins is the one that states it outright:
its own text says licensing is metadata only, with no portable verification
mechanism defined. [§5](../SPEC.md#5-entitlement) is the mechanism that
sentence leaves open.

### Reading the rows

- **A2A** — the closest neighbour and the strongest execution protocol here.
  An Agent Card covers `describe` and then some; `message/send` and
  `message/stream` cover `run` and `stream` with more structure than Postern
  has. `status` is the partial one: A2A reports *task* state, where
  [§4.4](../SPEC.md#44-get-posternv0status) reports the *runner's* readiness,
  conformance level, credential satisfaction and entitlement state in one
  document a client can poll before it commits to anything.
- **MCP** — a different subject wearing similar words. It gives a model tools
  and context; it does not expose an agent as a callable unit. A Postern agent
  may use MCP internally, and [§4.1.2](../SPEC.md#412-capabilitieswrite_tools)
  exists to report the tools that write.
- **ACP** — IBM/BeeAI's protocol merged into A2A in August 2025 and is no
  longer developed separately. The row is here because the name still
  circulates; read it as A2A.
- **AG-UI** — agent-to-UI event streaming, and better at that than Postern is.
  Its event vocabulary runs to sixteen types against Postern's five
  ([§4.3](../SPEC.md#43-post-posternv0stream)), which is the right comparison
  to make if you are building a UI and the wrong one if you are selling an
  agent.
- **Agent Protocol** and **LangGraph Platform** — runs, threads and stores.
  Both cover execution well. LangGraph Platform is a vendor platform rather
  than a vendor-neutral specification, which may or may not matter to you.
- **ANP**, **AP2**, **chat APIs** — routing and discovery, agent-initiated
  payment, and a single model call respectively. None is in this contest;
  they are listed so the table is not quietly selective. AP2 in particular is
  the *mirror image* of §5: it is about an agent making a purchase, where
  Postern is about a human being licensed to run one.

---

## What you would actually lose

Three properties are Postern's alone in the list above. If you pick any other
row, these are what you are giving up — and for many adopters, giving them up
is the correct call.

### 1. A licensing model that survives a refund ([§5](../SPEC.md#5-entitlement))

Not "a `license` field". A protocol:

- Tokens are **opaque bearer secrets** with a minimum entropy, never parseable
  documents, and a distributor **MUST NOT** store one in recoverable form
  ([§5.2](../SPEC.md#52-tokens)).
- A distributor **MUST** revoke when a purchase is reversed and **MUST** be
  able to restore it ([§5.4](../SPEC.md#54-revocation)).
- Revocation is **not** required to be instantaneous — a specification
  demanding that would be widely and quietly violated. What is required is
  that the window is *declared*, and that the declared number is not shorter
  than the longest staleness the distributor's caches can actually produce.
- **Not-entitled is indistinguishable from not-found**
  ([§5.5](../SPEC.md#55-not-entitled-is-indistinguishable-from-not-found)): a
  distributor answers `404`, never `403`, so the entitlement endpoint cannot
  enumerate a private catalogue. This costs a legitimate caller a worse error
  message, deliberately.
- An agent that is free, self-authored or local configures no distributor,
  reports `not_required`, and skips all of it
  ([§5.1](../SPEC.md#51-the-distributor-is-optional)).

The declared-window rule is the load-bearing one. Every other specification
that touches licensing either states a fact about a file or says nothing;
none of them make a claim a buyer could hold anyone to.

### 2. A threat model for the loopback browser ([§2.3](../SPEC.md#23-browser-clients))

Postern runs on the buyer's machine, which means a web page in the buyer's
browser can reach it. §2.3 is the only text in this comparison that works
through what that implies: that a cross-origin `GET` is stopped *after* the
runner has already executed it and only the reading of the answer is refused,
while a cross-origin `POST` is stopped *before* it is sent at all. That
asymmetry is survivable only because Postern's two unpreflighted verbs are the
side-effect-free ones, and §2.3 requires the media-type check *before the body
is read* so that the ordering holds.

A protocol designed for server-to-server calls has no reason to have written
any of this down, and mostly has not.

### 3. Credentials as names, enforced at the parse boundary ([§4.1.3](../SPEC.md#413-credentials))

An agent declares the environment variable **names** it needs. A `describe`
response **MUST NOT** carry a credential value, and a conforming bundle
**MUST NOT** either — a bundle-level prohibition, not just a wire rule.

The enforcement is the part worth copying: `describe.credentials` is a
**closed** object in the schema, the only closed object outside the error
envelope's root. An open object *is* somewhere in the protocol for a secret to
travel — `value` beside `env` would validate, and so would every other spelling
of the leak. Closing it removes the likely mistake (a runner serialising its
own credential record and shipping the value beside the name) at the parse
boundary rather than by review.

This is what makes "your keys stay on your machine" checkable rather than
promised.

---

## Where A2A is straightforwardly better

Stated plainly, because a comparison that only lists the author's wins is
marketing:

- **Governance.** Linux Foundation, many corporate contributors. Postern has
  one maintainer and says so in the README's *Status*.
- **A task lifecycle.** A2A tasks have identifiers a client can come back to.
  Postern has **no verb that takes a `run_id`** — so no cancel, no callback,
  no resumption. [§4.5](../SPEC.md#45-the-life-of-a-run) makes a disconnected
  client a cancelled run, which is a coherent rule and a much smaller promise.
- **Push notifications**, for long-running work where holding a connection is
  not viable. Postern has nothing equivalent.
- **Richer streaming**, and signed Agent Cards for provenance.
- **A published extension mechanism**, which is the subject of the next
  section.
- **Adoption.** A2A is deployed; Postern's own README does not claim to be.

If none of the three properties in the previous section matters to you, the
rest of this page is not an argument for Postern. Use A2A.

---

## Open question: should §5 be restated as an A2A extension?

**This is unresolved, and it is the maintainer's call. What follows is the
analysis, not a decision.**

The question is whether an A2A-native agent should be sellable without
standing up a second surface — today, an adopter who wants A2A's execution
model *and* Postern's entitlement model implements both protocols.

The useful observation is that **§5 splits cleanly in two**, and only one half
would need to move:

| Half | What it is | Does A2A care? |
|---|---|---|
| **Upstream** — [§5.2](../SPEC.md#52-tokens), [§5.3](../SPEC.md#53-the-check), [§5.4](../SPEC.md#54-revocation), [§5.6](../SPEC.md#56-bundle-retrieval), [§5.7](../SPEC.md#57-when-the-distributor-cannot-be-reached) | The runner↔distributor conversation: token, check, staleness, revocation, bundle retrieval | **No.** A2A is client↔agent; this traffic is on an axis A2A does not describe and would not need to. |
| **Client-visible** — the `entitlement` block in [§4.4](../SPEC.md#44-get-posternv0status), the `not_entitled` / `withdrawn` codes in [§2.1](../SPEC.md#21-errors), and step 2 of [§4.6](../SPEC.md#46-the-order-of-refusals) | How a client learns the agent is not runnable, and in what order that refusal beats the others | **Yes.** This is the only part that needs a place in someone else's surface. |

So an A2A extension would carry the second row — an Agent Card capability
declaring entitlement-awareness, a state field, and the refusal semantics —
while the first row stays exactly as written and is reused unchanged. That is
a much smaller document than "§5 as an A2A extension" sounds like, which is
the main finding here.

**Arguments for:**

- It is where the adopters are. An extension meets A2A's users on their own
  surface instead of asking them to add a second port.
- The upstream half is the part with the hard thinking in it, and it survives
  the move intact.
- Refusal-ordering is the kind of thing extension mechanisms exist for: it
  changes when a call fails, not what the protocol's verbs are.

**Arguments against:**

- Extension semantics are advisory in a way [§4.6](../SPEC.md#46-the-order-of-refusals)
  is not. Postern can require an ordering because it owns the surface; an
  extension can only ask, and a client that ignores it sees a run fail with a
  less specific error.
- It commits this project to tracking another specification's versioning on
  top of its own, with one maintainer.
- §5 is currently implementable against a runner that speaks no other
  protocol at all. An extension would not replace that, so it is a second
  artefact to keep consistent with the first, and two documents stating one
  rule drift silently — the failure is that nothing goes red when they
  disagree.
- It should probably wait for a second implementer. Writing an extension for
  a mechanism with one deployment is designing against an audience of one.

**What would settle it:** one adopter who wants A2A execution and Postern
entitlement together. Until someone asks, this is speculative work with a real
maintenance bill. If that is you,
[say so on the issue tracker](https://github.com/sigrix-io/postern/issues).

---

## Where to go next

| | |
|---|---|
| The specification | [SPEC.md](../SPEC.md) — the only thing that governs |
| The entitlement flow in pictures | [Postern in pictures](README.md) — the staleness window and the `404` indistinguishability, drawn |
| Why four verbs and not more | [VERSIONING.md](../VERSIONING.md) |
| A runner you can read | [`examples/minimal_runner.py`](../examples/minimal_runner.py) |
