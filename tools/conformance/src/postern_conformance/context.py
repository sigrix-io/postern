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
    def refuses_runs(self) -> bool:
        """True where SPEC.md section 5.7.4 says `run` must refuse.

        `revoked` refuses with `403 not_entitled`; `unknown` refuses with
        `503 unavailable` only once past the grace, which a client cannot
        determine from outside — so `unknown` is not counted here and the
        run probes treat it as undecided.
        """
        return self.entitlement_state == "revoked"

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
        agent. There is no clever substitute: an agent that requires nothing
        can be started by an empty map, and a checker that sent one anyway
        would be doing the thing it exists to avoid.
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
