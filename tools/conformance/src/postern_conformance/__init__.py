"""Conformance checker for the Postern protocol.

Points at a running runner and reports which of SPEC.md section 3's three
levels it actually meets, and which of the specification's MUST rules it
breaks getting there.

This is a test suite, not a client library. It speaks to a runner over the
wire, so it checks an implementation in any language equally — which is
also why it is packaged as `postern-conformance` and not as `postern`:
CONTRIBUTING.md puts a language SDK out of scope, and the name a Python
client would want is left free for whoever writes one under their own.
"""

from __future__ import annotations

__all__ = ["POSTERN_VERSION", "__version__"]

# The version of this package, and the only place it is written.
# `pyproject.toml` reads it from here via hatchling's version source, so
# the number the CLI reports and the number people install by cannot
# disagree.
__version__ = "0.1.1"

# The version of the specification it checks against. Deliberately separate:
# the checker will be released more often than the protocol, and a reader
# comparing the two should not have to work out which number means what.
POSTERN_VERSION = "0.1"
