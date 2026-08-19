#!/usr/bin/env python3
"""Check that the URLs this specification publishes still resolve.

Two kinds of URL rot silently, because nothing in the repository has to
change for either to break:

1. Documents cited but not controlled — Agent Plugins, MCP, RFCs. A reader
   at 2am follows one and lands on a 404, and the specification looks
   abandoned whether or not it is.
2. The schema `$id`s in schemas/. JSON Schema does not require an `$id` to
   be dereferenceable, but Postern's are meant to resolve (VERSIONING.md),
   so a 404 on one of those is a hosting task rather than a citation to fix.

    python scripts/check_links.py

This is deliberately *not* part of the pull request gate. Someone else's
outage is not a reason to block a contributor's typo fix, so CI runs it on a
schedule and a failure is a maintainer's triage task rather than a red mark
on an innocent change. It uses the standard library only, so the scheduled
job has no supply chain of its own.

Exit status is 0 when every URL resolves, 1 otherwise. A URL whose host
answers but refuses this client — a 401 or 403, which is what bot protection
looks like from a script — is reported as `warn` and does not fail the run:
that answers "who is asking", not "does this still exist".
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

# A URL written with a placeholder in it names a shape rather than a
# document, and asking whether it resolves reports a defect that is really a
# sentence. Two shapes arrive here, because the terminator set above ends a
# match at `<` but not at an ellipsis:
#
#     https://sigrix.io/schemas/postern/0.1/…            the mark is inside the URL
#     https://sigrix.io/schemas/postern/0.1/<name>.json  the mark ended the match
#
# The second is the one worth the code. It leaves behind a URL that looks
# real — a clean directory path nobody wrote and nothing serves — and it
# fails forever, in a weekly job whose whole value is that a failure means
# something.
ELISIONS = ("…", "...", "{")

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


def _collect() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Map every URL in those sources to the files citing it.

    Returns (links, illustrations). They are separated here rather than
    filtered away, so that a URL this script decides not to check still says
    so on the way past: a silent drop is how a real citation stops being
    checked without anyone noticing.
    """
    found: dict[str, list[str]] = {}
    illustrations: dict[str, list[str]] = {}
    for where, text in _sources():
        for match in URL.finditer(text):
            url = match.group(0).rstrip(TRAILING)
            follower = text[match.end() : match.end() + 1]
            bucket = illustrations if _is_illustrative(url, follower) else found
            citations = bucket.setdefault(url, [])
            if where not in citations:
                citations.append(where)
    return dict(sorted(found.items())), dict(sorted(illustrations.items()))


def _is_illustrative(url: str, follower: str) -> bool:
    """True when a URL is an illustration: the mark is in it, or ended it."""
    return any(mark in url for mark in ELISIONS) or follower in "<{"


# A rule with no failing case is a rule that can be deleted without anything
# going red, and this one is invisible when it works: the URLs it acts on are
# the ones that never appear in the output. Each case below is a string this
# script has actually mis-read, or one it must not start mis-reading — the
# markdown link, the autolink and the JSON member are the three ways a real
# URL ends in this repository.
CLASSIFIER_CASES = [
    ("https://sigrix.io/schemas/postern/0.1/…", " ", True),
    ("https://sigrix.io/schemas/postern/0.1/", "<", True),
    ("https://example.org/{owner}", "\n", True),
    ("https://www.rfc-editor.org/rfc/rfc9530", ")", False),
    ("https://sigrix.io", ">", False),
    ("https://sigrix.io/schemas/postern/0.1/error.schema.json", '"', False),
]


def _classifier_holds() -> bool:
    """Check the illustration rule before any network call. True on failure."""
    wrong = [
        (url, follower)
        for url, follower, illustrative in CLASSIFIER_CASES
        if _is_illustrative(url, follower) != illustrative
    ]
    for url, follower in wrong:
        print(f"FAIL  the illustration rule mis-reads {url!r} before {follower!r}")
    return bool(wrong)


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
    is a hosting task on a known base — so say which one this is, rather than
    leaving a maintainer to work it out from a red job.
    """
    if all(where.startswith("schemas/") for where in citations):
        return (
            "this is a schema $id, and Postern's are meant to resolve "
            "(VERSIONING.md, 'Schema identifiers'). Serve the file at that "
            "base. Until the files are served there, this job is red here "
            "on purpose, and serving them gates publication."
        )
    return ""


def _check(url: str) -> tuple[str, str]:
    """Classify a URL as "ok", "warn" or "fail", with a reason for the last two.

    The question this script asks is whether a URL still exists, and only
    some failures answer it. A 404 says the path is gone; a refused
    connection says the host is. A 401 or 403 says neither — the server
    resolved the path and declined to serve *this* client, which is what bot
    protection looks like from a script and what a human following the link
    never sees. Failing on that produces a job that is red every week for a
    working link, and a job that cries wolf gets ignored when it is right.
    """
    # HEAD is cheap and enough for most hosts. A few reject it outright or
    # mishandle it, so anything that looks like a refusal of the method
    # rather than of the URL is retried as a GET before it is believed.
    status, detail = _reach(url, "HEAD")
    if status is None or status in (401, 403, 405, 501) or status >= 500:
        status, detail = _reach(url, "GET")

    if status is None:
        return "fail", detail
    if 200 <= status < 400:
        return "ok", ""

    described = f"HTTP {status}" + (f" {detail}" if detail else "")
    if status in (401, 403):
        return "warn", (
            f"{described} — the host answered and refused this client rather "
            f"than the URL, which is usually bot protection. Not read as rot."
        )
    return "fail", described


def main() -> int:
    failed = _classifier_holds()
    links, illustrations = _collect()

    for url, citations in illustrations.items():
        where = ", ".join(citations)
        print(f"skip  {url} — written with a placeholder, so it names a shape "
              f"rather than a document ({where})")

    for url, citations in links.items():
        where = ", ".join(citations)
        if _is_reserved(url):
            print(f"skip  {url} — reserved for documentation ({where})")
            continue

        state, reason = _check(url)
        if state == "ok":
            print(f"ok    {url}")
            continue

        print(f"{'FAIL' if state == 'fail' else 'warn'}  {url}")
        print(f"        {reason}")
        print(f"        cited in {where}")
        if state == "fail":
            failed = True
            note = _note(citations)
            if note:
                print(f"        {note}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
