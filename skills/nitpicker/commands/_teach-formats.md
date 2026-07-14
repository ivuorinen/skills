# Teaching workspace formats — shared reference for `/nitpicker teach`

Formats for the three markdown artifacts the `teach` command writes into
`docs/lessons/`. Lessons, reference documents, and assets are HTML and have no
fixed template — their rules live in `teach.md`.

## `MISSION.md` format

`MISSION.md` lives at `docs/lessons/MISSION.md`. It captures the _reason_ the
user is learning this topic. Every teaching decision — what to teach next,
which resources to surface, which exercises to design — traces back to it.

```md
# Mission: <Topic>

## Why
<1–3 sentences. The concrete real-world goal the user is chasing. What changes
in their life or work when they have this skill? Reject abstract framings like
"to understand X" — push for the underlying outcome.>

## Success looks like
- <A specific, observable thing the user will be able to do>
- <Another specific thing>

## Constraints
- <Time, budget, prior commitments, learning preferences — anything that bounds
  the approach>

## Out of scope
- <Adjacent topics the user explicitly does not want to chase now — protects the
  zone of proximal development>
```

Rules:

- **One mission per workspace.** Two unrelated goals are two workspaces.
- **Concrete over abstract.** "Run a half marathon by October" beats "get
  fitter." "Ship a Rust CLI to my team" beats "learn Rust."
- **Push back on vagueness.** If the user cannot say why, interview them before
  writing anything. A bad mission is worse than no mission.
- **Revise when reality shifts.** When the goal moves, update this file — never
  leave a stale mission steering future sessions.
- **Keep it short.** Past one screen it has stopped being a compass and become a
  plan.

## `RESOURCES.md` format

`RESOURCES.md` lives at `docs/lessons/RESOURCES.md`. It is the curated set of
trusted sources. Draw knowledge from here, not from parametric guesses; wisdom
comes from the communities listed here.

```md
# <Topic> Resources

## Knowledge
- [Book: _The Science and Practice of Strength Training_ — Zatsiorsky & Kraemer](https://example.com)
  Foundational text on programming and adaptation. Use for: periodisation,
  recovery, intensity zones.
- [Article: "How Much Should I Train?" — Greg Nuckols](https://example.com)
  Evidence-based review of volume landmarks. Use for: weekly set targets.

## Wisdom (Communities)
- [r/weightroom](https://reddit.com/r/weightroom)
  High-signal, moderated against bro-science. Use for: programme critique,
  plateau troubleshooting.
- Local: Tuesday strength class at <gym name>
  Use for: real-time coaching feedback on lifts.
```

Rules:

- **High-trust only.** Prefer primary sources, recognised experts, peer-reviewed
  work, and communities with strong moderation. Leave out marketing dressed as
  education.
- **Annotate every entry.** A bare link is useless in three months. Add one
  line: what it covers and when to reach for it.
- **Group by Knowledge / Wisdom.** A resource may appear in only one group.
- **Surface gaps explicitly.** When no good resource exists for an area the
  mission needs, add a `## Gaps` section listing what is missing. This drives
  future search.
- **Prune ruinously.** Remove a source that turned out wrong, shallow, or
  off-mission — never bury it. Five sharp sources beat thirty mediocre ones.
- **Record community preferences.** If the user opted out of joining
  communities, note it here so future sessions stop proposing them.

## Learning record format

Learning records live in `docs/lessons/learning-records/` and use sequential
numbering: `0001-slug.md`, `0002-slug.md`. Create the directory lazily — only
when the first record is written. They are the teaching equivalent of ADRs:
they capture non-obvious lessons, key insights, and stated prior knowledge that
steer future sessions, and they drive the zone-of-proximal-development
calculation.

```md
# <Short title of what was learned or established>

<1–3 sentences: what was learned (or what prior knowledge was established), and
why it matters for future sessions.>
```

That is the whole format. A learning record can be one paragraph. The value is
recording _that_ this is now known and _why_ it changes what to teach next.

Optional sections — include only when they add genuine value:

- **Status** — a plain Markdown line, not YAML frontmatter (`Status: active` or
  `Status: superseded by <NNNN>`, where `<NNNN>` is the filename number of the
  superseding record) — when an earlier understanding turns out wrong and is
  replaced.
- **Evidence** — how the user demonstrated the understanding. Useful when the
  claim may be revisited.
- **Implications** — what this unlocks or rules out for future sessions.

Write a learning record when any of these holds:

1. **The user demonstrated genuine understanding of something non-trivial** —
   evidence they can use the concept correctly, not mere exposure. This sets a
   new floor for what to teach next.
2. **The user disclosed prior knowledge** — "I already know X." Record it, and
   the depth claimed, so future sessions do not re-teach it.
3. **A misconception was corrected** — high-value: it predicts future stumbling
   blocks for related topics.
4. **The mission shifted in response to learning** — cross-link to `MISSION.md`
   and update it.

Do _not_ write one for material merely covered (coverage is not learning), for
a term already defined in the glossary, or as a session activity log — records
are decision-grade insights, not a journal.

Numbering: scan `learning-records/` for the highest existing number and
increment by one. When a later record contradicts an earlier one, mark the old
record `Status: superseded by <NNNN>` (the superseding record's filename number)
rather than deleting it — the history of how understanding evolved is itself
useful signal.
