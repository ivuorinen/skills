# NitpickerBench — seeded defect corpus

Each directory under `corpus/` is a miniature repository containing exactly one
deliberately planted defect, plus an `expected.json` naming where that defect is
and which lens owns it.

The corpus answers two different questions, and only the first is gated here:

| Question | Scored by | Gated by `make check` | Needs a model |
| --- | --- | --- | --- |
| Did retrieval surface the defect's location at all? | `scripts/bench-retrieval.py` (`make bench`) | Yes | No |
| Did the lens recognise the defect once it saw it? | `scripts/bench-recall.py` (`make bench-recall`) | No | Yes |

**Retrieval is scored first because it is the half that can fail silently.** A
lens that never receives the defect's lines cannot report it, and the resulting
clean run is indistinguishable from a repository with no defect. That failure
mode is invisible to every other gate in this repo, it is deterministic, and it
is exactly what a context-reduction change puts at risk — so it is measured on
every commit, without credentials and without a model.

Model recall needs an agent per case: minutes of wall clock, API credentials,
and a nondeterministic verdict. It does not belong in `make check` and must stay
out — a gate that grades differently twice on the same input is one people learn
to re-run until it passes. Run `make bench-recall` by hand, or from a scheduled
job, when a lens or a command file changes.

`bench-recall.py` splits along that line deliberately:

- `--grade <dir>` scores case directories an agent has already audited. Pure,
  deterministic, and covered by `tests/test_bench_recall.py` — no agent needed.
- `--run` invokes an agent per case and then grades what it filed. This is the
  half that cannot be tested here.

A lens is credited only when it filed a finding whose recorded `location`
overlaps the expected range. Filing *something* is not recognition, and crediting
it would make this a participation prize.

## Case layout

```text
corpus/<case-id>/
├── expected.json
└── <the repository tree>
```

`expected.json`:

```json
{
  "id": "python-command-injection",
  "lens": "security",
  "class": "command-injection",
  "severity_floor": "high",
  "goal": "subprocess shell command injection user input",
  "file": "src/run.py",
  "lines": [11, 14],
  "note": "shell=True on a string built from an argv value"
}
```

- `goal` is the query a lens would realistically issue for its own defect class.
  It is written from the *class*, never from the planted line — a goal quoting
  the answer measures nothing. `scripts/bench-retrieval.py` refuses a goal whose
  terms appear only inside the expected range, which is the guard against that.
- `lines` is the smallest range that proves the defect. A retrieved candidate
  counts as a hit when it overlaps this range.
- `severity_floor` is the lowest severity that counts as recognising the
  defect. `bench-recall.py` asserts at-or-above, so filing higher is not a miss;
  the retrieval harness ignores the field entirely.
- `class` supplies the tokens for `bench-recall.py`'s class signal, which is
  reported and never gated — a lens that found the right lines at the right
  severity has done the job whatever vocabulary it chose.

## Adding a case

1. Create `corpus/<case-id>/` with the smallest tree that makes the defect real.
   Distractors are welcome and are the point of the `adversarial-*` cases: code
   that shares the defect's vocabulary without being the defect.
2. Write `expected.json`.
3. Run `python3 scripts/bench-retrieval.py --case <case-id> -v` and read the
   rank. A case that scores a perfect 1.0 with no distractors is not testing
   retrieval, it is testing `grep`.
4. `make bench` must still pass.
5. Optionally `python3 scripts/bench-recall.py --run --case <case-id>` to see
   whether a lens actually reports it. Not required to land a case: retrieval is
   what gates.

## Known ceiling

Every case here is small. Real repositories are not, and rank degrades with
corpus size in ways a 6-file tree cannot show. The `adversarial-*` cases exist to
push back on that by burying the defect among near-miss code, but they are a
proxy. Treat a passing run as "retrieval did not regress", never as "retrieval
is good".
