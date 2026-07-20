# /nitpicker commits — Commit-Message Discipline Audit

Hostile audit of every commit message in a range against the diff it labels: assume every label lies until the hunks prove it — release automation (release-please, semantic-release) reads only the message, so a mislabeled commit silently mis-versions the release.

## When to use

- Auditing commit messages against their diffs before a release, to prove release-please computes the right version
- After a suspicious version bump — a major nobody intended, a shipped feature missing from the changelog
- Verifying a PR's commits or a squash-merge title against the full diff before merge
- When asked to "audit the commits", "check commit messages", or "verify conventional commits"

The extra instructions may name the range: an explicit `<base>..<head>` range, or a PR number (audit that PR's commits).

Out of scope: code defects inside the diffs route to `/nitpicker review`; CI/CD workflow defects, including the release workflow's own YAML, to `/nitpicker ci`; implementing PR review comments is `/nitpicker cr`.

## Process

1. **Determine the audit range.** A user-given range or PR wins (`<base>..<head>`, or the PR's commits via `gh pr view <n> --json commits`). Default: commits since the last release tag — `$(git describe --tags --abbrev=0)..HEAD`. No tag exists → the full branch history. Record the range and commit count. Every commit in range is examined — merge commits, squash merges, bot commits (renovate/dependabot), release commits — never a sample. A run with unexamined commits has verdict INCOMPLETE.
2. **Load the convention.** The project's own convention table is the standard, tried in order: CLAUDE.md, then CONTRIBUTING, then the release-please config's `changelog-sections` if defined (in `.release-please-config.json`). Absent all of those, Conventional Commits. Record the source in the run summary.
3. **Verify every commit: message vs diff.** For each commit read the full message (subject, body, footers) AND the full diff (`git show <sha>`). Judge the label only against the hunks — never from the message alone, never from the diff stat alone. Check every commit against every class in the defect classes table. Breaking is a defined test, not a judgment call: the diff removes or renames public surface (exported API, CLI flag, config key, output format, skill/plugin name) or changes documented behavior in a way an existing consumer observes as incompatible.
4. **Compute the version consequence.** Derive the bump release-please takes for the range as-labeled and as-corrected, per the loaded convention (default map: feat → minor, fix → patch, `!`/`BREAKING CHANGE:` footer → major, every other type → none). The divergence sets severity. Classify each finding's commit as pushed (reachable from any remote ref — `git for-each-ref --contains <sha> refs/remotes refs/tags`) or unpushed; the fix shape depends on it.
5. **File findings** via the store protocol in `_conventions.md`, using `--auditor commits` (category `conventions`). Each finding records the class, the SHA and quoted subject line, pushed yes/no, the contradicting hunks (file + hunk; for malformed-convention, the quoted malformed line), the version consequence (the bump release-please takes vs the bump the diff earns), and the exact fix — the corrected message for an unpushed commit, or the exact correction commit (`Release-As:` footer or corrected-type restatement) for pushed history.
6. **Summarize and fix.** The summary states the run verdict (COMPLETE only if every commit in range was examined), the range, the convention source, and the version consequence as-labeled vs corrected. Fix application and the commit gate follow `_conventions.md`, with this override: the (s)afe option amends unpushed commits only and proposes pushed-history corrections without creating them. After each fix, recompute the version consequence for the range. Amendments and correction commits are created only per the approval — never silently.

### Defect classes

| Class | What to flag | Fix shape |
| --- | --- | --- |
| **type-understatement** | A no-bump type (`chore:`, `docs:`, `refactor:`, `test:`, `ci:`) whose diff adds or changes user-facing behavior — a new feature, a bug fix, a shipped-surface change | Relabel `feat:`/`fix:`; pushed → empty correction commit restating the change under its earned type |
| **type-overstatement** | A `feat:` whose diff is a pure fix, refactor, or internal change; a `fix:` on a diff with no behavior change | Relabel to the type the diff earns |
| **unmarked-breaking** | The diff removes or renames public surface, or changes behavior incompatibly, with no `!` and no `BREAKING CHANGE:` footer | Add the `!`/footer; pushed → correction commit carrying the `BREAKING CHANGE:` footer |
| **spurious-breaking** | A `!` or `BREAKING CHANGE:` footer on a diff with no consumer-visible break (e.g. a bot's `chore(deps)!:` on an internal CI action bump) | Drop the marker; pushed → `Release-As: X.Y.Z` correction commit pinning the correct next version |
| **scope-lie** | A squash-merge title describing only part of the diff — the title says docs, the hunks also change code | Retitle to cover the whole diff; pushed → correction commit naming the omitted change under its earned type |
| **malformed-convention** | A type not in the project's convention table, a missing `: ` separator, or a footer not in the `BREAKING CHANGE: <desc>` form release-please parses | Rewrite the message into the convention shape |

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | A wrong major or minor release would ship, or a breaking change would ship unmarked: spurious-breaking forcing a bogus major; unmarked-breaking riding out as minor or patch; the net as-labeled bump diverging from the corrected bump at major level |
| High | The net bump diverges at minor or patch level: type-understatement suppressing a due release (the feature or fix ships unreleased); type-overstatement forcing an undue release |
| Medium | The label is wrong but the net bump is unchanged (another commit in range already earns it) — the changelog misfiles the entry; malformed-convention hiding a commit from release-please without changing the bump |
| Low | A scope-lie or format defect whose only consequence is changelog wording; malformed scope syntax on a no-bump commit |
| Advisory | Message hygiene (tense, casing, body detail) with no version or changelog consequence |

## Fix strategy

**Auto-applicable:**

- Amend the message of an unpushed HEAD commit (`git commit --amend -m` with the corrected message)
- Reword a deeper unpushed commit (show old → new message per commit before applying)
- Rewrite a not-yet-merged squash-merge PR title to cover the whole diff

**Requires explicit approval per change:**

- Creating the empty correction commit for pushed history — `git commit --allow-empty` with a `Release-As: X.Y.Z` footer, or restating the mislabeled change under its earned type or `BREAKING CHANGE:` footer
- Any correction touching a commit already inside a tagged release (the correction shifts the next release, not the shipped one)

**Never auto-apply:**

- Rewriting pushed history — no amend, rebase, or force-push on any commit reachable from a remote ref, ever
- Changing code to make the diff match the message — code defects route to `/nitpicker review`

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

**"The message says chore, so it's a chore."** The message is the thing on trial; it is not evidence for itself. Only the diff testifies. Read every hunk before accepting any label.

**"Bot commits are auto-generated — skip them."** Bots mislabel too: a Renovate `chore(deps)!:` on an internal CI action bump reads to release-please as a breaking change and forces a spurious major. Bot commits get the same message-vs-diff verification as human commits.

**"The diff is huge, I'll trust the title."** Big diffs are where scope-lies live — the squash title describes the headline change and the hunks smuggle in three more. Size raises scrutiny; it never lowers it.

**"Checking every commit since the tag is too many — merge commits are enough."** release-please reads every commit in the range, not just merges. Every commit is examined; a sampled run has verdict INCOMPLETE and says so — it never presents a subset as complete.

**"It's already pushed, so nothing can be done."** Pushed history is never rewritten — and it is always correctable: an empty follow-up commit with a `Release-As:` footer or the corrected type/footer restates the truth for release-please. "Pushed" changes the fix shape, never the finding.

**"Breaking is subjective, I won't flag it."** Breaking is the defined test in step 3: removed or renamed public surface, or a behavior change an existing consumer observes as incompatible. Apply the test and file the result; discomfort is not a severity.

**"commitlint passed, so the messages are fine."** Format linters check shape, not truth. A perfectly-formed `chore:` on a feature diff passes every linter and still ships the feature unreleased. Shape checks replace nothing; the message-vs-diff comparison is the audit.

**"The net bump is right anyway, so the label doesn't matter."** The net bump sets severity, not validity. A mislabeled commit still misfiles the changelog entry and misleads every future reader of the history; file it at the severity the net consequence earns.

**"A quick force-push fixes the pushed commit."** Never. Rewriting pushed history breaks every checkout, PR, and tag that references it. The pushed-history fix is a documented correction commit, proposed to the user — nothing else.

**"I described the correction, so the finding is handled."** A described fix is an open finding. It is resolved only after the amendment or correction commit exists and the recomputed version consequence for the range confirms the bump is right.
