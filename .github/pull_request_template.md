<!--
CONTRIBUTING.md is the authority on why each of these is asked for:
https://github.com/sigrix-io/postern/blob/main/CONTRIBUTING.md#pull-requests
-->

## What this changes

<!-- What is different afterwards, and why. -->

## This change breaks

<!--
Required. If nothing breaks, write "Nothing."

Before 1.0, breaking things is allowed. Breaking them without saying so is
not — an unmentioned break is discovered by whoever built on the old shape.
-->

## Checklist

- [ ] **One change.** A normative change is not bundled with unrelated fixes.
- [ ] **Breakage stated above**, or "Nothing."
- [ ] **Examples and schemas updated**, and `python scripts/validate.py` passes
      locally. It runs in CI on every pull request too, including from forks.
- [ ] **Identifier change called out**, if you added or edited a file in
      `schemas/`. The serving side picks it up on a schedule either way; saying
      so here is what gets it landed the same day.
- [ ] **Appendix A entry added**, if anything normative changed.
