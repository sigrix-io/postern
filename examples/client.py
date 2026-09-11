"""A Postern client in the standard library, from ``status`` to ``stream``.

    python examples/client.py http://127.0.0.1:8787 prompt="Say hello"

It reads the level from ``status`` before calling anything above Level 1
(SPEC.md §3), builds ``run``'s inputs from what ``describe`` declares
(§4.1.1), reads the error envelope on every refusal (§2.1), never renders a
``bytes`` output as prose (§4.1.4), and reads ``stream`` with the
event-stream grammar rather than a line at a time (§4.3).
"""

import base64
import json
import sys
import urllib.error
import urllib.request

PREFIX = "/postern/v0"


def call(base, verb, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"} if data else {}
    request = urllib.request.Request(base + PREFIX + "/" + verb, data=data, headers=headers)
    try:
        return urllib.request.urlopen(request, timeout=900)
    except urllib.error.HTTPError as refusal:  # §2.1: every non-2xx carries the envelope
        error = json.load(refusal)["error"]
        sys.exit(f"{verb}: {refusal.code} {error['code']} — {error['message']}")


def events(response):
    """The event-stream grammar: data joins across lines, a ':' line is a keepalive."""
    name, data = "", []
    for raw in response:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield name or "message", json.loads("\n".join(data))
            name, data = "", []
        elif line.startswith("event:"):
            name = line[6:].removeprefix(" ")
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        # id:, retry: and comment lines mean nothing to a Postern client


def show(output):
    if output["type"] == "text":
        print(output["value"])
    elif output["type"] == "bytes":  # §4.1.4: an artifact, never prose
        path = "output." + output["media_type"].split("/")[-1]
        with open(path, "wb") as handle:
            handle.write(base64.b64decode(output["value"]))
        print(f"wrote {path} ({output['media_type']})")
    else:  # §4.1.4: say which type, and do not call the run failed
        print(f"the run succeeded with an output type this client cannot render: {output['type']}")


def main(base, *pairs):
    status = json.load(call(base, "status"))
    describe = json.load(call(base, "describe"))
    given = dict(pair.split("=", 1) for pair in pairs)
    inputs = {}
    for declared in describe["inputs"]:
        value = given.get(declared["key"], declared.get("default"))
        if value is None:
            continue  # a required input left out is the runner's to refuse, by name (§4.2)
        inputs[declared["key"]] = json.loads(value) if declared["type"] == "number" and isinstance(value, str) else value
    print(
        f"{describe['agent']['name']} · level {status['level']} · {status['state']}"
        f" · entitlement {status['entitlement']['state']}",
        file=sys.stderr,
    )
    if status["level"] < 2:
        print("Level 1: describe and status only.", file=sys.stderr)
    elif status["level"] < 3:
        show(json.load(call(base, "run", {"inputs": inputs}))["output"])
    else:
        streamed = []
        for name, payload in events(call(base, "stream", {"inputs": inputs})):
            if name == "delta":
                streamed.append(payload["text"])
                print(payload["text"], end="", flush=True)
            elif name == "step":
                print(f"[{payload['status']}] {payload['name']}", file=sys.stderr)
            elif name == "done":  # §4.3: done's value is the result, the deltas were a preview
                if streamed and "".join(streamed) == payload["output"]["value"]:
                    print()
                else:
                    if streamed:
                        print("\n[the streamed text was superseded by done]")
                    show(payload["output"])
            elif name == "error":
                sys.exit(f"stream: {payload['error']['code']} — {payload['error']['message']}")


if __name__ == "__main__":
    main(*sys.argv[1:])
