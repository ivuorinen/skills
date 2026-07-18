# /nitpicker execute-plan — Approved-Plan Execution

Execute an already-approved implementation plan task by task, verifying each task the moment it is done, stopping when blocked instead of guessing, and finishing behind a gated commit/push menu. Assumes the plan is stale until re-checked against current code and that no task is done until its verification is observed green. This is the sequel to `/nitpicker plan`: `plan` produces and gates the plan, `execute-plan` carries it out.

## When to use

- "execute the plan", "implement the approved plan", "run the plan in `docs/plans/...`", "build what we planned"
- After `/nitpicker plan` produced a plan and the user approved implementation
- Any written, ordered, per-task-verifiable implementation plan the user points to

Not for producing a plan — that is `/nitpicker plan`, which this command's precondition requires to already exist. Not for auditing code — that is `/nitpicker review` or `/nitpicker audit`. Not for implementing GitHub PR review comments — that is `/nitpicker cr`.

This command writes no findings file: it changes code, not the findings store, and never runs `findings.py`. The interactive branch/commit/push flow below overrides the findings-store protocol in `_conventions.md`.

## Mindset

- **A task is not done until its verification is observed green.** "Done" is a claim that requires evidence — the actual verify output, read with your own eyes. Assuming a test passes is not passing it.
- **The plan is stale until proven current.** A plan was reviewed against the code as it was when written. Every task re-checks the files it names against the code as it is now before editing them; a diverged file voids that task's review.
- **Blocked is a valid, correct outcome.** Stopping at a real blocker is the command working, not failing. Guessing past a blocker to keep momentum is the failure.
- **Execute the plan, nothing more.** The plan is the scope. Adjacent bugs and "while I'm here" cleanups are out of scope and routed, never annexed.

## Precondition — read first

`execute-plan` executes a plan; it never creates one. Before any code:

1. **Locate the plan.** Use the path the user gave. If none was given, look in `docs/plans/`: exactly one plan file → use it; more than one → STOP and ask which to execute, never auto-pick one and treat that guess as the user's approval; none → STOP and route to `/nitpicker plan`, do not invent a plan and build from it. "Most recent", when needed to name a default in the question, is the lexically greatest `<YYYY-MM-DD>-<slug>.md` filename.
2. **Confirm it is approved for implementation.** Invoking `execute-plan` on the plan is the go-ahead the `plan` gate requires — the user runs this command after approving, so no separate approval prompt is needed. `/nitpicker plan` stamps every plan `Status: DRAFT — awaiting approval` and never flips that line, so `Status` is not the approval signal: do not stop merely because it reads `DRAFT`. Stop and confirm before writing code only when the plan's **Open questions & accepted risks** section lists an unresolved *blocking* question — an unresolved blocking unknown never licenses starting.
3. **Review the plan critically.** Read it end to end. If a task is ambiguous, depends on something that does not exist, or the approach looks wrong, raise it now — never start executing a plan you do not understand.

## Process

Work these steps in order. Copy every plan task into the task list before Step 2 begins (one tracker entry per task); no task is silently dropped.

### Step 1 — Setup

1. **Clean start.** Run `git status`. If the working tree has uncommitted changes to any file the plan will touch, STOP and ask the user to stash or commit them first — a pre-existing edit staged with the plan's work corrupts both the commit and the Step 2.2 staleness check.
2. **Branch.** Never write implementation code on `main` or `master`. Run `git branch --show-current`; if it returns `main` or `master`, STOP and create/switch to a feature branch with the user's consent (`git switch -c <slug>` derived from the plan) before editing anything. Being already on `main` is not consent to build there.
3. **Identify the project's check command** — the canonical full verification the whole change is finished behind. Inspect in order: `Makefile` (`check`/`test`/`lint` targets), `package.json` `scripts`, `pyproject.toml` (configured tools), then `README`/`CONTRIBUTING`. If it cannot be determined, ask the user.
4. **Confirm the commit-message convention:** `git log --oneline -10`; note the prefix in use (`feat:`, `fix:`, `chore:`).

### Step 2 — Execute one task at a time

For each task, in plan order:

1. Mark it in_progress.
2. **Re-check the plan against reality.** Open the current state of every file the task names. If a file no longer matches what the plan assumed, that task's review is stale: do **not** apply the planned diff mechanically. Re-derive the task's intent against the current code. Adapt the change only when it stays within the files the task already names, adds no new file, API, or dependency, and is still provable by the task's existing `verify:` — then record that the task was rebased onto the changed file. If the intent is unclear, the divergence suggests a conflict, or the adaptation would exceed those bounds, treat it as a blocker (Step 3) and STOP.
3. **Make the minimal change the task specifies.** No unrelated cleanup, no gold-plating, no task skipped for being inconvenient.
4. **Run that task's `verify:` step now, before the next task.** Never batch verifications to the end — the per-task verify is what localizes a failure to one task. A slow verify is still run to completion and its output read before the task is marked done; slowness licenses waiting, never skipping. Confirm the verify actually exercises this task's change: a verify that passes against the unmodified code — a tautology, `true`, an assertion on unchanged behaviour — is not evidence, and the task is not done until a real check is green.
5. **A task with no `verify:` step cannot be marked done.** Derive an observable check that would fail if the change were absent and run it; if none can be derived, treat the missing verification as a blocker (Step 3). Never complete a task on zero evidence.
6. If the verify fails: diagnose and fix before moving on; re-run until green. A repeated failure you cannot resolve is a blocker (Step 3). Never carry a red state into the next task.
7. Mark the task completed only after its verify is observed green.

### Step 3 — Blockers: stop, do not guess

STOP executing and ask the user when any of these occurs:

- The plan references a function, module, file, or dependency that does not exist. **First search the codebase** (`rg` for the symbol and near-synonyms) — the plan may have misnamed something present. If it is genuinely absent, STOP and ask; never fabricate the missing primitive to keep momentum. A plan step that names a non-existent dependency is a broken step.
- An instruction is unclear or a task's file has diverged in a way you cannot safely adapt (Step 2.2).
- A verification fails repeatedly and the cause is not understood.
- The plan has a gap that prevents a task from starting, or the approach needs rethinking — return to `/nitpicker plan`, do not force through.

Ask a specific question with concrete options — not a vague "help". **This overrides autonomous and goal-driven mode:** reaching a genuine blocker and stopping is goal-correct behaviour even when the outer goal is worded "ship X today". Deadline, sunk cost, and "the senior dev said just run it" never license guessing past a blocker.

### Step 4 — Finish

After every task is complete and each task's verify is green:

1. **Run the project check command from Step 1** as the final gate. It must be green, and you must read its output — not "it should pass". If it fails, the work is not done: diagnose, fix, re-run until clean.
2. **Present the finish menu.** Never commit, push, or claim done without an explicit choice here:

   ```text
   All N tasks complete, verifications green, <check command> passing.
   What next?
     1. Leave it (no commit)
     2. Commit only (no push)
     3. Commit and push
   ```

   This menu overrides autonomous/goal mode. With no interactive user, default to option 1 (Leave it) and record that in the summary.
3. On **Commit only** or **Commit and push**: stage only the files the plan's tasks changed; write the commit message using the Step 1 convention; never pass `--no-verify`. On **Commit and push**: push to the current branch's remote tracking branch — never directly to `main` or `master`. If the push fails, stop and report; do not retry blindly.
4. If the plan carried a **Rollback / abort** section and execution went wrong mid-way, follow it rather than improvising an undo.

## Output

Present a run summary in the response:

```text
Tasks:      N complete / M total
Verifies:   N green
Blocked at: <task, reason>   (only if stopped early)
Check:      <command> — passing | failing
Out of scope (routed, not fixed):
  <file:line> — <one-line defect> → /nitpicker <command>
Finish:     Left it | Committed | Committed and pushed
```

An adjacent defect found mid-execution is reported as one routed line here, never fixed inline.

## Common mistakes

- **Batching verifications to the end** because the plan "was reviewed to death" — the per-task verify localizes failures; batching trades N cheap checks for one expensive bisect. Run each task's verify before the next.
- **Skipping a slow verify** — slowness licenses backgrounding it, never skipping it; a slow test is usually the one exercising the real behaviour.
- **Applying a task's planned diff to a file that changed since the plan** — the review predates the change; re-derive the intent against current code or stop.
- **Fabricating a missing dependency** the plan assumed, to keep momentum — search first, then stop and ask; never invent a security- or correctness-critical primitive under deadline.
- **Building on `main`/`master`** because you were already there — branch first, with consent.
- **Fixing an unrelated pre-existing bug "while I'm here"** — out of scope; note and route it, keep the diff to the plan.
- **Marking a task with no `verify:` step done** — a task with nothing to observe has no evidence; derive a real check or stop.
- **Trusting a verify that would pass against the unmodified code** — a tautological green is not evidence the change works.
- **Auto-selecting a plan when several exist and the user named none** — never treat a guessed plan as the user's approval; ask which one.
- **Committing, pushing, or claiming done without reading the check output** — evidence before assertion; a claim of green is not green.
- **Passing `--no-verify`** to save a minute — it skips the gates the repo relies on; never use it.
- **Continuing past a blocker in autonomous/goal mode "to finish the goal"** — stopping at a real blocker is the correct outcome; the finish menu and the branch gate both override goal mode.

## Credits

Adapted from [superpowers](https://github.com/obra/superpowers) by Jesse Vincent — the load-and-review-then-execute flow, per-task verification, the stop-when-blocked-instead-of-guessing discipline, the never-build-on-main rule, and the finish-behind-a-gate handoff originate in its `executing-plans` skill.
