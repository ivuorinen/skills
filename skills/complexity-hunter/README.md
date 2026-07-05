# complexity-hunter

Persistent anti-over-engineering enforcement. Forces the laziest solution that actually works — simplest, shortest, most minimal — by climbing a reuse-first ladder (YAGNI → codebase → stdlib → platform → installed dependency → one line → minimum code) before any new code is written. Channels a lazy senior developer: lazy means efficient, not careless, and the best code is the code never written. Once invoked it stays active every response, and it never shortens the reading — the problem is understood fully first, then the minimum ships.

## When to Use

- Any coding task: writing, adding, refactoring, fixing, reviewing, or designing code
- Choosing libraries, frameworks, or dependencies
- Reviewing a diff, plan, or design for over-engineering, bloat, or unnecessary dependencies
- Auditing a whole repo for over-engineering — "find bloat", "what can I delete from this repo"
- "Be lazy" / "simplest solution" / "YAGNI" / "do less" / "stop over-engineering"

**When NOT to use:**

- Non-coding requests — general knowledge, prose, translation, summaries, recipes
- Hunting correctness bugs in existing code → use [adversarial-reviewer]
- A whole-repo defect audit → use [nitpicker]

## complexity-hunter vs. adversarial-reviewer

| | complexity-hunter | adversarial-reviewer |
|---|---|---|
| Question | "What should not be built at all?" | "What is built wrong?" |
| When | While designing and writing the code | After the code exists |
| Output | The minimal design/diff, plus what was skipped and when to add it | Findings report of bugs and defects |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | The task, every file the change touches, the project manifest (for what is already installed), existing helpers and patterns in the codebase |
| **Writes** | stdout only — no findings file |

## How to Invoke

```
/complexity-hunter
```

Activation is sticky: the skill governs every subsequent coding response in the session until the user clearly asks to disable it ("stop complexity-hunter", "complexity-hunter off", or an unambiguous skill-specific equivalent). Non-coding responses pass through unchanged; the skill stays armed for the next coding task.

## The Ladder

Stop at the first rung that holds:

1. **Does this need to exist at all?** Speculative need = skip it, say so in one line. (YAGNI)
2. **Already in this codebase?** Reuse the helper, util, type, or pattern that already lives here.
3. **Stdlib does it?** Use it.
4. **Native platform feature covers it?** `<input type="date">` over a picker lib, CSS over JS, a DB constraint over app code.
5. **Already-installed dependency solves it?** Use it — direct dependencies only, never add a new one for what a few lines can do.
6. **Can it be one line?** One line.
7. **Only then:** the minimum code that works.

The ladder runs *after* the problem is understood, never instead of understanding it. Bug fixes target the root cause in the shared function all callers route through, never the symptom path the ticket names.

## Output Format

Code first, then at most three short lines:

```
[code] → skipped: [X], add when [Y].
```

Review and whole-repo audit findings are tagged one-liners (`delete:` / `stdlib:` / `native:` / `yagni:` / `shrink:`), ranked biggest cut first; a repo audit ends with `net: -<N> lines, -<M> deps possible.` and applies nothing. Scope is over-engineering only — correctness routes to [adversarial-reviewer], security to [security-auditor], and performance to [perf-auditor].

Non-trivial logic (any branch, loop, parser, or money/security path) ships with one runnable check — an assert-based self-check or one small test file in the project's existing convention. Never simplified away: input validation at trust boundaries, error handling that prevents data loss, security measures, accessibility basics, anything the user explicitly requested.

## Credits

Adapted from [ponytail](https://github.com/DietrichGebert/ponytail) by Dietrich Gebert — the lazy-senior mindset, the ladder, the output pattern, and the audit tags originate there, reshaped to this repo's skill conventions.

## Related Skills

- [adversarial-reviewer] — hunts correctness bugs in existing code; complexity-hunter prevents the excess code from existing
- [nitpicker] — exhaustive whole-repo defect audit
- [pr-reviewer] — reviews a diff for GitHub; complexity-hunter governs how the diff is written in the first place

---

[adversarial-reviewer]: ../adversarial-reviewer/README.md
[nitpicker]: ../nitpicker/README.md
[pr-reviewer]: ../pr-reviewer/README.md
[security-auditor]: ../security-auditor/README.md
[perf-auditor]: ../perf-auditor/README.md
