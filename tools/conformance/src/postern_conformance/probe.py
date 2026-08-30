"""The HTTP layer: one connection per request, and nothing above it.

`http.client` rather than a request library, for the reason recorded in
`pyproject.toml`: a conforming runner serves four routes on loopback and
ships without a web framework, so a checker for it should not ask an
implementer to install more to test the protocol than to speak it.

Two things here are not what a convenience client would do, and both are
load-bearing.

**Headers are kept as a multi-map.** SPEC.md section 2.3 turns on the exact
value of `Access-Control-Allow-Origin` and on `Vary: Origin` being present,
and a runner that emits a header twice with different values has done
something a `dict` would hide by keeping one of them.

**Nothing is retried and nothing is followed.** A redirect is not part of
this protocol, and a checker that quietly followed one would report on
whatever it landed on.
"""

from __future__ import annotations

import dataclasses
import http.client
import json
import socket
import ssl
import urllib.parse
from typing import Any, Iterator

PATH_PREFIX = "/postern/v0"

# Long enough that a slow `describe` on a cold runner is not reported as a
# failure, short enough that an unreachable port does not hold the run.
# A `run` is given its own, much longer, budget by the caller.
DEFAULT_TIMEOUT_SECONDS = 30.0


class Unreachable(RuntimeError):
    """The runner could not be spoken to at all.

    Distinct from any HTTP status, because it is the one outcome that says
    nothing whatever about conformance — there is a difference between a
    runner that broke a rule and a port with nothing behind it, and only
    the first is this tool's subject.
    """


@dataclasses.dataclass(frozen=True)
class Response:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    # 11 for HTTP/1.1, 10 for HTTP/1.0, as `http.client` reports it.
    # Section 2 requires HTTP/1.1, and a runner answering 1.0 has no
    # chunked encoding — which `stream` needs to send events as they
    # happen rather than at the end.
    http_version: int = 11

    def header(self, name: str) -> str | None:
        """The single value of a header, or None.

        Returns None where the header appears more than once, so a caller
        asking for one value never silently receives the first of several;
        `header_values` is how a caller asks that question deliberately.
        """
        values = self.header_values(name)
        return values[0] if len(values) == 1 else None

    def header_values(self, name: str) -> tuple[str, ...]:
        lowered = name.lower()
        return tuple(value for key, value in self.headers if key.lower() == lowered)

    @property
    def media_type(self) -> str:
        """`Content-Type` with parameters stripped and case folded."""
        raw = self.header_values("content-type")
        if not raw:
            return ""
        return raw[0].split(";", 1)[0].strip().lower()

    @property
    def json(self) -> Any:
        """The parsed body, or None where it is not JSON.

        None rather than a raise: a body that should have been JSON and is
        not is a finding for a check to report, not an error for the
        transport to throw.
        """
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def normalise_target(target: str) -> tuple[str, str, int, str]:
    """Split a target into scheme, host, port and origin.

    Accepts what someone will actually paste: a bare origin, an origin with
    a trailing slash, or the full `/postern/v0` prefix copied out of the
    specification. All three name the same runner, and refusing two of them
    would be a papercut in the first thing anyone types.
    """
    if "://" not in target:
        target = "http://" + target

    parsed = urllib.parse.urlsplit(target)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"unsupported scheme {parsed.scheme!r} — expected http or https")
    if not parsed.hostname:
        raise ValueError(f"no host in {target!r}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    path = parsed.path.rstrip("/")
    if path and not path.endswith(PATH_PREFIX):
        raise ValueError(
            f"unexpected path {parsed.path!r} in the target. Give the runner's "
            f"origin (http://host:port) or its {PATH_PREFIX} prefix."
        )

    origin = f"{parsed.scheme}://{parsed.netloc}"
    return parsed.scheme, parsed.hostname, port, origin


class Runner:
    """A runner under test, addressed by origin."""

    def __init__(self, target: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.scheme, self.host, self.port, self.origin = normalise_target(target)
        self.timeout = timeout

    def __str__(self) -> str:
        return self.origin

    def _connect(self, timeout: float) -> http.client.HTTPConnection:
        if self.scheme == "https":
            return http.client.HTTPSConnection(
                self.host, self.port, timeout=timeout, context=ssl.create_default_context()
            )
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def request(
        self,
        method: str,
        verb: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        """Call one Postern verb and read the whole answer.

        `verb` is the bare name — `describe`, `run` — and the version prefix
        is added here so no check can spell it differently.
        """
        connection = self._connect(timeout or self.timeout)
        try:
            connection.request(
                method, f"{PATH_PREFIX}/{verb}", body=body, headers=headers or {}
            )
            raw = connection.getresponse()
            return Response(
                status=raw.status,
                headers=tuple((key, value) for key, value in raw.getheaders()),
                body=raw.read(),
                http_version=raw.version,
            )
        except (OSError, socket.timeout, http.client.HTTPException) as exc:
            raise Unreachable(f"{method} {PATH_PREFIX}/{verb}: {exc}") from exc
        finally:
            connection.close()

    def get(self, verb: str, **kwargs: Any) -> Response:
        return self.request("GET", verb, **kwargs)

    def post(self, verb: str, **kwargs: Any) -> Response:
        return self.request("POST", verb, **kwargs)

    def options(self, verb: str, **kwargs: Any) -> Response:
        return self.request("OPTIONS", verb, **kwargs)

    def post_json(
        self,
        verb: str,
        payload: Any,
        *,
        content_type: str = "application/json",
        extra_headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Response:
        encoded = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(encoded)),
            "Accept": "application/json",
        }
        headers.update(extra_headers or {})
        return self.request("POST", verb, body=encoded, headers=headers, timeout=timeout)

    def stream(
        self,
        payload: Any,
        *,
        timeout: float,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[Response, list[tuple[str, str]]]:
        """POST `stream` and read the SSE events as they arrive.

        Returns the response (with an empty body, since the body is the
        stream) and the events as `(event_name, data)` pairs in wire order. The framing rules in
        SPEC.md section 4.3 — `start` first, exactly one `done` or `error`
        last — are about that order, so the order is what is preserved and
        nothing is coalesced or sorted on the way out.

        A field with no `event:` line is reported as `message`, which is
        what a browser's `EventSource` would call it. That is not a
        courtesy: it is how an unnamed event becomes visible to the check
        that says every event must be named, rather than being dropped here
        and passing.
        """
        encoded = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Content-Length": str(len(encoded)),
            "Accept": "text/event-stream",
        }
        headers.update(extra_headers or {})

        connection = self._connect(timeout)
        try:
            connection.request("POST", f"{PATH_PREFIX}/stream", body=encoded, headers=headers)
            raw = connection.getresponse()
            headers = tuple((key, value) for key, value in raw.getheaders())

            if raw.status != 200:
                # An error before the stream starts is an ordinary JSON
                # body, not SSE. Hand it back as an ordinary response so the
                # caller validates it as the envelope it is.
                return (
                    Response(raw.status, headers, raw.read(), raw.version),
                    [],
                )

            events = list(_read_sse(raw))
            return Response(raw.status, headers, b"", raw.version), events
        except (OSError, socket.timeout, http.client.HTTPException) as exc:
            raise Unreachable(f"POST {PATH_PREFIX}/stream: {exc}") from exc
        finally:
            connection.close()


def _read_sse(stream: Any) -> Iterator[tuple[str, str]]:
    """Parse an SSE body into (event, data) pairs.

    Only as much of the format as this protocol uses: `event:` and `data:`,
    events separated by a blank line, and `data:` accumulating across lines
    with a newline between them, per the EventSource specification. `id:`
    and `retry:` are ignored, and a comment line (one starting `:`) is
    skipped — Postern defines no use for any of the three, and a checker
    that choked on one would fail a runner for sending something the wire
    format allows.
    """
    event_name = ""
    data_lines: list[str] = []

    for raw_line in stream:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

        if not line:
            if data_lines or event_name:
                yield (event_name or "message", "\n".join(data_lines))
            event_name = ""
            data_lines = []
            continue

        if line.startswith(":"):
            continue

        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]

        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    # A stream that ends without a trailing blank line still delivered its
    # last event. Dropping it here would report a missing `done` that was
    # sent, which is a failure invented by the reader.
    if data_lines or event_name:
        yield (event_name or "message", "\n".join(data_lines))
