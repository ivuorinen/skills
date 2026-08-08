# Snapshot Before Mutating

A failing-capability proof breaks the code on purpose: revert the fix, confirm
the test goes red, restore. The restore step is where the work gets destroyed.

## Never restore with git

`git checkout -- <path>` and `git restore <path>` overwrite the working tree from
the **index**, not from the state before the mutation. Unstaged changes at that
path are discarded; staged ones survive, because the index is the source. Neither
reaches the object store first, so discarded unstaged content has no reflog entry
and no stash to recover from.

```console
$ printf 'COMMITTED\n' > f && git add f && git commit -qm init
$ printf 'STAGED\n' > f && git add f     # index
$ printf 'UNSTAGED\n' > f                # working tree
$ git restore f && cat f
STAGED
```

Reverting to the last commit is a different command — `git restore --source=HEAD
--staged --worktree <path>`. Both forms stay correct where discarding to their
own source is the actual intent. A proof's restore step means something narrower:
undo one mutation and leave everything else alone. Neither can express that.

The fix being proven is unstaged almost every time, because the proof runs
*before* the `git add`. So the restore deletes the fix. Worse than losing it: every
measurement after the first restore runs against an unfixed file, the mutation
still looks caught, and the proof reports green while proving nothing.

Both incidents in this repo were exactly that shape:

- A mutation-proof script whose `restore() { git checkout -- "$F"; }` wiped the
  uncommitted production fix it existed to validate.
- `git checkout -- renovate.json`, run to undo a one-line probe, discarded two
  unrelated uncommitted edits to the same file.

## Snapshot with cp, restore with cp, verify with cmp

```bash
cp scripts/hooks/thing.py /tmp/snap.orig      # before touching anything
# ...mutate, run the check, observe red...
cp /tmp/snap.orig scripts/hooks/thing.py      # restore
if ! cmp -s /tmp/snap.orig scripts/hooks/thing.py; then
  echo "RESTORE FAILED" >&2
  exit 1
fi
```

`cp` restores what was there. `cmp` proves it did — a restore that silently fails
leaves a mutated file in the tree and the next commit ships it.

The check exits non-zero. `cmp -s … || echo "RESTORE FAILED"` reads like a guard
and is not one: `echo` succeeds, so the line exits 0 and the proof stays green
with a mutated file on disk — the failure this section exists to catch, printed
and then ignored.

## Assert the baseline before mutating

A proof that starts from an already-red baseline demonstrates nothing: the test
was failing before the mutation and after it. Before mutating, assert both that
the check is green **and** that the fix under test is present in the file. A
proof that skips this reports the same green whether the fix is there or not.

## Enforcement

`scripts/hooks/ask-destructive-restore-hook.py` asks for confirmation when a
`git checkout --` or `git restore` would discard uncommitted tracked changes.
It covers one surface only: a Bash command the agent issues directly.

A `git checkout --` written *inside* a shell script is invisible to it. The hook
sees the command that runs the script, not the git call within it — and a
verification script is precisely where both incidents above happened. Nothing
gates that case. This rule is applied by the author.
