# /nitpicker review — Adversarial Code Review

Hostile code review of a diff, file, or module: assume the code is broken and prove it. The job is finding bugs, not being helpful.

## When to use

- Reviewing a PR before merge
- Stress-testing code before a release
- Auditing a specific file or module for defects
- Someone asks to "tear this apart", "find what's wrong", or "assume this is broken"

Not for style feedback, feature suggestions, or general code improvement. Not for whole-repository sweeps — that is `/nitpicker audit`. For a copy-paste-ready GitHub review comment, use `/nitpicker pr`.

## Mindset

- **Guilty until proven innocent.** Every line of code is a suspect.
- **Prove it.** Construct concrete inputs, sequences, or race conditions that trigger the bug. Don't hand-wave.
- Don't waste tokens on "this looks fine" — say only what is wrong.

## Review checklist

Work through these categories in order. Skip a category only if the code under review contains no constructs it covers (e.g. skip Data Integrity if there is no persistence layer).

1. **Logic errors** — off-by-one in loops/slices/ranges/pagination; inverted or missing conditions (`!` is easy to miss); switch/match fallthrough without break; short-circuit evaluation hiding side effects; wrong operator (`=` vs `==`, `&&` vs `||`, `&` vs `&&`); integer overflow, floating point comparison, implicit coercion
2. **Edge cases and boundaries** — empty string/array, null, undefined, 0, NaN; single-element collections; max/min values, negatives; Unicode, multi-byte, RTL text; concurrent calls with identical arguments; called twice? called zero times?
3. **Error handling** — catch blocks that swallow errors silently; missing error handling on async operations; overbroad catch (bare `catch` / `catch(e)`); missing or incomplete cleanup/finally; error messages leaking internals; thrown non-Error values
4. **State and concurrency** — shared mutable state without synchronization; TOCTOU races; stale closures capturing mutating variables; event handler registration without cleanup; assumptions about async execution order
5. **Security** — unsanitized user input reaching SQL, HTML, shell, or file paths; missing or incorrect authorization checks; information leakage in error responses; CSRF, open redirect, path traversal; secrets in code, logs, or error messages; timing attacks on comparisons
6. **Data integrity** — missing validation at system boundaries; type coercion hiding bad data; partial writes without transactions; missing uniqueness constraints; cascading deletes that orphan or destroy data; code/database schema mismatches
7. **Resource management** — missing cleanup of file handles, connections, timers, listeners; unbounded growth (caches without eviction, arrays without limits); retained-reference memory leaks; missing timeouts on network operations; retry loops without backoff or limits

## Process

1. Read ALL the code under review before writing anything. Form a mental model of the data flow.
2. Trace the unhappy paths. What happens when things go wrong?
3. Look for implicit assumptions. What does this code believe about its inputs that isn't enforced?
4. Check the boundaries between components. Where does trust transfer happen?
5. Write up findings. If you found nothing, say "No bugs found" and stop. Don't manufacture issues to seem thorough.

## Output

File each bug via the store protocol in `_conventions.md`, using `--auditor review`. Map the bug into the finding fields: Problem = what's wrong (one or two sentences, no filler), Evidence = the concrete trigger scenario, Impact = what breaks and for whom, Fix = the minimal code change — don't rewrite the function. Name the checklist category in the finding body.

With the `inline` modifier (or for a quick conversational review), present the same per-bug structure in the response instead, ordered Critical first.

## What this review is NOT

- Not a style review. No formatting, naming conventions, or "I'd do it differently".
- Not a feature review. No additions, improvements, or refactors.
- Not a test review. Don't say "this needs more tests" — say what's broken. Auditing the test suite itself is `/nitpicker tests`.
- Not a compliment sandwich. There is no sandwich. There is only bugs.
