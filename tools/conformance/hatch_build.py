"""Put the specification's schemas inside the package at build time.

The checker validates against `schemas/` rather than restating their rules
in Python, so a wheel installed from an index — which has no repository
around it — has to carry a copy. There is still only one copy in the
repository: this hook is what gets it into the artifact, and
`postern_conformance/_schemas/` exists only inside a build.

Two builds have to work, and they find the schemas in different places:

- **From a checkout**, `schemas/` is two directories up, beside `SPEC.md`.
  The hook points the builder straight at it, per file, so the wheel is
  filled from the repository's own copy on every build.
- **From an sdist**, that directory is not there — the sdist's own
  `force-include` has already placed a copy at
  `src/postern_conformance/_schemas`, inside the package the wheel builds
  from, and nothing outside the extracted tree exists to copy from.
  Building a wheel from an sdist is the default path `python -m build`
  takes, so this is the ordinary case rather than an exotic one.

**The checkout is asked about first, and nothing is ever written into the
tree.** Both halves are the same rule. This hook used to copy the schemas
into `src/postern_conformance/_schemas` and return early whenever that
directory was already populated — so the second wheel built in a checkout
carried the *first* build's schemas, indefinitely, and a release cut that
way ships a checker validating against a specification nobody is reading.
The default `python -m build` hid it, because the sdist's force-include
re-copies every time; `python -m build --wheel`, `pip wheel .` and
`hatch build -t wheel` all build the wheel in place and went stale. A
`force_include` mapping leaves no artifact behind to go stale, which is
why the fix is not merely reordering the two checks.
"""

from __future__ import annotations

import pathlib

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SCHEMA_FILENAMES = (
    "describe.schema.json",
    "error.schema.json",
    "run-request.schema.json",
    "run-response.schema.json",
    "status.schema.json",
    "stream-event.schema.json",
)

PACKAGE_SCHEMA_DIR = "postern_conformance/_schemas"


class SchemaBundleHook(BuildHookInterface):
    PLUGIN_NAME = "bundle-schemas"

    def initialize(self, version: str, build_data: dict) -> None:
        root = pathlib.Path(self.root)
        source = root.parent.parent / "schemas"

        if self._complete(source):
            # A checkout. Point the builder at the repository's own files
            # rather than copying them anywhere: an included path is read
            # at the moment the wheel is written, so it cannot be stale,
            # and it overrides a copy an older build of this hook left in
            # the tree.
            force_include = build_data.setdefault("force_include", {})
            for name in SCHEMA_FILENAMES:
                force_include[str(source / name)] = f"{PACKAGE_SCHEMA_DIR}/{name}"
            return

        destination = root / "src" / "postern_conformance" / "_schemas"
        if self._complete(destination):
            # An sdist. The copy is already inside the package being built.
            return

        raise RuntimeError(
            "Cannot find the Postern schemas to bundle. Expected them at "
            f"{source} (a checkout) or already at {destination} (an "
            "sdist). A wheel built without them installs cleanly and then "
            "cannot validate anything."
        )

    @staticmethod
    def _complete(directory: pathlib.Path) -> bool:
        return all((directory / name).is_file() for name in SCHEMA_FILENAMES)
