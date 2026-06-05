# Hermes RPG Real-Use Reviewed Learning Loop Handover

Date: 2026-06-05

## Purpose

This handover asks Hermes to validate the newest selector and memory-brain architecture update after pulling GitHub. The new work advances the RPG/ERG/OGCF supervised maintenance path from synthetic fixtures into a locally reviewed real-use memory scenario.

The goal is evidence collection and shadow-learning validation, not policy promotion.

The new path is:

```text
full memory-brain real-use scenario
-> reviewed duplicate/correction/bridge/related memory pairs
-> filled RPG worksheet import
-> natural label bank
-> label quality report
-> transparent RPG label scorer
-> architecture gate / preflight
```

## Safety Boundary

Do not mutate a real production memory DB during this test.

Expected safety properties:

- `report_only: true`
- `mutates_db: false`
- `mutates_runtime: false`
- `mutates_config: false`
- `ready_for_policy_use: false`
- `promotion_ready: false`

RPG/ERG/OGCF and learned residual signals are allowed only as diagnostics, shadow signals, explanations, or reviewed training evidence.

## Pull Latest

From the Hermes test checkout:

```bash
git pull origin main
git rev-parse HEAD
```

Record the commit SHA in your final report.

## Required Clean Validation

Run from the repository root. If practical, archive or move the existing `experiments` folder first so stale artifact problems are visible.

```bash
python3 eval/architecture_preflight_regression.py
python3 eval/memory_maintenance_rpg_label_collection_plan_regression.py
python3 eval/memory_maintenance_rpg_label_review_worksheet_regression.py
python3 eval/memory_maintenance_rpg_filled_worksheet_import_regression.py
python3 eval/memory_maintenance_rpg_filled_worksheet_learning_loop_regression.py
python3 eval/memory_maintenance_rpg_real_use_reviewed_learning_loop_regression.py
python3 eval/full_memory_brain_real_use_eval.py
python3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 8
python3 eval/architecture_preflight.py --random-cases 8
```

The full selector architecture gate can take several minutes.

Expected high-level result:

- selector architecture gate: `ok: true`
- architecture preflight: `ok: true`
- transition state: `stable_report_only_learning_loop`
- dashboard handover ready: `true`
- dashboard GitHub upload ready: `true`
- full memory-brain real-use eval: `ok: true`
- `memory_maintenance_rpg_label_collection_plan_ok: true`
- `memory_maintenance_rpg_label_review_worksheet_ok: true`
- `memory_maintenance_rpg_filled_worksheet_import_ok: true`
- `memory_maintenance_rpg_filled_worksheet_learning_loop_ok: true`
- `memory_maintenance_rpg_real_use_reviewed_learning_loop_ok: true`

## Explicit RPG Real-Use Reviewed Loop

Run the newest real-use reviewed learning-loop script directly:

```bash
python3 eval/memory_maintenance_rpg_real_use_reviewed_learning_loop.py
```

Expected local baseline:

- imported reviewed items: `15`
- label classes: at least `4`; local baseline has `6`
- candidate classes: at least `4`; local baseline has `6`
- label quality `ready_for_shadow_scorer_training: true`
- scorer `ready_for_shadow_scorer: true`
- scorer `ready_for_policy_use: false`
- local leave-one-out scorer accuracy: around `0.933333`
- promotion blockers include:
  - `external_reviewer_confirmation_required`
  - `real_maintenance_outcome_validation_required`
  - `policy_ablation_required`

If this fails, check first for contradictory labels assigned to the same memory pair. The local quality report should reject those.

## Natural/Real DB Label Collection Test

If Hermes has access to a copied non-production memory DB, run the natural candidate flow on the copy only. Do not run maintenance apply commands on the original DB.

Suggested flow:

```bash
python3 eval/memory_maintenance_rpg_natural_candidate_review_packet.py
python3 eval/memory_maintenance_rpg_label_collection_plan.py
python3 eval/memory_maintenance_rpg_label_review_worksheet.py
```

Then fill as many worksheet rows as possible using only these labels:

```text
safe_duplicate
stale_or_update_conflict
bridge_contamination
semantic_near_duplicate
harmless_related_memory
uncertain_needs_more_context
```

After filling labels and reviewer fields, import the worksheet:

```bash
python3 eval/memory_maintenance_rpg_filled_worksheet_import.py \
  --worksheet ../experiments/memory_maintenance_rpg_label_review_worksheet_results.json
```

If the imported packet has enough labels, run:

```bash
python3 eval/memory_maintenance_rpg_natural_label_bank.py \
  --packet ../experiments/memory_maintenance_rpg_filled_worksheet_import_results.json
python3 eval/memory_maintenance_rpg_label_quality_report.py \
  --packet ../experiments/memory_maintenance_rpg_filled_worksheet_import_results.json \
  --label-bank ../experiments/memory_maintenance_rpg_natural_label_bank_results.json
python3 eval/memory_maintenance_rpg_label_scorer.py \
  --label-bank ../experiments/memory_maintenance_rpg_natural_label_bank_results.json
```

Report whether the natural reviewed packet reaches:

- at least 12 labeled examples;
- at least 4 label classes;
- at least 4 candidate classes;
- dominant label ratio at or below 0.55;
- no contradictory labels for the same pair;
- family prediction accuracy at or above 0.60;
- shadow scorer readiness true;
- policy readiness false.

## Artifacts To Include

Please include paths and key values from:

- `experiments/selector_architecture_gate_results.json`
- `experiments/selector_architecture_gate_report.md`
- `experiments/architecture_preflight_results.json`
- `experiments/architecture_preflight_report.md`
- `experiments/architecture_transition_map_results.json`
- `experiments/architecture_readiness_dashboard_results.json`
- `experiments/full_memory_brain_real_use_eval_results.json`
- `experiments/memory_maintenance_rpg_real_use_reviewed_learning_loop_results.json`
- `experiments/memory_maintenance_rpg_real_use_reviewed_learning_loop_report.md`
- any natural filled worksheet, imported packet, label bank, quality report, or scorer report Hermes creates

For each relevant artifact, report:

- `ok`
- schema
- label counts
- candidate-class counts
- readiness fields
- promotion blockers
- failing checks
- whether anything mutated DB/runtime/config

## What The Developer Needs Back

Answer these questions:

1. Did a clean pull and required validation pass?
2. Did the real-use reviewed learning loop pass?
3. Did any contradictory labels appear in natural/real reviewed data?
4. Did natural labels, if tested, reach the quality thresholds?
5. How did natural scorer accuracy compare to the local real-use baseline?
6. Did any script unexpectedly mutate DB/runtime/config?
7. What should the next development focus be: real worksheet UI/API, external label confirmation, scorer feature improvements, copied-DB outcome validation, or gate/dashboard consolidation?

Do not recommend runtime policy promotion. The expected conclusion is that the architecture is ready for more real reviewed evidence collection and copied-DB outcome validation, not automatic memory mutation.
