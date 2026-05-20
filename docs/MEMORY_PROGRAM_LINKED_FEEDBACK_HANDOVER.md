# Memory Program Linked Feedback Handover

Date: 2026-05-20

This handover is for the separate memory-program development session. The selector session has added a dry-run parser for the new outcome log, but the current live log does not yet contain linked feedback examples. The next useful step belongs to the memory-program session: collect a small real linked-feedback batch.

## Boundary

Keep ownership separated:

- Memory-program session owns the outcome logging layer and API behavior.
- Selector session owns selector training, selector parsing, and selector evals.
- Coordinate before pushing to GitHub.

Do not merge selector-training changes into the memory program directly. Generate outcome logs and hand them back to the selector session for analysis.

## Goal

Produce a small `logs/memory_outcomes.jsonl` sample containing real ask/feedback pairs where feedback is linked to the exact ask operation.

The selector session will then run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_outcome_log_training_eval.py
```

and inspect:

- eligible training candidates
- rejected feedback rows
- conflicting feature signatures

## What To Test

Run a small batch of about 10-20 real memory-program asks. Mix easy and hard cases:

- clean factual asks
- direct corrections
- deep correction chains
- near-topic distractors
- unrelated stale clutter
- multi-turn follow-up questions

For each answer, send feedback linked to the `/ask` operation id.

## Required Feedback Linking

`POST /ask` should return:

```json
{
  "operation_id": "op_...",
  "outcome_log_logged": true
}
```

When sending feedback, pass that operation id back as either `operation_id` or `linked_operation_id`:

```json
{
  "memory_id": "mem_...",
  "label": "useful",
  "rating": 1.0,
  "query": "same user query",
  "operation_id": "op_...",
  "rank": 1,
  "retrieval_score": 0.72,
  "notes": "answer was correct and evidence was relevant"
}
```

Negative examples are also important:

```json
{
  "memory_id": "mem_...",
  "label": "wrong",
  "rating": -1.0,
  "query": "same user query",
  "operation_id": "op_...",
  "rank": 1,
  "retrieval_score": 0.61,
  "notes": "answer used a near-topic but wrong correction"
}
```

Useful labels:

- Positive: `useful`, `correct`, `helpful`, `good`, `accepted`
- Negative: `wrong`, `incorrect`, `incomplete`, `stale`, `bad`

## Expected Log Content

The output file should be:

```text
logs/memory_outcomes.jsonl
```

It should contain:

- `ask` events with selector snapshots
- `feedback` events with `linked_operation_id`
- optionally `selector_explain` events

Each linked feedback event should point to the `operation_id` of an earlier `ask` event.

## Regression To Run In Memory-Program Session

Run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
```

Expected:

```text
ok: true
```

The regression should write exactly:

- `ask`
- `selector_explain`
- `feedback`

and confirm the feedback event links to the ask operation.

## What To Hand Back To Selector Session

After collecting the batch, write a short note with:

- path to `logs/memory_outcomes.jsonl`
- number of ask events
- number of feedback events
- number of linked feedback events
- any cases that looked questionable
- whether `outcome_logging_regression.py` passed

Do not edit selector training files from the memory-program session.

## GitHub Coordination Plan

Recommended upload order:

1. Memory-program session commits/pushes the outcome-log layer first:
   - `core/outcome_log.py`
   - `serve.py`
   - `storage/db.py`
   - `config.yaml`
   - `README.md`
   - `docs/AGENT_USER_MANUAL.md`
   - `docs/SELECTOR_OUTCOME_LOG_HANDOVER.md`
   - `eval/outcome_logging_regression.py`

2. Selector session pulls/updates after that.

3. Selector session commits/pushes selector-side parser/eval files:
   - `eval/selector_outcome_log_training_eval.py`
   - `eval/selector_outcome_log_candidate_regression.py`

This avoids mixing ownership and keeps the Git history clear.

## Current Selector-Side Status

The selector-side parser has already been tested locally:

- `selector_outcome_log_training_eval.py`: passes on the current live log
- `selector_outcome_log_candidate_regression.py`: passes with fixture data
- conflict blocking works
- orphan feedback rejection works

The selector session is waiting for real linked feedback rows before creating any real training candidates.
