# Hermes Resolver-Shadow Validation Handover

Date: 2026-05-24

## Purpose

This handover tells Hermes how to validate the new answer-behavior resolver-shadow mode.

The goal is to test proposed answer-control actions during normal work without changing user-facing answer text. The selector/memory architecture is moving toward a neural-symbolic adaptive memory brain, where learned or mined behavior stays report-only until guarded by real logs and feedback.

## Current Architecture Checkpoint

The new selector-side answer behavior path is:

```text
answer feedback signals
-> answer feedback memory bank
-> guarded answer behavior proposals
-> controlled shadow eval
-> linked-log shadow replay
-> configurable resolver-shadow mode
```

The new runtime-adjacent module is:

```text
core/answer_behavior_shadow.py
```

It emits proposed actions beside the normal answer:

- `require_evidence_backed_answer`
- `emit_ogcf_bridge_warning`
- `preserve_missing_support_refusal`
- `disclose_stale_conflict`

It is report-only:

- `mutates_answer: false`
- `mutates_config: false`

## Important Runtime Behavior

The default config keeps the normal API unchanged:

```yaml
resolver_shadow:
  enabled: false
  include_in_outcome_log: false
  bridge_warning_score_threshold: 0.70
  bridge_warning_effective_ratio_threshold: 0.50
```

To request shadow diagnostics for one ask call, send:

```json
{
  "query": "your question",
  "top_k": 8,
  "namespace": "your-test-namespace",
  "include_global": false,
  "include_selector_snapshot": true,
  "include_resolver_shadow": true
}
```

Expected response addition:

```json
{
  "resolver_shadow": {
    "schema": "resolver_shadow_actions/v1",
    "report_only": true,
    "mutates_answer": false,
    "mutates_config": false,
    "actions": [],
    "reasons": [],
    "annotations": [],
    "diagnostics": {}
  }
}
```

Do not change user-facing resolver behavior yet.

## Pull And Setup

From the Hermes environment, pull the latest GitHub version:

```bash
cd <your clc_gcl_memory_core checkout>
git pull origin main
```

Use the existing project Python environment. On Windows in this repository we use:

```powershell
..\.venv-torch\Scripts\python.exe
```

On WSL, use the corresponding local environment path that Hermes already uses for this project.

## Required Local Validation Commands

Run these after pulling:

```bash
python eval/resolver_shadow_mode_regression.py
```

Expected:

```text
ok: true
case_count: 7
```

Generate the linked answer-feedback fixture:

```bash
python eval/answer_behavior_real_log_fixture.py
```

Run the full linked-log replay:

```bash
python eval/answer_behavior_real_log_shadow_replay.py \
  --log ../experiments/neural_symbolic_outcome_holdout_workflow.jsonl \
  --log ../experiments/answer_behavior_real_log_missing_cases.jsonl \
  --out-json ../experiments/answer_behavior_real_log_shadow_replay_full_coverage_results.json \
  --out-md ../experiments/answer_behavior_real_log_shadow_replay_full_coverage_report.md
```

Expected:

```text
ok: true
case_count: 8
passed_count: 8
```

Run the proposal and architecture guards:

```bash
python eval/answer_behavior_shadow_regression.py
python eval/answer_behavior_proposal_guard_regression.py
python eval/answer_feedback_bank_guard_regression.py
python eval/canonical_ogcf_policy_distribution_regression.py
```

All should pass.

## Live API Validation Task

Start the local server as Hermes normally does.

Then run a small live workflow with `include_resolver_shadow: true`.

Create or use a test namespace with at least these situations:

- supported answer with selected evidence;
- unsupported/private fact where no selected evidence should support the query;
- ordinary factual query containing a bridge-like word, such as a room or location named Bridge;
- OGCF bridge/geometry-style query with non-empty OGCF diagnostics when possible;
- stale/current correction pair where current evidence is selected but stale context is present.

For each ask response, record:

- query;
- answer;
- evidence memory ids;
- selector snapshot;
- resolver shadow actions;
- resolver shadow annotations;
- whether the normal answer changed unexpectedly;
- answer-level feedback label.

Use answer-level labels:

- `answer_correct`
- `answer_good_citation`
- `answer_bridge_warning_useful`
- `answer_bridge_warning_noise`
- `answer_missing_support`
- `answer_overconfident`
- `answer_stale`
- `answer_conflict_not_disclosed`
- `answer_bad_citation`
- `answer_wrong_scope`

When submitting answer-level feedback, link it to the ask `operation_id` and include selected memory ids:

```json
{
  "feedback_scope": "answer",
  "linked_operation_id": "<ask operation_id>",
  "label": "answer_correct",
  "rating": 1.0,
  "query": "<same query>",
  "selected_memory_ids": ["mem_..."],
  "answer": "<answer text>",
  "notes": "resolver-shadow validation"
}
```

## What To Measure

Create a report with:

- total ask cases;
- total answer feedback cases;
- action counts;
- false positive bridge warnings;
- missed useful bridge warnings;
- missed stale/conflict disclosures;
- missing-support cases where shadow failed to preserve refusal;
- supported-answer cases where shadow failed to require evidence;
- any case where the normal answer text changed because of shadow mode.

The last count should be zero.

## Expected Interpretation

This is not a promotion to user-facing resolver behavior.

If live validation passes, the next development step is a stronger resolver-shadow replay over Hermes natural logs. Only after that should the memory-program session consider config-gated user-facing answer annotations.

## Files To Inspect

- `core/answer_behavior_shadow.py`
- `serve.py`
- `config.yaml`
- `eval/resolver_shadow_mode_regression.py`
- `eval/answer_behavior_real_log_shadow_replay.py`
- `eval/answer_behavior_real_log_fixture.py`
- `docs/ANSWER_BEHAVIOR_SHADOW_EVAL_HANDOVER.md`
- `docs/ARCHITECTURE_RESTRUCTURE_ROADMAP.md`
- `docs/CLC_ARCHITECTURE_STATUS.md`

## Output Files To Return

Please write your final Hermes report to:

```text
../experiments/hermes_resolver_shadow_validation_report.md
../experiments/hermes_resolver_shadow_validation_results.json
```

Include all failed cases with query, answer, selected evidence ids, shadow actions, and feedback label.
