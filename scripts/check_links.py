#!/usr/bin/env python3
"""Check that the URLs this specification publishes still resolve.

Two kinds of URL rot silently, because nothing in the repository has to
change for either to break:

1. Documents cited but not controlled — Agent Plugins, MCP, RFCs. A reader
   at 2am follows one and lands on a 404, and the specification looks
   abandoned whether or not it is.
2. The schema `$id`s in schemas/. A JSON Schema `$id` is an identifier and
   is not required to be dereferenceable, but publishing an `https://` URI
   that does not resolve invites the assumption that it should.

    python scripts/check_links.py

This is deliberately *not* part of the pull request gate. Someone else's
outage is not a reason to block a contributor's typo fix, so CI runs it on a
schedule and a failure is a maintainer's triage task rather than a red mark
on an innocent change. It uses the standard library only, so the scheduled
job has no supply chain of its own.

Exit status is 0 when every URL resolves, 1 otherwise.
"""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Terminators are whatever Markdown link syntax, JSON quoting and ordinary
# prose put after a URL. Trailing sentence punctuation is stripped
# separately, because a full stop is legal in a URL and usually is not one.
URL = re.compile(r"""https?://[^\s"'<>()\[\]`]+""")
TRAILING = ".,;:!?"

# RFC 2606 and RFC 6761 reserve these for documentation and testing. A URL
# under one of them is an illustration that is not supposed to resolve —
# SPEC.md's worked example uses `example.com` for precisely that reason, and
# checking it would report a failure that is actually correct behaviour.
RESERVED_DOMAINS = ("example.com", "example.net", "example.org")
RESERVED_TLDS = (".example", ".invalid", ".localhost", ".test")

# Some hosts answer a bare urllib request with 403 and a browser with 200.
# Identifying as a browser-shaped client is not a trick here: the question
# being asked is whether a human following this link arrives somewhere, so
# the answer should be measured the way a human would get it.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; postern-link-check/1.0; "
        "+https://github.com/sigrix-io/postern)"
    ),
    "Accept": "*/*",
}
TIMEOUT = 20


def _sources():
    """Yield (path relative to the repository root, text) for each source.

    examples/ is left out on purpose. Its URLs are illustrative payloads —
    a listing URL for an agent that does not exist — and demanding that they
    resolve would either fail forever or push the examples towards real
    endpoints, which is worse.
    """
    paths = sorted(ROOT.glob("*.md")) + sorted(ROOT.glob("schemas/*.json"))
    for path in paths:
        yield path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")


def _collect() -> dict[str, list[str]]:
    """Map every URL in those sources to the files citing it."""
    found: dict[str, list[str]] = {}
    for where, text in _sources():
        for match in URL.finditer(text):
            url = match.group(0).rstrip(TRAILING)
            citations = found.setdefault(url, [])
            if where not in citations:
                citations.append(where)
    return dict(sorted(found.items()))


def _is_reserved(url: str) -> bool:
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host.endswith(RESERVED_TLDS) or any(
        host == domain or host.endswith("." + domain) for domain in RESERVED_DOMAINS
    )


def _reach(url: str, method: str) -> tuple[int | None, str]:
    """Return (HTTP status, detail), or (None, reason) if nothing answered."""
    request = urllib.request.Request(url, method=method, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, ""
    except urllib.error.HTTPError as error:
        return error.code, str(error.reason or "")
    except Exception as error:  # DNS, TLS, timeout, malformed URL
        return None, f"{type(error).__name__}: {error}"


def _note(citations: list[str]) -> str:
    """Explain a failure whose meaning depends on where the URL came from.

    A URL cited in prose is a promise to a reader and a 404 is a defect. A
    URL that appears only in schemas/ is a schema `$id`, where the same 404
    means something narrower and currently undecided — so say which one this
    is, rather than leaving a maintainer to work it out from a red job.
    """
    if all(where.startswith("schemas/") for where in citations):
        return (
            "this is a schema $id — an identifier, which JSON Schema does not "
            "require to be dereferenceable. Whether Postern's must resolve is "
            "an open decision (#25); if the answer is no, drop schemas/ from "
            "_sources()."
        )
    return ""


def _check(url: str) -> str | None:
    """Return None when the URL resolves, or the reason it did not."""
    # HEAD is cheap and enough for most hosts. A few reject it outright or
    # mishandle it, so anything that looks like a refusal of the method
    # rather than of the URL is retried as a GET before it is believed.
    status, detail = _reach(url, "HEAD")
    if status is None or status in (403, 405, 501) or status >= 500:
        status, detail = _reach(url, "GET")

    if status is None:
        return detail
    if 200 <= status < 400:
        return None
    return f"HTTP {status}" + (f" {detail}" if detail else "")


def main() -> int:
    failed = False

    for url, citations in _collect().items():
        where = ", ".join(citations)
        if _is_reserved(url):
            print(f"skip  {url} — reserved for documentation ({where})")
            continue

        reason = _check(url)
        if reason:
            failed = True
            print(f"FAIL  {url}")
            print(f"        {reason}")
            print(f"        cited in {where}")
            note = _note(citations)
            if note:
                print(f"        {note}")
        else:
            print(f"ok    {url}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
