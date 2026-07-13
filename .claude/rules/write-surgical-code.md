---
paths:
  - "scripts/**/*.py"
  - "skills/**/scripts/*.py"
  - "tests/**/*.py"
---

# Writing Code In This Repo

Applies to the repo's own Python — the shipped skill tools, the internal dev
scripts, the hooks, and the tests. Distilled from [Andrej Karpathy's notes on
LLM coding pitfalls](https://x.com/karpathy/status/2015883857489522876). The
nitpicker commands already audit *for* these on consumer code; this rule holds
the same bar on the code we ship *to* run those audits.

## Think before coding

State the assumption a change rests on before writing it, not after. When a
request has two readings that produce different code, name both and pick one
out loud — never encode a silent guess. A simpler approach than the one asked
for gets said, not just done.

## Simplicity first

Minimum code that solves the problem, nothing speculative — no abstraction for
a single call site, no config knob for a value that never changes, no error
handling for scenarios that cannot occur. Shipped tools under `skills/*/scripts/`
are stdlib-only (see [use-uv-runner.md](use-uv-runner.md)); reach for the
standard library before writing your own. If the diff could be half the size
and still correct, make it half the size.

## Surgical changes

Every changed line traces to the task. Do not reformat, rename, or "improve"
adjacent code, comments, or imports that the task did not touch — match the
existing style even where you would write it differently. Remove only the
imports, variables, and helpers your own change orphaned; pre-existing dead
code gets mentioned, not deleted, unless removing it is the task.

## Verifiable done

A change is done when a check proves it, not when it looks right. Non-trivial
logic (a branch, a parser, a validator, a findings-store mutation) leaves one
runnable check behind — a `test_*.py` in the existing pytest convention, or an
assert-based self-check — and `make check` passes before the change is called
finished. "Make it work" is not a success criterion; "this test now passes" is.
