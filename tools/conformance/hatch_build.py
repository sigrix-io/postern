"""Put the specification's schemas inside the package at build time.

The checker validates against `schemas/` rather than restating their rules
in Python, so a wheel installed from an index — which has no repository
around it — has to carry a copy. There is still only one copy in the
repository: this hook is what gets it into the artifact, and
`postern_conformance/_schemas/` exists only inside a build.

Two builds have to work, and they find the schemas in different places:

- **From a checkout**, `schemas/` is two directories up, beside `SPEC.md`.
- **From an sdist**, it is not — the sdist's own `force-include` has
  already placed the copy at `src/postern_conformance/_schemas`, and
  nothing outside the extracted tree exists to copy from. Building a wheel
  from an sdist is the default path `python -m build` takes, so this is the
  ordinary case rather than an exotic one.

So the hook copies where it can and accepts an existing copy where it
cannot, and fails loudly when there is neither — a wheel published without
the schemas would install cleanly and then be unable to check anything.
"""

from __future__ import annotations

import pathlib
import shutil

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SCHEMA_FILENAMES = (
    "describe.schema.json",
    "error.schema.json",
    "run-request.schema.json",
    "run-response.schema.json",
    "status.schema.json",
    "stream-event.schema.json",
)


class SchemaBundleHook(BuildHookInterface):
    PLUGIN_NAME = "bundle-schemas"

    def initialize(self, version: str, build_data: dict) -> None:
        root = pathlib.Path(self.root)
        destination = root / "src" / "postern_conformance" / "_schemas"

        if self._complete(destination):
            return

        source = root.parent.parent / "schemas"
        if not self._complete(source):
            raise RuntimeError(
                "Cannot find the Postern schemas to bundle. Expected them at "
                f"{source} (a checkout) or already at {destination} (an "
                "sdist). A wheel built without them installs cleanly and then "
                "cannot validate anything."
            )

        destination.mkdir(parents=True, exist_ok=True)
        for name in SCHEMA_FILENAMES:
            shutil.copy2(source / name, destination / name)

    @staticmethod
    def _complete(directory: pathlib.Path) -> bool:
        return all((directory / name).is_file() for name in SCHEMA_FILENAMES)
