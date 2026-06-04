# Hermes Handover: OGCF/ERG Maintenance Lifecycle Validation

Date: 2026-06-04

## Purpose

Validate the newest selector/memory architecture update after pulling from GitHub.

This update adds a complete report-only maintenance lifecycle that connects OGCF/ERG geometry signals to memory-side review artifacts without mutating the database.

The lifecycle is:

```text
ERG geometry
-> dry-run maintenance candidates
-> priority-ranked review queue
-> review labels
-> multi-run review memory bank
-> guarded maintenance candidates
-> memory-side review plan
-> manual review outcomes
-> dry-run manual apply/reject decisions
```

Everything in this handover is report-only. Do not apply memory changes, deprecate rows, merge memories, update runtime config, or promote learned behavior from these tests.

## Required Pull

From the Hermes working clone:

```bash
git pull origin main
git rev-parse HEAD
```

Record the commit SHA in your report.

## New Files To Know

Core contract:

```text
core/maintenance_candidate_contract.py
```

Maintenance lifecycle tools:

```text
eval/ogcf_maintenance_review_queue.py
eval/ogcf_maintenance_review_label_eval.py
eval/ogcf_maintenance_review_label_loop_regression.py
eval/ogcf_maintenance_review_memory_bank.py
eval/ogcf_maintenance_review_memory_bank_regression.py
eval/ogcf_maintenance_candidate_guard.py
eval/ogcf_maintenance_candidate_guard_regression.py
eval/memory_maintenance_candidate_review_plan.py
eval/memory_maintenance_candidate_review_plan_regression.py
eval/memory_maintenance_review_outcome_log.py
eval/memory_maintenance_review_outcome_log_regression.py
eval/memory_maintenance_manual_apply_decisions.py
eval/memory_maintenance_manual_apply_decisions_regression.py
```

## Required Tests

Run from the repository root. If your environment uses `python3`, use `python3` instead of `python`.

```bash
python eval/ogcf_maintenance_review_label_loop_regression.py
python eval/ogcf_maintenance_review_memory_bank_regression.py
python eval/ogcf_maintenance_candidate_guard_regression.py
python eval/memory_maintenance_candidate_review_plan_regression.py
python eval/memory_maintenance_review_outcome_log_regression.py
python eval/memory_maintenance_manual_apply_decisions_regression.py
python eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 8
```

## Required Gate Checks

In `experiments/selector_architecture_gate_results.json`, confirm these are all `true`:

```text
ogcf_maintenance_review_label_loop_ok
ogcf_maintenance_review_memory_bank_ok
ogcf_maintenance_candidate_guard_ok
memory_maintenance_candidate_review_plan_ok
memory_maintenance_review_outcome_log_ok
memory_maintenance_manual_apply_decisions_ok
```

Also confirm the gate overall reports:

```text
ok: true
```

## Artifact Inspection

Inspect these generated artifacts under `experiments/`:

```text
ogcf_maintenance_review_label_loop_regression_results.json
ogcf_maintenance_review_memory_bank_regression_results.json
ogcf_maintenance_candidate_guard_regression_results.json
memory_maintenance_candidate_review_plan_regression_results.json
memory_maintenance_review_outcome_log_regression_results.json
memory_maintenance_manual_apply_decisions_regression_results.json
```

Report the following values.

From `ogcf_maintenance_review_memory_bank_regression_results.json`:

```text
memory_bank.evidence_ready_count
memory_bank.next_action
checks.exact_duplicate_evidence_ready
checks.stale_version_evidence_ready
checks.negative_bridge_not_ready
```

From `ogcf_maintenance_candidate_guard_regression_results.json`:

```text
guard.manual_review_candidate_count
guard.blocked_count
guard.next_action
checks.negative_bridge_blocked
checks.promotion_still_blocked
```

From `memory_maintenance_candidate_review_plan_regression_results.json`:

```text
plan.candidate_count
plan.blocked_count
plan.memory_review_kind_counts
plan.blocked_review_kind_counts
plan.promotion_ready
```

From `memory_maintenance_review_outcome_log_regression_results.json`:

```text
summary.outcome_count
summary.outcome_counts
summary.readiness
summary.next_action
summary.promotion_ready
```

From `memory_maintenance_manual_apply_decisions_regression_results.json`:

```text
manual_apply_decisions.decision_count
manual_apply_decisions.ready_for_manual_apply_count
manual_apply_decisions.held_count
manual_apply_decisions.applied_count
manual_apply_decisions.promotion_ready
```

Expected interpretation:

```text
accepted reviewed candidates may become ready_for_manual_apply
applied_count must stay 0
promotion_ready must stay false
negative/noisy bridge evidence must stay blocked
all artifacts must report mutates_db false
```

## Optional Full Lifecycle Smoke

If you want to exercise the generated fixture artifacts end to end, run:

```bash
python eval/ogcf_maintenance_review_memory_bank.py \
  --run ../experiments/ogcf_maintenance_review_memory_bank_run1_candidates.json::../experiments/ogcf_maintenance_review_memory_bank_run1_labels.json \
  --run ../experiments/ogcf_maintenance_review_memory_bank_run2_candidates.json::../experiments/ogcf_maintenance_review_memory_bank_run2_labels.json \
  --out-json ../experiments/hermes_maintenance_review_memory_bank_results.json \
  --out-md ../experiments/hermes_maintenance_review_memory_bank_report.md

python eval/ogcf_maintenance_candidate_guard.py \
  --memory-bank ../experiments/hermes_maintenance_review_memory_bank_results.json \
  --out-json ../experiments/hermes_maintenance_candidate_guard_results.json \
  --out-md ../experiments/hermes_maintenance_candidate_guard_report.md

python eval/memory_maintenance_candidate_review_plan.py \
  --guard ../experiments/hermes_maintenance_candidate_guard_results.json \
  --out-json ../experiments/hermes_memory_maintenance_review_plan_results.json \
  --out-md ../experiments/hermes_memory_maintenance_review_plan_report.md

python eval/memory_maintenance_review_outcome_log.py \
  --plan ../experiments/hermes_memory_maintenance_review_plan_results.json \
  --write-template \
  --template-out ../experiments/hermes_memory_maintenance_review_outcomes_template.json \
  --out-json ../experiments/hermes_memory_maintenance_review_outcome_summary_results.json \
  --out-md ../experiments/hermes_memory_maintenance_review_outcome_summary_report.md
```

If you fill the outcome template manually, rerun `memory_maintenance_review_outcome_log.py` with `--outcomes <filled-template>` and then:

```bash
python eval/memory_maintenance_manual_apply_decisions.py \
  --plan ../experiments/hermes_memory_maintenance_review_plan_results.json \
  --outcomes <filled-template> \
  --out-json ../experiments/hermes_memory_maintenance_manual_apply_decisions_results.json \
  --out-md ../experiments/hermes_memory_maintenance_manual_apply_decisions_report.md
```

Do not apply the decisions to the database. This version only validates the dry-run decision artifact.

## Report Back

Please write a concise report with:

- commit SHA tested;
- platform/environment notes;
- pass/fail table for required tests;
- required gate checks listed above;
- key artifact values listed above;
- any traceback or unexpected warning;
- whether the optional lifecycle smoke was run;
- recommendation: `ready_for_dev_review`, `needs_fix`, or `needs_more_real_review_labels`.
