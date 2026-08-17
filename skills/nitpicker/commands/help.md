# /nitpicker help — Command Reference

Prints the categorized command listing. Writes nothing, audits nothing.

## When to use

"/nitpicker help", "/nitpicker list", "what nitpicker commands are there",
"/nitpicker help security and data" (one category).

Print the command listing from the router (`np_read_skill` with
`name: "nitpicker"`, else read SKILL.md directly) — the `## Commands` section,
all category tables, not the `## Internal commands` section — verbatim,
followed by usage:

```text
/nitpicker [command] [extra instructions]

No command        → full repository audit (audit)
inline            → findings in the response only, nothing written
changed-files     → limit scope to modified files + direct dependencies
release-gate [th] → fail if open findings at/above threshold (default High)
help [category]   → one category's table only (Review and fixing, Planning,
                    Learning, Security and data, Runtime behavior, Structure
                    and contracts, Quality surfaces, Coding-agent enforcement,
                    Meta)
```

When the extra instructions name a category, print that table only: pass the
text to `np_list_commands` as `category` (case, spaces, and hyphens are
interchangeable) and render its rows as the same `| Command | Purpose |` table
under the category heading; without the MCP tools, copy the matching `###`
section out of SKILL.md. Never invent a category: an unknown value makes the
tool error with the known set — print that set and the full listing instead of
guessing which group was meant. `Internal commands` is never printed, whether
named or not.

Then stop. Run nothing else.
