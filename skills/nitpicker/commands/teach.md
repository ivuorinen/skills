# /nitpicker teach — Teach a Skill or Concept

Teach the user a skill or concept inside a persistent teaching workspace. This is a stateful, multi-session request: the user intends to learn the topic over time, and each run builds on the last. The topic is the text after the command (`/nitpicker teach rust ownership`); with no topic, read the existing workspace and continue from the user's zone of proximal development; with no topic and no workspace yet, interview for a mission and start a new course.

## When to use

- "teach me X", "help me learn X", "I want to get good at X over time"
- "explain X so it actually sticks", "build me a course on X"
- Continuing an existing course: "next lesson", "what should I learn next", or `/nitpicker teach` with no topic
- Any request to acquire a skill or body of knowledge across more than one sitting, where retention — not a one-off answer — is the goal

Not for a single throwaway explanation the user will not revisit — answer that directly. Not for auditing or reviewing code: that is `/nitpicker review` or `/nitpicker audit`.

## Not an audit — what this command produces

This command teaches; it does not hunt defects. It writes a teaching workspace under `docs/lessons/`, not findings. The entire `_conventions.md` **Findings store** section is overridden — the findings store, `findings.py`, the severity table, the `Apply fixes?` prompt, and Run-protocol step 0 (the legacy `docs/audit/*-findings.md` migration-consent gate) all bind the audit commands and never fire for `teach`. The `inline` and `changed-files` modifiers do not apply either: the persistent workspace under `docs/lessons/` is always the deliverable, never a response-only or scoped-down answer. Only two `_conventions.md` execution rules carry over: run the Process below as a task list (one tracker entry per step), and preflight every external tool with `command -v` before invoking it.

Never trust your parametric knowledge as the source of truth. Ground every claim in a resource the user can verify, and cite it. Knowledge you "know cold" is exactly the trap: settled, stable, unchanged-for-years facts still get a citation, because the citation — not your confidence — is what the user verifies and returns to. Fetching and citing sources is never over-engineering here; it is the command's core. When no source can be fetched (no network or fetch capability in the environment), tell the user sourcing is unavailable and either defer the lesson or record the gap under `## Gaps` in `RESOURCES.md` — never silently fall back to teaching from memory.

## The teaching workspace

The workspace is `docs/lessons/` in the current repository. Create it lazily — only the parts a session actually needs. Its state:

- `docs/lessons/MISSION.md` — the _reason_ the user is learning this. Grounds every teaching decision. Format in `_teach-formats.md`.
- `docs/lessons/RESOURCES.md` — the curated set of trusted sources (knowledge) and communities (wisdom). Format in `_teach-formats.md`.
- `docs/lessons/lessons/NNNN-<slug>.html` — the lessons themselves. A **lesson** is one self-contained HTML file that teaches a single tightly-scoped thing tied to the mission. This is the primary unit of teaching.
- `docs/lessons/reference/*.html` — compressed reference material: cheat sheets, algorithms, syntax cards, pose sequences, glossaries. Beautiful documents that print well and are built for quick lookup.
- `docs/lessons/learning-records/NNNN-<slug>.md` — records of what the user has learned. The teaching equivalent of ADRs; they drive the zone-of-proximal-development calculation. Format in `_teach-formats.md`.
- `docs/lessons/assets/*` — reusable **components** shared across lessons (stylesheets, quiz widgets, simulators, diagram helpers).
- `docs/lessons/NOTES.md` — a scratchpad for user preferences and working notes.

`NNNN` is a zero-padded sequence (`0001`, `0002`, …); scan the directory for the highest existing number and increment.

## Philosophy

Deep learning needs three things:

- **Knowledge** — captured from high-quality, high-trust resources.
- **Skills** — acquired through highly relevant interactive lessons you devise from that knowledge.
- **Wisdom** — earned by testing skills against other practitioners in the real world.

Before `RESOURCES.md` is well populated, find high-quality resources first; knowledge acquisition depends on them. Weight the mix to the topic: theoretical physics leans knowledge-heavy, yoga leans skills-heavy.

### Fluency vs storage strength

Split two kinds of learning:

- **Fluency strength** — in-the-moment retrieval.
- **Storage strength** — long-term retention. This is the real goal.

Fluency creates an illusion of mastery; storage strength is what lasts. Build storage strength through desirable difficulty:

- **Retrieval practice** — make the user recall from memory, not re-read.
- **Spacing** — distribute practice over sessions.
- **Interleaving** — mix related topics during skills practice.

## The mission

Every lesson ties into the mission — the real-world reason the user wants this skill. If `MISSION.md` is empty or the mission is unclear, interview the user before writing anything else: a bad mission is worse than none. Without a grounded mission, lessons drift abstract and you have no basis for choosing what to teach next.

Missions change as the user grows. When the goal shifts, confirm with the user, update `MISSION.md`, and write a learning record capturing the change.

## Zone of proximal development

Each lesson must challenge the user _just enough_. If the user names an exact thing to learn, teach that. Otherwise compute the next step:

1. Read the `learning-records/` to establish what is already known.
2. Weigh it against the mission.
3. Teach the most mission-relevant thing that fits inside the user's current reach.

## Lessons

A lesson is one self-contained HTML file in `docs/lessons/lessons/` (the nested `lessons/` subdirectory is intentional — it holds only lesson files, keeping them out of the workspace root), named `NNNN-<slug>.html`. Rules for every lesson:

- **Beautiful.** Clean typography and layout — the user returns to these to review. Think Tufte.
- **Short and completable fast.** Working memory is small; stay inside it. Each lesson delivers one tangible win the user builds on, tied directly to the mission and inside their zone of proximal development.
- **Cited.** Litter the lesson with links to the external resources backing each claim — citations raise trust.
- **Linked.** Cross-link via HTML anchors to related lessons and reference documents.
- **Sourced.** Recommend one primary source — the highest-quality resource found on the topic — for the user to read or watch.
- **Interactive follow-up.** End with a reminder that the user can ask you, their teacher, to clarify anything.

After writing a lesson, open it for the user with the platform's file-opener — `open` on macOS, `xdg-open` on Linux, `start` on Windows — when one is present (`command -v`).

## Assets

Lessons are built from reusable **components** in `docs/lessons/assets/`: stylesheets, quiz widgets, simulators, diagram helpers — anything a second lesson reuses.

Reuse is the default. Read `docs/lessons/assets/` before authoring a lesson and build from what already exists. When a lesson needs something new and reusable, write it as a component in `assets/` and link to it — never inline code a future lesson would duplicate. A shared stylesheet is the first component every workspace earns: every lesson links it, so the course reads as one consistent whole. Grow the component library as the workspace grows.

## Knowledge

Design each lesson around one skill the user will acquire, and include only the knowledge that skill requires. Teach the knowledge first, then drive practice through an interactive feedback loop. Draw knowledge from the trusted resources in `RESOURCES.md`, never from parametric guesses. For knowledge, difficulty is the enemy — it consumes the working memory understanding needs.

## Skills

Skills make knowledge durable and flexible. For skill acquisition, difficulty is the tool: effortful retrieval is what builds storage strength. Teach skills through interactive lessons:

- Quizzes and light in-browser tasks.
- Guided sequences of real-world steps to perform (for example, yoga poses).

Every skills lesson runs on a **feedback loop** — the tightest possible, giving feedback immediately and, where possible, automatically. For quizzes, make every answer option the same word count (and character count where possible), so formatting leaks no clue to the correct answer.

## Wisdom

Wisdom comes from real-world interaction beyond the learning environment. When a question needs wisdom, attempt an answer, then delegate to a **community** — a forum, subreddit, class, or local interest group where the user tests skills for real. Find high-reputation communities and propose them. If the user declines to join a community, respect it and record that preference in `RESOURCES.md`.

## Reference documents

Alongside lessons, build reference documents in `docs/lessons/reference/`. Lessons are rarely revisited; reference documents are. A reference document is the compressed essence of what a lesson taught, in a format built for fast lookup. Topics that reward reference material:

- Syntax and code snippets for programming.
- Algorithms and flowcharts for processes.
- Poses and sequences for yoga; exercises and routines for fitness.
- Glossaries for any topic with its own nomenclature.

A **glossary** is the essential reference: once created, adhere to its terms in every subsequent lesson.

## `NOTES.md`

When the user states a preference for how they want to be taught, or anything to keep in mind, record it in `docs/lessons/NOTES.md` and consult it when designing lessons.

## Process

Run these steps as a task list. Never skip a step; a step whose precondition is already satisfied — judged by that step's own guard below, not by a blanket "looks covered" — is closed immediately with a note in the tracker.

1. **Read the workspace.** Load `MISSION.md`, `RESOURCES.md`, `NOTES.md`, and the `learning-records/`. If `docs/lessons/` does not exist yet, treat this as a new course.
2. **Establish the mission.** If `MISSION.md` is empty or the mission is unclear, interview the user until you can write a concrete mission, then write `MISSION.md`.
3. **Populate resources.** If `RESOURCES.md` is thin for what the mission needs, search for high-trust sources and record them (annotated) before teaching. Record community preferences.
4. **Locate the zone of proximal development.** From the learning records and mission, choose the single most relevant next thing to teach — unless the user named an exact target.
5. **Teach.** Author the lesson as an HTML file in `lessons/`, reusing `assets/` components. Cite sources, cross-link, recommend one primary source, and close with the interactive follow-up reminder. Open it for the user with the platform file-opener when one is present.
6. **Capture reference material.** Write or update reference documents and the glossary for durable units of knowledge.
7. **Record learning.** When the user demonstrates genuine understanding, discloses prior knowledge, corrects a misconception, or shifts the mission, write a learning record (format in `_teach-formats.md`).
8. **Commit.** Ask "Commit the teaching workspace to git? (y/n)" — never commit silently.

## Common mistakes

- **Teaching before the mission is grounded.** An empty or vague `MISSION.md` makes every lesson abstract — interview the user first.
- **Teaching from parametric memory because the topic feels settled.** "I know this cold" is the rationalization that skips sourcing — settled knowledge still earns a cited resource in `RESOURCES.md`.
- **Collapsing the workspace into a chat answer or a single loose file** under deadline or a "don't over-engineer" nudge. The user invoked `teach`; the persistent `docs/lessons/` workspace is the deliverable, not gold-plating. Keep components lean — never drop the workspace.
- **Optimizing for fluency.** A lesson the user breezes through builds no storage strength — use retrieval, spacing, and interleaving even when it feels harder.
- **Lessons that overshoot the zone of proximal development.** Too hard eats working memory; too easy teaches nothing. Calibrate against the learning records.
- **Inlining reusable code into a single lesson** instead of extracting a component into `assets/`.
- **Quiz answers of unequal length** that leak the correct option through formatting.
- **Silently changing the mission.** Confirm with the user, update `MISSION.md`, and write a learning record.
