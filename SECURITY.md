# Security Policy

Postern is a specification before it is code. A weakness in it is a weakness
in every implementation that follows it faithfully, so findings against the
document are in scope here — not only bugs in something that runs.

## Reporting a vulnerability

**Do not open a public issue.**

Email **security@sigrix.io** with enough detail to reproduce. You will get an
acknowledgement within 72 hours and an assessment as soon as we have one.
[CONTRIBUTING.md](CONTRIBUTING.md) publishes the queues everything else waits
in; security reports jump all of them.

## What is in scope

Weaknesses in the specification itself, which is the half most policies omit:

- **Entitlement that can be bypassed** — the check in
  [§5.3](SPEC.md#53-the-check), the revocation window in
  [§5.4](SPEC.md#54-revocation), or the interaction between them.
- **Anything that leaks catalogue contents** —
  [§5.5](SPEC.md#55-not-entitled-is-indistinguishable-from-not-found) requires
  that not-entitled be indistinguishable from not-found. A way to tell them
  apart is a finding, including by timing.
- **Token handling that is unsafe as written** —
  [§5.2](SPEC.md#52-tokens) and [§7](SPEC.md#7-security-considerations):
  transport, storage at rest, and the requirement that rotation invalidate a
  predecessor immediately rather than at the end of a cache window.
- **Credentials traversing the protocol** —
  [§4.1.3](SPEC.md#413-credentials) makes this nonconformant precisely
  because it is a security property. A path that carries a credential value
  anyway is a finding.
- **Anything that makes a conforming implementation less safe than a
  non-conforming one.** If following the specification is what creates the
  exposure, that is the most valuable report we can receive.

Defects in this repository count too: `scripts/`, the CI workflows, the
schemas.

## What is not in scope

- **Vulnerabilities in someone else's Postern implementation.** Report those
  to whoever wrote it. If the specification is what led them there, that is
  in scope — say so, and we will treat it as a specification finding.
- **Agent Plugins, MCP, or other adjacent specifications**
  ([§1.3](SPEC.md#13-relationship-to-adjacent-specifications)). Report those
  upstream.
- **Hardening Postern deliberately leaves to the runner.** A runner binding a
  non-loopback interface is explicitly outside the threat model this version
  addresses ([§7](SPEC.md#7-security-considerations)); that is a documented
  boundary, not an oversight.

## Supported versions

| Version | Status |
|---|---|
| 0.1 | Draft — supported |

Postern is pre-1.0, and [VERSIONING.md](VERSIONING.md) is blunt about what
that means: nothing is stable, and any `0.x` release may break any other.
There is no back-porting, because there is nothing to back-port to. A finding
that requires a normative change lands in the current draft with an [Appendix
A](SPEC.md#appendix-a--changes) entry recording it.

## What happens next

We will agree a disclosure timeline with you rather than impose one, and the
Appendix A entry will credit you unless you would rather it did not.

This is a small team, and [CONTRIBUTING.md](CONTRIBUTING.md) is candid about
what that means everywhere else. Security is the one queue where the 72-hour
acknowledgement is a commitment rather than an aspiration.
