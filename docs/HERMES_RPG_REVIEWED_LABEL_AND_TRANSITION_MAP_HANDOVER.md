# Hermes RPG Reviewed Label And Transition Map Handover

Date: 2026-06-05

## Purpose

This handover asks Hermes to validate the newest selector/memory architecture update after pulling GitHub. The new version adds:

- a clean-artifact bootstrap guard for the hybrid adaptive-behavior scorer;
- an architecture transition map for the neural-symbolic memory-brain restructuring roadmap;
- a balanced reviewed RPG label batch fixture that pressure-tests the label-bank, label-quality, and transparent scorer path.

The goal is not policy promotion. The goal is to verify that the combined architecture is stable as a report-only adaptive learning loop and to compare the synthetic reviewed-label baseline against any real or natural labels Hermes can collect.

## Safety Boundary

Do not mutate a real memory DB during this test.

Expected safety properties:

- report-only: true
- mutates_db: false
- mutates_runtime: false
- mutates_config: false
- ready_for_policy_use: false

RPG/ERG/OGCF and learned residual signals are allowed only as diagnostics, shadow signals, explanations, or reviewed training evidence.

## Pull Latest

From the Hermes test checkout:

```bash
git pull origin main
```

Record the commit SHA in your report.

## Required Clean Run

If possible, run from a clean or archived `experiments` folder so artifact-order bugs are visible.

```bash
python3 eval/adaptive_behavior_feature_scorer_hybrid_bootstrap_regression.py
python3 eval/controller_packet_residual_pipeline_regression.py
python3 eval/memory_maintenance_rpg_reviewed_label_batch_regression.py
python3 eval/architecture_transition_map_regression.py
python3 eval/architecture_readiness_dashboard_regression.py
python3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 8
python3 eval/architecture_valuation_report.py
python3 eval/architecture_transition_map.py
python3 eval/architecture_readiness_dashboard.py
```

Expected high-level result:

- selector architecture gate: ok true
- `adaptive_behavior_feature_scorer_hybrid_bootstrap_ok`: true
- `memory_maintenance_rpg_reviewed_label_batch_ok`: true
- `architecture_transition_map_ok`: true
- transition state: `stable_report_only_learning_loop`
- dashboard handover ready: true
- dashboard GitHub upload ready: true

The controller packet residual pipeline can be slow. Give it at least 5 minutes before treating it as failed.

## Reviewed RPG Label Baseline

Run the explicit reviewed-label path:

```bash
python3 eval/memory_maintenance_rpg_reviewed_label_batch.py
python3 eval/memory_maintenance_rpg_natural_label_bank.py \
  --packet ../experiments/memory_maintenance_rpg_reviewed_label_batch_results.json \
  --out-json ../experiments/memory_maintenance_rpg_reviewed_label_bank_results.json \
  --out-md ../experiments/memory_maintenance_rpg_reviewed_label_bank_report.md \
  --min-labels 12
python3 eval/memory_maintenance_rpg_label_quality_report.py \
  --packet ../experiments/memory_maintenance_rpg_reviewed_label_batch_results.json \
  --label-bank ../experiments/memory_maintenance_rpg_reviewed_label_bank_results.json \
  --out-json ../experiments/memory_maintenance_rpg_reviewed_label_quality_results.json \
  --out-md ../experiments/memory_maintenance_rpg_reviewed_label_quality_report.md
python3 eval/memory_maintenance_rpg_label_scorer.py \
  --label-bank ../experiments/memory_maintenance_rpg_reviewed_label_bank_results.json \
  --out-json ../experiments/memory_maintenance_rpg_reviewed_label_scorer_results.json \
  --out-md ../experiments/memory_maintenance_rpg_reviewed_label_scorer_report.md
```

Expected baseline:

- reviewed packet item count: 18
- six review labels, three examples each
- label quality `ready_for_shadow_scorer_training`: true
- scorer `ready_for_shadow_scorer`: true
- scorer `ready_for_policy_use`: false
- leave-one-out scorer accuracy should be at or above 0.5; local baseline was 0.722222

## Real Or Natural Label Comparison

If Hermes can collect or fill labels from natural RPG candidate packets, create a second packet with real/natural labels and run the same three scripts above against that packet.

Use labels only from:

```text
safe_duplicate
stale_or_update_conflict
bridge_contamination
semantic_near_duplicate
harmless_related_memory
uncertain_needs_more_context
```

Report whether the real/natural packet reaches:

- at least 12 labeled examples;
- at least 4 label classes;
- at least 4 candidate classes;
- dominant label ratio at or below 0.55;
- no contradictory labels for the same pair;
- family prediction accuracy at or above 0.60;
- shadow scorer readiness true;
- policy readiness false.

## Artifacts To Include In Hermes Report

Please report these file paths and key values:

- `experiments/selector_architecture_gate_results.json`
- `experiments/architecture_transition_map_results.json`
- `experiments/architecture_readiness_dashboard_results.json`
- `experiments/memory_maintenance_rpg_reviewed_label_batch_results.json`
- `experiments/memory_maintenance_rpg_reviewed_label_quality_results.json`
- `experiments/memory_maintenance_rpg_reviewed_label_scorer_results.json`
- any real/natural label packet, label bank, quality report, and scorer report you create

For each, include:

- `ok`
- schema
- readiness fields
- promotion blockers
- any failing checks
- whether anything mutated DB/runtime/config

## What The Developer Needs Back

Give a concise report answering:

1. Did the clean clone/run pass?
2. Did the controller residual pipeline remain fixed?
3. Did the transition map report `stable_report_only_learning_loop`?
4. Did the reviewed RPG label baseline pass label quality and scorer readiness?
5. If real/natural labels were tested, how did they compare to the synthetic reviewed baseline?
6. What failed, timed out, or looked suspicious?
7. What should the next development focus be: more real labels, scorer improvement, operator outcome UI/API integration, or gate/dashboard consolidation?

Do not recommend runtime policy promotion unless real/natural labels and real maintenance outcomes pass the quality gates. Current expected conclusion is that the architecture is ready for more reviewed evidence collection, not automatic memory mutation.
