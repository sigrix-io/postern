"""Locate and load the specification's JSON Schemas.

The checker validates payloads against `schemas/` rather than restating
their rules in Python. A restatement would be a second home for the
contract and the one nobody diffs — the specification's own validator
(`scripts/validate.py`) exists to stop SPEC.md and `schemas/` drifting from
each other, and a checker carrying its own third copy would sit outside
that guarantee entirely.

Two places they can come from, and which one was used is reported rather
than assumed:

- **A checkout.** Walking up from the working directory finds `schemas/`
  beside `SPEC.md`, so an edit to a schema is checked immediately, without
  reinstalling anything.
- **An installed wheel.** There is no repository around it, so the build
  bundles a copy at `_schemas/`.

A checkout is preferred deliberately. The alternative — always using the
bundled copy — would let someone edit a schema, run the checker, watch it
pass, and have tested the version they had installed last week.
"""

from __future__ import annotations

import functools
import json
import pathlib
from typing import Any

# Every schema the checker validates against, by the filename `schemas/`
# uses. `entitlement.schema.json` is deliberately absent: it is the
# distributor's answer to a runner (SPEC.md section 5.3), and a runner never
# emits one — a checker pointed at a runner has nothing to validate with it.
SCHEMA_FILENAMES = (
    "describe.schema.json",
    "error.schema.json",
    "run-request.schema.json",
    "run-response.schema.json",
    "status.schema.json",
    "stream-event.schema.json",
)

_BUNDLED = pathlib.Path(__file__).resolve().parent / "_schemas"


class SchemasNotFound(RuntimeError):
    """Neither a checkout nor a bundled copy carries the schemas."""


def _looks_like_the_spec_repo(candidate: pathlib.Path) -> bool:
    """True for a directory holding `SPEC.md` and a populated `schemas/`.

    Both halves are checked. A `schemas/` directory alone is a name common
    enough that any project could have one, and matching on it would let the
    checker validate a runner against some unrelated repository's schemas
    while reporting a source that looked entirely plausible.
    """
    if not (candidate / "SPEC.md").is_file():
        return False
    schemas = candidate / "schemas"
    return all((schemas / name).is_file() for name in SCHEMA_FILENAMES)


def _search_upward(start: pathlib.Path) -> pathlib.Path | None:
    for directory in (start, *start.parents):
        if _looks_like_the_spec_repo(directory):
            return directory / "schemas"
    return None


@functools.lru_cache(maxsize=1)
def schema_source() -> tuple[pathlib.Path, str]:
    """Return the directory the schemas load from, and a word for it.

    The word reaches the report. A run whose result depends on which copy
    was read should say which copy was read.
    """
    from_cwd = _search_upward(pathlib.Path.cwd().resolve())
    if from_cwd is not None:
        return from_cwd, "checkout"

    # An editable install lives inside the checkout even when the working
    # directory is elsewhere, so this finds the repository a `pip install -e`
    # points at without the caller having to stand in it.
    from_package = _search_upward(pathlib.Path(__file__).resolve().parent)
    if from_package is not None:
        return from_package, "checkout"

    if all((_BUNDLED / name).is_file() for name in SCHEMA_FILENAMES):
        return _BUNDLED, "bundled with this package"

    raise SchemasNotFound(
        "Could not find the Postern schemas. Run from a checkout of "
        "sigrix-io/postern, or install this package from a wheel built "
        "with the schemas bundled."
    )


@functools.lru_cache(maxsize=None)
def load(filename: str) -> dict[str, Any]:
    """Load one schema by its `schemas/` filename."""
    if filename not in SCHEMA_FILENAMES:
        raise KeyError(f"{filename} is not a schema this checker validates against")
    directory, _ = schema_source()
    return json.loads((directory / filename).read_text(encoding="utf-8"))
