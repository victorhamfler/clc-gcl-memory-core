# Hermes Handover: Architecture Readiness And Feedback Loop Test

## Purpose

Test the current selector + memory-maintenance architecture after the new report-only RPG supervised feedback loop was added.

The system now has this guarded loop:

```text
RPG diagnostics
-> copied-DB maintenance rehearsal
-> operator review packet
-> operator outcome capture
-> operator outcome RPG feedback packet
-> merged RPG label-bank evaluation
-> architecture readiness dashboard
```

All of this must remain report-only. Do not enable real DB mutation. Do not treat RPG labels or scorer output as policy.

## Current Readiness

The local dashboard currently reports:

- architecture gate OK: true
- architecture valuation OK: true
- handover ready: true
- GitHub upload ready: true
- RPG feedback merge label gain: 2
- combined scorer policy ready: false

Policy boundary:

```text
runtime_policy_mutation_allowed: false
real_db_mutation_allowed_by_default: false
rpg_policy_use_allowed: false
```

## Setup

Pull the latest GitHub version of:

```text
https://github.com/victorhamfler/clc-gcl-memory-core
```

Use the repository root:

```powershell
cd clc_gcl_memory_core
```

If your environment uses WSL, translate paths as needed, but keep generated experiment artifacts in the repo-level `experiments` folder or a clearly named external artifact folder.

## Required Smoke Tests

Run these first:

```powershell
py -3 eval/architecture_readiness_dashboard.py
py -3 eval/architecture_readiness_dashboard_regression.py
py -3 eval/architecture_valuation_report_regression.py
py -3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 8
```

Expected:

- all commands exit successfully;
- selector architecture gate prints `"ok": true`;
- dashboard prints `"handover_ready": true`;
- dashboard prints `"github_upload_ready": true`;
- dashboard does not mark RPG scorer policy ready.

## Required Feedback Loop Test

Run the full report-only feedback chain:

```powershell
py -3 eval/memory_maintenance_operator_review_packet_regression.py
py -3 eval/memory_maintenance_operator_outcome_capture_regression.py
py -3 eval/memory_maintenance_operator_outcome_rpg_feedback_regression.py
py -3 eval/memory_maintenance_rpg_feedback_merge_evaluation_regression.py
py -3 eval/architecture_readiness_dashboard.py
```

Expected:

- operator packet includes `rpg_learning_context`;
- operator outcome capture preserves RPG summary and learning context;
- operator outcome RPG feedback emits `memory_maintenance_rpg_natural_candidate_review_packet/v1`;
- RPG label bank can consume the feedback packet;
- merge evaluation reports positive label gain from operator feedback;
- all artifacts remain report-only and non-mutating.

## Realistic Operator Feedback Test

If possible, create or use a small copied-DB rehearsal/operator packet with realistic memory items. Then:

1. Generate an operator review packet.
2. Fill an operator outcome JSON with at least:
   - one accepted duplicate-like item;
   - one rejected or unsafe item;
   - one `needs_more_evidence` item if available;
   - one explicit `rpg_training_label` where the operator/Hermes thinks the derived label is not enough.
3. Run:

```powershell
py -3 eval/memory_maintenance_operator_outcome_capture.py --packet <operator_packet.json> --outcomes <your_outcomes.json>
py -3 eval/memory_maintenance_operator_outcome_rpg_feedback.py --capture <capture_results.json>
py -3 eval/memory_maintenance_rpg_feedback_merge_evaluation.py --operator-feedback <feedback_results.json>
py -3 eval/architecture_readiness_dashboard.py
```

Do not run any mutation command. Do not use `--enable-mutation`. Do not use a real DB apply path.

## Report Back

Write a Markdown report and a JSON report with:

- command list;
- pass/fail result for every command;
- dashboard summary;
- whether handover/upload readiness stayed true;
- whether any chain failed;
- label gain from operator feedback;
- combined label count;
- whether combined scorer is still policy blocked;
- any confusing operator packet fields;
- any memory-program UI/API hooks that would make outcome capture easier.

Suggested filenames:

```text
experiments/hermes_architecture_readiness_feedback_loop_report.md
experiments/hermes_architecture_readiness_feedback_loop_report.json
```

## Safety Rules

- No real DB mutation.
- No automatic memory deprecation.
- No RPG policy promotion.
- No scorer-driven apply decisions.
- Treat RPG signals as explanation-only or shadow-learning evidence.
- If a command suggests mutation, stop and report the command instead of running it.

## What We Need To Learn

The key question is whether the current architecture is ready for real/Hermes-generated operator feedback:

```text
operator review outcomes
-> RPG feedback packet
-> merged label-bank evaluation
-> readiness dashboard
```

If this works on realistic logs, the next development should be memory-program UI/API hooks for outcome capture. If it fails, report which artifact or schema made the loop difficult to use.
