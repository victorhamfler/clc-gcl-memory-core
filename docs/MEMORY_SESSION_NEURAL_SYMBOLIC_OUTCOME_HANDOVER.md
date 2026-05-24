# Memory Session Neural-Symbolic Outcome Handover

Date: 2026-05-24

## Purpose

Implemented the memory-side outcome capture requested by `MEMORY_SESSION_NEURAL_SYMBOLIC_ROADMAP_HANDOVER.md`.

This step does not promote learned behavior, mutate runtime selector config, or change selector-owned candidate miners. It adds richer memory-program logging for future neural-symbolic learning:

- answer-level feedback labels linked to `ask` operation ids
- log-only answer feedback, separate from memory-row feedback
- OGCF metadata propagation into memory API selector snapshots and selector explanations
- a Hermes-style holdout workflow that emits reusable candidate artifacts

## Files Changed

- `serve.py`
  - Added answer-level feedback labels:
    - `answer_correct`
    - `answer_stale`
    - `answer_wrong_scope`
    - `answer_missing_support`
    - `answer_overconfident`
    - `answer_good_citation`
    - `answer_bad_citation`
    - `answer_conflict_not_disclosed`
    - `answer_bridge_warning_useful`
    - `answer_bridge_warning_noise`
  - `POST /feedback` now supports:
    - memory-level feedback with `memory_id` as before
    - answer-level feedback with `feedback_scope: "answer"` or `answer_*` labels and a linked `operation_id`
  - Answer-level feedback is outcome-log-only and does not call `add_retrieval_feedback`.
  - `ask` selector snapshots now apply non-empty `ogcf_meta` through `augment_selector_features(...)`.
  - `selector_explain` context also carries OGCF-augmented diagnostics when `ogcf_meta` is provided.

- `eval/neural_symbolic_outcome_holdout_workflow.py`
  - New regression/workflow for answer-level labels and non-empty OGCF bridge diagnostics.
  - Creates a small Hermes-like namespace, runs three ask cases, records answer feedback, records one compatibility memory-level OGCF feedback event, and writes holdout artifacts.

## Generated Artifacts

- `C:\Users\victo\Desktop\projcod2\experiments\neural_symbolic_outcome_holdout_workflow_results.json`
- `C:\Users\victo\Desktop\projcod2\experiments\neural_symbolic_outcome_holdout_workflow_report.md`
- `C:\Users\victo\Desktop\projcod2\experiments\neural_symbolic_outcome_holdout_workflow.jsonl`
- `C:\Users\victo\Desktop\projcod2\experiments\neural_symbolic_holdout_candidates.json`
- `C:\Users\victo\Desktop\projcod2\experiments\neural_symbolic_holdout_candidates.md`

Holdout candidate schema: `memory_neural_symbolic_holdout/v1`.

## Validation

Commands run from `C:\Users\victo\Desktop\projcod2\clc_gcl_memory_core`:

- `py -3 -m py_compile serve.py eval\neural_symbolic_outcome_holdout_workflow.py`
- `py -3 eval\neural_symbolic_outcome_holdout_workflow.py`
- `py -3 eval\outcome_logging_regression.py`
- `py -3 eval\ogcf_intent_outcome_workflow.py`
- `py -3 eval\canonical_ogcf_policy_distribution_regression.py`
- `py -3 eval\selector_architecture_gate.py`

All passed.

New workflow summary:

- Ask events: 3
- Feedback events: 4
- Answer-level feedback events: 3
- Memory-level feedback events: 1
- Holdout candidates: 3
- OGCF bridge diagnostics non-empty: true
- Answer feedback avoided retrieval-feedback DB mutation: true

Sample non-empty OGCF diagnostics from the bridge case:

```json
{
  "ogcf_bridge_overload_score": 0.94,
  "ogcf_max_interaction_z": 2.82,
  "ogcf_loop_count": 9,
  "ogcf_cluster_count": 1,
  "ogcf_effective_affected_memory_ratio": 1.0
}
```

## Runtime Mutation Notes

No new runtime DB mutation was introduced for answer-level feedback.

The existing memory-level retrieval feedback path is unchanged. The new workflow intentionally records one memory-level `ogcf_geometry` feedback event to verify backward compatibility; the three answer-level feedback events are log-only.

No runtime selector config or learned policy artifact was promoted.

## Coordination Notes For Selector Session

The memory program can now produce answer-level labeled outcome logs with selected answer text, selected memory ids, raw/reranked evidence fields, canonical fields, and OGCF selector diagnostics. These logs are suitable as upstream data for a future learned selector/controller, but this session did not implement the learner or promotion gate.

Suggested next selector-side use:

- Read `neural_symbolic_outcome_holdout_workflow.jsonl`.
- Treat answer feedback labels as response-quality supervision, not memory-row supervision.
- Use `ogcf_*` diagnostics in bridge-risk samples only when `ogcf_meta_present` is true.
- Keep promotion gated by existing selector-owned readiness checks.
