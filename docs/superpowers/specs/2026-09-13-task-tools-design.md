# Task-tracking MCP tools — design

Approved 2026-09-13 (option 1 of three; the alternatives — a file-backed store
under the audited project, and mirroring Claude's built-in names verbatim —
were declined for the cost of a write path and for colliding with the
built-ins respectively).

## Purpose

`_conventions.md` tells every command to run its numbered process as a task
list: one tracker entry per step, closed before reporting. Claude Code provides
`TaskCreate`/`TaskUpdate`/`TaskGet`/`TaskList`/`TodoWrite` only on some models,
and Copilot, pi and other Agent Skills hosts provide nothing. The nitpicker MCP
server therefore ships the same five operations as `np_` tools, so the rule has
a tracker to satisfy on every harness that runs the server.

Reference for the shape: <https://code.claude.com/docs/en/agent-sdk/todo-tracking>.
Tool-definition shape: the MCP `2026-07-28` schema (`title`, `inputSchema`,
`outputSchema`, `annotations`; `structuredContent` beside the text block). The
server keeps negotiating `2025-06-18`; those fields are backward compatible.

## Store

One in-process dict, keyed by id, living as long as the server process — which
is the session, and a task list's lifetime. Ids are decimal strings assigned in
creation order, per process. No file is written, so no root confinement and no
gitignore concern arise. Two ceilings, accepted: the list is lost on server
restart, and the two registered servers (project scope, plugin scope) hold
separate lists.

## Tools

All arguments snake_case, matching every other `np_` tool. All
`openWorldHint: false`.

| Tool | Arguments | Result (`structuredContent`) | Annotations |
| --- | --- | --- | --- |
| `np_task_create` | `subject` (required), `description`, `active_form`, `metadata` (object) | `{"task": {"id", "subject"}}` | mutates, not destructive, not idempotent |
| `np_task_get` | `task_id` (required) | the full task | read-only |
| `np_task_list` | none | `{"tasks": [{"id", "subject", "status", "owner", "blocked_by"}]}` | read-only |
| `np_task_update` | `task_id` (required); `status` (`pending`, `in_progress`, `completed`, `deleted`), `subject`, `description`, `active_form`, `owner`, `metadata`, `add_blocks`, `add_blocked_by` (arrays of ids) | the updated task, or `{"task": {"id", "subject", "status": "deleted"}}` | mutates, destructive (`deleted` removes), not idempotent |
| `np_todo_write` | `todos` (required): array of `{content, status, active_form}` | `{"tasks": [...]}` as `np_task_list` | mutates, destructive (replaces the whole list), not idempotent — the list reads the same but the ids advance |

A task record: `id`, `subject`, `description`, `active_form`, `status`
(default `pending`), `owner`, `blocks`, `blocked_by`, `metadata`.

`np_todo_write` writes into the same store: each todo becomes a task with
`content` as its subject, so `np_task_list` reads it back. Unknown ids in
`task_id`, `add_blocks` or `add_blocked_by` are `isError` results naming the
id. `metadata` replaces the whole object on update. `status: "deleted"` removes
the task and strips its id from every other task's `blocks`/`blocked_by`.

## Validation and errors

The dispatch-boundary validator (`_validate`) covers every argument: the
schema declares the enums and array item types, and an `object` type for
`metadata`. The todo item schema is an array of flat objects, one level deeper
than the validator's previous ceiling of scalar `items`; the validator now
recurses into an object property that declares `properties`, so the item shape
is enforced at dispatch like every other argument, with the violation prefixed
by the item's position (`todos[0]: status must be one of …`).

## Tests

`tests/test_mcp_server.py`: round trip create → get → update → list; todo_write
replaces and reads back; delete strips references; unknown id is an error;
annotations and `outputSchema` published; `structuredContent` matches the text
block; ids are per-process and sequential.

## Docs

`SKILL.md` MCP table (a `Task tracking` row) and the pinned count; the
annotations paragraph names the new destructive and idempotent tools;
`_conventions.md`'s task-list rule names `np_task_create` first; `README.md`'s
MCP paragraph.
