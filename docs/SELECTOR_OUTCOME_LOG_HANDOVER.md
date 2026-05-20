# Selector Outcome Log Handover

Date: 2026-05-20

This note is for the separate selector-module development session. The memory-program session added an append-only outcome log so real agent memory use can become selector training material without changing selector code here.

## Boundary

The memory program owns this logging layer. Selector algorithm changes should stay in the selector session.

If the selector session needs additional fields, request them through a handover note rather than editing memory-program behavior directly.

## Log Location

Default path:

```text
logs/memory_outcomes.jsonl
```

Config:

```yaml
outcome_log:
  enabled: true
  path: logs/memory_outcomes.jsonl
  max_text_chars: 600
  max_list_items: 20
```

## Event Schema

Each line is one JSON object:

```json
{
  "schema_version": 1,
  "operation_id": "op_...",
  "linked_operation_id": null,
  "event_type": "ask|selector_explain|feedback",
  "created_at": "ISO-8601 UTC timestamp",
  "payload": {}
}
```

## Logged Events

`ask`

- request query, namespace, top_k, agent_id, session_id, condition_name
- answer, confidence, conflict, namespace warning
- compact evidence, raw results, source context, stale context
- selector snapshot derived from the ask raw results:
  - selected policy/action/reason/confidence
  - retrieval diagnostics

`selector_explain`

- request query/namespace/condition/top_k
- selector config
- explanation and decision
- retrieval diagnostics and compact retrieval context when a query or retrieval_context was supplied

`feedback`

- feedback label/rating/query/memory_id
- `linked_operation_id` when the caller supplies an `operation_id`, `linked_operation_id`, or `outcome_id`
- persisted feedback metadata includes `linked_operation_id`

## Why This Matters For Selector Training

The selector can now learn from real memory operations rather than only generated harness rows. A useful training row can connect:

- what the agent asked,
- what evidence retrieval produced,
- what selector policy was recommended,
- what answer was returned,
- whether feedback later marked the answer/evidence useful, stale, wrong, or incomplete.

## Suggested Selector-Session Use

1. Build a parser for `logs/memory_outcomes.jsonl`.
2. Group rows by `operation_id` and feedback rows by `linked_operation_id`.
3. Convert `ask.payload.selector_snapshot.diagnostics` into selector features.
4. Use feedback labels to create candidate outcome labels.
5. Keep the existing guarded trainer rule: never admit conflicting feature signatures unless a guard suite proves they are safe.

## Memory-Program Regression

Run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
```

Expected result: `ok: true`, with exactly `ask`, `selector_explain`, and `feedback` events written to a temporary JSONL file.
