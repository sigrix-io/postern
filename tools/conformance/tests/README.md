# What is in here

`fake_runner.py`, and nothing else. It is a fixture — a deliberately
conformant Postern runner the self-test spins over a socket, and can ask to
break exactly one rule at a time — not a test module. So `pytest` collects
nothing here, which is the intended state rather than a gap:

```console
$ pytest tests -q
no tests ran          # exit 5
```

The suite is [`../selftest.py`](../selftest.py), and it is run directly:

```console
$ python tools/conformance/selftest.py
```

## Why it is a script rather than a pytest suite

Three reasons, in increasing order of what it would cost to undo them.

**It matches the repository.**
[`scripts/validate.py`](../../../scripts/validate.py) and
[`scripts/check_links.py`](../../../scripts/check_links.py) are the same
shape — a `main() -> int` a workflow invokes directly — and the self-test
documents its own exit status as matching `validate.py`'s. Nothing in this
repository imports pytest, and no workflow installs it.

**Standard library only.** The self-test needs nothing the package does not
already depend on, which is what lets
[`conformance.yml`](../../../.github/workflows/conformance.yml) run it
against the *installed wheel* on 3.10 and 3.13 — the step that catches a
dependency missing from `pyproject.toml` before someone else's machine
does. A test runner would be the one thing installed for the tests alone.

**One check is a claim about the whole run.** `_the_readme_quotes_this_run`
compares [`../README.md`](../README.md)'s transcript of that command against
the tally every other check printed, in order — it has already caught three
simultaneous drifts, including a line added to the self-test that never
reached the block. Split the file into one test per check and that guard has
nothing to assert against, so a pytest layout would either drop it or keep a
whole-run entry point beside the tests and carry both shapes at once.

[Issue #133](https://github.com/sigrix-io/postern/issues/133) records the
decision and the alternatives weighed against it.
