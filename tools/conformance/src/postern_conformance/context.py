"""What one check learns and the next one needs.

The checks are ordered, and later ones depend on earlier answers: the level
rule in SPEC.md section 3 cannot be applied without `status.level`, and the
run probes cannot be built without `describe`'s `inputs`. This carries those
answers between them rather than having each re-fetch, which also keeps the
count of requests the checker makes small enough to reason about — a tool
that runs an agent twice by accident has spent someone's money.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Any


@dataclasses.dataclass
class Context:
    # Whether the caller opted into checks that actually execute the agent.
    execute: bool = False
    # The origin the CORS checks present themselves as. None means the
    # caller named none, and the origin checks that need one are skipped.
    origin: str | None = None

    status: dict[str, Any] | None = None
    describe: dict[str, Any] | None = None

    @property
    def level(self) -> int | None:
        """The runner's declared conformance level, if it stated a usable one."""
        if not isinstance(self.status, dict):
            return None
        level = self.status.get("level")
        return level if isinstance(level, int) and level in (1, 2, 3) else None

    @property
    def entitlement_state(self) -> str | None:
        if not isinstance(self.status, dict):
            return None
        entitlement = self.status.get("entitlement")
        if not isinstance(entitlement, dict):
            return None
        state = entitlement.get("state")
        return state if isinstance(state, str) else None

    @property
    def never_checked(self) -> bool:
        """True for §5.7.3's runner: `unknown`, and no check has ever completed.

        The two shapes of `unknown` are told apart by `checked_at`, and the
        specification says so in those words: one with a timestamp is a
        runner inside grace, still running, with a deadline; one without is
        a runner that cannot start. Only the second is decidable from
        outside, and it is fully decided — `run` and `stream` **MUST**
        answer `503` `unavailable`.
        """
        if self.entitlement_state != "unknown":
            return False
        if not isinstance(self.status, dict):
            return False
        entitlement = self.status.get("entitlement")
        return isinstance(entitlement, dict) and "checked_at" not in entitlement

    @property
    def refuses_runs(self) -> bool:
        """True where the specification says `run` and `stream` must refuse.

        Two states, and both are decidable from outside. `revoked` refuses
        with `403 not_entitled` (§5.7.4). A runner that has never completed
        a check refuses with `503 unavailable` (§5.7.3).

        The third shape is not here and must not be: `unknown` *with* a
        `checked_at` is a runner inside grace, and whether it has passed
        that grace cannot be determined from outside, so the run probes
        treat it as undecided. This property used to answer `revoked`
        alone, on that reasoning — which is right for the grace case and
        was silently covering the never-checked one, where the answer is
        fixed.
        """
        return self.entitlement_state == "revoked" or self.never_checked

    @property
    def runs_are_free(self) -> bool:
        """True where a `run` would execute the agent rather than be refused.

        This is what gates every probe that could spend money: where the
        runner would run, the checker does not ask unless told to.
        """
        return self.entitlement_state in (None, "active", "not_required")

    @property
    def credentials_satisfied(self) -> bool | None:
        """Whether `status` says the environment carries what the agent needs.

        Three answers, not two. `None` means the runner said nothing, which
        is not the same as saying no — a runner declaring no credentials
        block has not claimed its environment is incomplete.
        """
        if not isinstance(self.status, dict):
            return None
        credentials = self.status.get("credentials")
        if not isinstance(credentials, dict):
            return None
        satisfied = credentials.get("satisfied")
        return satisfied if isinstance(satisfied, bool) else None

    @property
    def missing_credentials(self) -> list[str]:
        if not isinstance(self.status, dict):
            return []
        credentials = self.status.get("credentials")
        if not isinstance(credentials, dict):
            return []
        missing = credentials.get("missing")
        return [name for name in missing if isinstance(name, str)] if isinstance(missing, list) else []

    @property
    def declares_idempotent_retry(self) -> bool:
        if not isinstance(self.describe, dict):
            return False
        capabilities = self.describe.get("capabilities")
        if not isinstance(capabilities, dict):
            return False
        return capabilities.get("idempotent_retry") is True

    @property
    def inputs(self) -> list[dict[str, Any]]:
        if not isinstance(self.describe, dict):
            return []
        declared = self.describe.get("inputs")
        return [item for item in declared if isinstance(item, dict)] if isinstance(declared, list) else []

    @property
    def required_input_keys(self) -> list[str]:
        return [
            item["key"]
            for item in self.inputs
            if item.get("required") is True and isinstance(item.get("key"), str)
        ]

    def a_body_that_cannot_execute(self) -> dict[str, Any] | None:
        """A `run` body a conforming runner must refuse before executing.

        Section 4.2 requires a request omitting a `required` input to be
        rejected with `bad_request`, so an empty `inputs` map is refused by
        any runner declaring one — which is what makes it safe to send at an
        agent that spends money on every run.

        Returns None where the agent declares no required input, because
        then the same body is a valid request and sending it would run the
        agent. There is no clever substitute *for this rule*: §4.2 is about
        what a runner does with an incomplete request, and against an agent
        requiring nothing there is no incomplete request to send.

        A probe for a different rule can still be safe, and `levels.py` is
        the one that has to be: a malformed body — `inputs` typed as
        something other than an object — cannot be executed by anyone, and
        §4.6 step 1 puts the level check ahead of reading it, so a
        conformant runner answers 501 without ever looking. That works
        there because the rule under test sits above the body; it would not
        work here, where the body *is* the test.
        """
        return {"inputs": {}} if self.required_input_keys else None

    def a_valid_body(self) -> dict[str, Any] | None:
        """A `run` body that satisfies every declared input, or None.

        Used only where the caller passed `--execute`, because a body a
        runner has no grounds to refuse is a body that runs the agent. It
        fills each `required` input from its own declaration — the first
        option of a `select`, a number inside any declared bounds, a short
        string for anything else — so the request is one the runner's own
        validation should accept.

        Returns None where an input cannot be filled from what `describe`
        says about it, rather than guessing: a request refused as
        `bad_request` would be read by the checks that use this as the
        runner declining the *media type*, which is a different finding
        entirely.
        """
        inputs: dict[str, Any] = {}
        for declaration in self.inputs:
            if declaration.get("required") is not True:
                continue
            key = declaration.get("key")
            if not isinstance(key, str):
                return None
            value = _fill(declaration)
            if value is None:
                return None
            inputs[key] = value
        return {"inputs": inputs}

    def a_body_that_fails_validation(self) -> tuple[dict[str, Any], str] | None:
        """A `run` body §4.2 obliges the runner to refuse, and why.

        Every other input is filled the way `a_valid_body` fills it, so the
        request differs from an acceptable one in exactly the constraint
        being tested — a refusal cannot then be read as the runner disliking
        something else about it, which is the same care `a_different_valid_body`
        takes for the idempotency probe.

        Returns `None` where no declared `validation` can be violated
        derivably. That is not a gap to paper over: §4.2 binds a runner to
        the validation it *declares*, so an agent declaring none is owed no
        refusal and there is nothing here to ask about.
        """
        base = self.a_valid_body()
        if base is None:
            return None

        for declaration in self.inputs:
            key = declaration.get("key")
            if not isinstance(key, str):
                continue
            broken = _violate(declaration)
            if broken is None:
                continue
            value, why = broken
            inputs = dict(base["inputs"])
            inputs[key] = value
            return {"inputs": inputs}, f"`{key}` carrying {why}"
        return None

    def a_different_valid_body(self) -> dict[str, Any] | None:
        """A second valid `run` body, differing from `a_valid_body()`, or None.

        Section 4.2 binds an `Idempotency-Key` to the `inputs` it was first
        answered for, so checking that rule needs a body a runner has no
        grounds to refuse *except* the key it arrives under. One input is
        varied and the rest are left alone: the smallest difference that
        makes it a different request, so a refusal cannot be read as the
        runner disliking something else about it.

        Returns None where no required input can be varied within its own
        declared validation — a `select` with one option, a number pinned
        between equal bounds, a `pattern` this checker will not solve.
        Guessing past a `validation` would produce a `bad_request` that
        reads as the runner failing to conflict, which is the opposite
        finding.
        """
        body = self.a_valid_body()
        if body is None:
            return None

        inputs = dict(body["inputs"])
        for declaration in self.inputs:
            if declaration.get("required") is not True:
                continue
            key = declaration.get("key")
            if not isinstance(key, str) or key not in inputs:
                continue
            varied = _vary(declaration, inputs[key])
            if varied is not None:
                inputs[key] = varied
                return {"inputs": inputs}
        return None


def _violate(declaration: dict[str, Any]) -> tuple[Any, str] | None:
    """A value one declared `validation` must reject, and what it breaks.

    The inverse of `_fill`, and it has to be derived the same way rather
    than guessed: a value that merely looks wrong is a value the runner may
    legitimately accept, and reading its `200` as a defect would be the
    checker asserting a rule the runner never declared.

    Returns `None` where the declaration constrains nothing this can break.
    A `pattern` is the one that cannot be inverted in general, so the
    candidate is tested against the pattern before it is offered — an
    unanchored or permissive expression matches it and yields `None`.
    """
    validation = declaration.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    kind = declaration.get("type")

    if kind == "select":
        options = validation.get("options")
        if isinstance(options, list) and options:
            outside = "postern-conformance-not-an-option"
            if outside not in options:
                return outside, f"a value outside its {len(options)} declared options"
        return None

    if kind == "number":
        high, low = validation.get("max"), validation.get("min")
        if isinstance(high, (int, float)) and not isinstance(high, bool):
            return high + 1, f"a number above its declared max of {high}"
        if isinstance(low, (int, float)) and not isinstance(low, bool):
            return low - 1, f"a number below its declared min of {low}"
        return None

    max_length = validation.get("max_length")
    if isinstance(max_length, int) and max_length >= 0:
        return "x" * (max_length + 1), f"a string longer than its declared max_length of {max_length}"

    pattern = validation.get("pattern")
    if isinstance(pattern, str):
        candidate = "postern-conformance-violates-the-pattern"
        try:
            if re.search(pattern, candidate) is None:
                return candidate, "a string its declared pattern does not match"
        except re.error:
            # An expression this checker cannot compile is one it cannot
            # claim to be violating. The runner's own engine may differ.
            return None
    return None


def _fill(declaration: dict[str, Any]) -> Any:
    """A value satisfying one input declaration, or None where none is derivable."""
    validation = declaration.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    kind = declaration.get("type")

    if kind == "select":
        options = validation.get("options")
        if isinstance(options, list) and options:
            return options[0]
        return None

    if kind == "number":
        low, high = validation.get("min"), validation.get("max")
        if isinstance(low, (int, float)):
            return low
        if isinstance(high, (int, float)):
            return high
        return 1

    # `text`, and — per section 4.1.1 — any type a client does not
    # recognise, which it must treat as text rather than failing.
    if isinstance(validation.get("pattern"), str):
        # A pattern this checker would have to solve to satisfy. Guessing a
        # matching string is how a conformance tool starts reporting its own
        # cleverness as the runner's behaviour.
        return None
    text = "postern conformance check"
    max_length = validation.get("max_length")
    if isinstance(max_length, int) and max_length >= 0:
        return text[:max_length]
    return text


def _vary(declaration: dict[str, Any], current: Any) -> Any:
    """A second value for one input: valid, and different from `current`.

    The counterpart to `_fill`, and it answers None in the same spirit —
    where a declaration admits exactly one value this checker can derive,
    there is no second request to make of it. Every branch re-reads the
    declaration's own `validation` rather than trusting that `current` came
    from `_fill`, so a caller varying a value from anywhere else still gets
    one inside the declared bounds.
    """
    validation = declaration.get("validation")
    validation = validation if isinstance(validation, dict) else {}
    kind = declaration.get("type")

    if kind == "select":
        options = validation.get("options")
        if isinstance(options, list):
            for option in options:
                if option != current:
                    return option
        return None

    if kind == "number":
        if not isinstance(current, (int, float)):
            return None
        low, high = validation.get("min"), validation.get("max")
        for candidate in (current + 1, current - 1):
            if isinstance(low, (int, float)) and candidate < low:
                continue
            if isinstance(high, (int, float)) and candidate > high:
                continue
            return candidate
        return None

    # `text`, and anything a client reads as text (section 4.1.1).
    if isinstance(validation.get("pattern"), str):
        return None
    text = "a second postern conformance body"
    max_length = validation.get("max_length")
    if isinstance(max_length, int):
        if max_length <= 0:
            return None
        text = text[:max_length]
    # A short `max_length` can truncate this to whatever `_fill` produced.
    return text if text != current else None
