---
paths:
  - "skills/**/SKILL.md"
  - ".claude/skills/**/SKILL.md"
---

# Skill Official Best Practices

The normative format is the open Agent Skills specification:
<https://agentskills.io/specification>. Anthropic's authoring guide
(<https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices>)
adds the reserved-word and description-shape rules below, which are stricter
than the spec and still binding here.

`scripts/validate-skill.py` enforces every constraint in this file except "No
Time-Sensitive Content" and the capability-summary half of "Description Format",
which are author discipline caught in review. "File Reference Depth" is gated in
part: a shared `commands/_*.md` file must be named in SKILL.md, so it is never
reachable only through a command file. Depth beyond that — a chain inside
`references/` — is not gated.

## Frontmatter Fields

Only these six keys are defined by the spec:

| Field | Required | Constraint |
| --- | --- | --- |
| `name` | Yes | 1-64 chars, matches the parent directory |
| `description` | Yes | 1-1024 chars |
| `license` | No | License name, or the name of a bundled license file |
| `compatibility` | No | 1-500 chars; environment requirements only |
| `metadata` | No | Map of string keys to string values |
| `allowed-tools` | No | One space-separated string (experimental) |

A key outside that set is an **error**, matching the reference validator, which
rejects any unrecognised frontmatter key. Client-specific properties go under
`metadata` — that is what the spec designates it for. This applies to every
skill in the repo, internal dev skills included; there is no allowlist and no
exemption.

`disable-model-invocation` is the worked example. Claude Code reads it from the
**top level**, so moving it to `metadata:` makes it inert and the skill becomes
model-invocable. That behaviour change was accepted deliberately in exchange for
portability: a top-level client key makes the skill invalid in every
spec-conforming host, and these skills' descriptions are written tightly enough
that model invocation lands only on genuine requests. Keep the entry under
`metadata` as the record of intent:

```yaml
metadata:
  disable-model-invocation: "true"
```

Quote the value. The spec defines `metadata` as a map of string keys to string
**values**, so a bare `true` is a boolean, not a string.

## Cross-checking against the reference validator

`make spec-check` runs the Agent Skills reference implementation over every
skill in the repo; all of them pass. Three traps, each hit once already:

- The PyPI package is `skills-ref`, but the console script it installs is
  `agentskills`. The spec page still documents `skills-ref validate`, a command
  the current release does not provide — it exits 1 with no output, which reads
  exactly like a validation failure.
- The npm package named `skills-ref` is published by an unrelated author with
  no repository link. It is not the reference implementation. The authentic one
  is the PyPI package authored by `klazuka@anthropic.com`.
- Failures print to **stderr**, successes to stdout. Reading stdout alone shows
  a clean run while skills are failing, so merge stderr before judging.

A validator that is silent on everything proves nothing. Before trusting a
clean run, confirm it still rejects a known-bad skill — a name with consecutive
hyphens and a skill with a top-level client key both work as controls.

Declare `compatibility` when a skill needs a runtime, a system package, or
network access that a bare agent host lacks. Omit it otherwise; most skills
have no such requirement.

## Name Constraints

- Maximum 64 characters, minimum 1.
- Only lowercase letters, numbers, and hyphens.
- Never starts or ends with a hyphen.
- Never contains consecutive hyphens (`--`).
- Cannot contain reserved words: "anthropic" or "claude".

## Description Format

Description must include **both** a capability summary and trigger conditions:

```yaml
description: <Capability summary sentence>. Use when <trigger conditions>.
```

Good example:

```yaml
description: Generates descriptive commit messages by analyzing git diffs. Use when asked to write commit messages or review staged changes.
```

Bad (trigger-only, no capability context):

```yaml
description: Use when asked to write commit messages or review staged changes.
```

Bad (vague, no trigger):

```yaml
description: Helps with git.
```

Write the trigger clause imperatively and about user intent, not internal
mechanics. Name the contexts where the skill applies, including ones where the
user does not say the domain outright. The description is the only text an
agent reads before deciding to load the skill, so it carries the entire
triggering burden.

## Body Length

Keep the SKILL.md body under 500 lines **and** under 5000 tokens — the two
halves of the spec's instructions tier. The validator estimates tokens at four
characters each and warns past either bound. Past either bound, split content
into separate files using progressive disclosure (link from SKILL.md).

## File Reference Depth

All reference files must link directly from SKILL.md (one level deep).
Never chain references: SKILL.md → advanced.md → details.md is forbidden.

Gated in part: `validate-skill.py` errors when a `commands/_*.md` shared
reference is not named in SKILL.md, since such a file is reachable only as
SKILL.md → command → reference. Chains that do not pass through a shared
command reference stay author discipline.

State *when* to load each referenced file. "Read `references/api-errors.md`
when the API returns a non-200" tells the agent the trigger; "see references/
for details" does not, and the file goes unread.

## No Time-Sensitive Content

Do not embed specific dates, version numbers, or other time-sensitive data directly in skill instructions.
Use "current version", "latest release", or point to a file that contains the up-to-date value instead.

## Context Window Courtesy

The context window is a shared resource. Keep SKILL.md concise.
Verbose skills degrade every response in the same session.
Move large reference materials, API docs, and examples into separate files.

Write only what the agent lacks: project conventions, domain procedures,
non-obvious edge cases, the specific tools to reach for. Cut anything the agent
already handles correctly without the instruction.

## Evals

A skill carries its eval sets under `<skill-dir>/evals/`, validated by
`scripts/validate-evals.py` in `make check`:

- `evals.json` — output-quality cases, each with a realistic `prompt`, an
  `expected_output`, and at least one objectively gradable assertion
  (<https://agentskills.io/skill-creation/evaluating-skills>).
- `trigger-queries.json` — description trigger-accuracy queries labelled
  `should_trigger`, split into a fixed `train` and `validation` set
  (<https://agentskills.io/skill-creation/optimizing-descriptions>).

Revise a description against `train` failures only, and score each iteration by
its `validation` pass rate — tuning against the whole set overfits the wording
to those exact phrasings. Both splits carry positive and negative queries,
because a split holding one label measures only one of the two failure modes.
Negative queries are near-misses that share the skill's vocabulary; an
obviously-irrelevant negative tests nothing.
