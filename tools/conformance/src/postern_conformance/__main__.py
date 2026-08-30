"""`python -m postern_conformance`, equivalent to the installed script."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
