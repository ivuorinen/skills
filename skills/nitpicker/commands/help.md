# /nitpicker help — Command Reference

Prints the categorized command listing. Writes nothing, audits nothing.

## When to use

"/nitpicker help", "/nitpicker list", "what nitpicker commands are there".

Print the command listing from SKILL.md (the `## Commands` section — all
category tables, not the `## Internal commands` section) verbatim, followed
by usage:

```text
/nitpicker [command] [extra instructions]

No command        → full repository audit (audit)
inline            → findings in the response only, nothing written
changed-files     → limit scope to modified files + direct dependencies
release-gate [th] → fail if open findings at/above threshold (default High)
```

Then stop. Run nothing else.
