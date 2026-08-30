# Counts in Prose

Documentation here states facts about sets that grow: MCP tools, bundled
modules, defect classes, version manifests. A count spelled out in prose is a
copy of something the code already holds, and the copy goes stale the next time
the set changes — silently, because no gate reads English.

## The rule

A number stays in prose only when one of these holds:

- **It is structural.** The number cannot change without redesigning the thing
  it describes: "one file per open finding", "two script classes", "one command
  per invocation". These state shape, not a tally.
- **A gate pins it.** SKILL.md keeps "exposes 16 tools" because
  `test_skill_md_documents_every_tool_the_server_exposes` asserts it against
  `TOOLS` and fails the commit when it drifts.

Delete every other count and name the set instead.

| Instead of | Write |
| --- | --- |
| "All thirteen read tools carry `readOnlyHint: true`" | "Each read tool carries `readOnlyHint: true`" |
| "fourteen tools carry `false` — the eleven local read tools and all three mutate tools" | "Every other tool carries `false`" |
| "imports five modules once at startup" | "imports every shipped module it depends on; `_LOADED` is the authoritative list" |
| "the eight classes above `install-script`" | "each class listed above `install-script` in the table" |
| "Three operations have no MCP tool: `baseline`, `migrate`, `migrate-resolved`" | "These operations have no MCP tool: `baseline`, `migrate`, `migrate-resolved`" |

## Enumerations

An enumeration a reader needs — *which* modules, *which* operations — stays. It
is the content, not a tally. Keep the list, drop the number in front of it, and
keep the list in one place: a second copy is a second thing to update.

Where the authoritative list lives in code, name that symbol instead of
restating it — `_LOADED`, `TOOLS`, `VENDORED_SKILLS`, `SEVERITIES`. A reader
who follows the pointer gets the current answer; a reader who trusts a copy
gets whatever was true the day it was typed.

## Enforcement

Author discipline for counts themselves. No gate parses English number words,
which is the reason this rule exists: three separate count drifts shipped in a
single session, each one accurate when it was written.

The neighbouring drift *is* gated, and the split is worth knowing. A number is
prose, so nothing checks it. A **reference** has a referent on disk, so
`check-rules-anatomy.py` does check it, and fails or reports on four shapes of
the same rot: `stale_path` for a cited file that is gone, `dead_anchor` for a
link into a heading that was renamed, `stale_date` for a date left behind, and
`placeholder` for a slot nobody filled. Write a reference rather than a count
wherever both would say the same thing: only one of them can be checked.
