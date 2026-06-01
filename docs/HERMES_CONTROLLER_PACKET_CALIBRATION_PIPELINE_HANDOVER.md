# Hermes Controller Packet Calibration Pipeline Handover

Date: 2026-06-01

## Purpose

This handover asks Hermes to validate the new selector-side controller packet calibration path under realistic continued work.

The current selector architecture now writes `controller_evidence_packet/v1` into ask outcome logs and includes a one-command report-only pipeline:

```text
outcome logs -> controller packets -> packet memory bank -> calibration proposals -> calibration guard
```

The goal is not to promote any runtime behavior. The goal is to gather real packet evidence and verify that the new calibration pipeline remains safe, useful, and conservative.

## Repository Setup

Pull the latest GitHub version:

```bash
cd /home/victo
rm -rf clc-gcl-memory-core
git clone https://github.com/victorhamfler/clc-gcl-memory-core.git
cd clc-gcl-memory-core
```

Use the project Python environment available to Hermes. If needed, create or reuse a venv with the project dependencies already used in previous Hermes runs.

## Sanity Gate

First run the portable architecture gate:

```bash
python eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 8
```

Expected result:

```text
ok: true
```

The required summary should include:

```text
outcome_logging_controller_packet_ok: true
controller_packet_memory_bank_ok: true
controller_packet_calibration_proposals_ok: true
controller_packet_calibration_guard_ok: true
controller_packet_calibration_pipeline_ok: true
```

If this fails, stop and report the failing checks and stderr/stdout.

## Runtime Test Goal

Run a realistic memory-agent session that produces ask logs with embedded `controller_evidence_packet/v1`.

The test should include:

- normal supported-answer questions;
- safe supported-evidence questions where a residual benefit opportunity may appear;
- missing-support questions that should not be answered confidently;
- stale/current correction-chain questions;
- near-topic distractors;
- ordinary memory lookups with no OGCF pressure;
- a few OGCF/bridge-style questions if the local memory data supports them.

Keep all adaptive/residual behavior report-only. Do not manually promote config, resolver weights, selector policy, or memory mutation behavior from these results.

## Suggested Prompt Mix

Use the live memory program and ask at least 40 questions if practical.

Include prompts similar to these, adapted to available local memories:

```text
What evidence supports keeping selector policy mutation report-only?
How should the selector use Hermes failure evidence safely?
What does the current gate say about learned-risk checks?
What proof authorizes immediate policy mutation from one test run?
What evidence says learned risk can rewrite policy immediately?
Should we revert to the prior no-veto authority interpretation?
What is the current rule when stale and current memories disagree?
What should the memory system do when no support exists?
Which memory explains the controller packet pipeline?
How does OGCF bridge pressure affect selector decisions?
```

For each ask, add answer-level feedback when possible:

- `answer_correct` for supported correct answers;
- `answer_missing_support` for answers that should have refused or lowered confidence;
- `answer_stale` for stale-answer failures;
- `answer_wrong_scope` for near-topic wrong answers;
- `answer_bridge_warning_useful` or `answer_bridge_warning_noise` for bridge-warning behavior.

Also add memory-row feedback where possible:

- `useful` for selected evidence that directly supports the answer;
- `wrong`, `stale`, or `wrong_domain` for bad evidence rows.

## Required Pipeline Command

After generating the outcome log, run the new one-command calibration pipeline.

Replace `<LOG_PATH>` with the actual outcome log path:

```bash
python eval/controller_packet_calibration_pipeline.py \
  --log <LOG_PATH> \
  --out-prefix /home/victo/experiments_hermes/controller_packet_calibration_real \
  --out-json /home/victo/experiments_hermes/controller_packet_calibration_real_results.json \
  --out-md /home/victo/experiments_hermes/controller_packet_calibration_real_report.md
```

Expected behavior:

- pipeline `ok` should be true;
- packet count should be greater than zero;
- clusters should be generated;
- proposals may be generated;
- guard-ready promotions should normally be `0` unless there is unusually strong multi-log evidence;
- all outputs must remain report-only and non-mutating.

## Additional Verification

Run these focused checks:

```bash
python eval/controller_packet_calibration_pipeline_regression.py
python eval/outcome_logging_regression.py
python eval/resolver_policy_runtime_view_regression.py
```

Expected result for all:

```text
ok: true
```

## What To Report Back

Write a Markdown report and a JSON summary under:

```text
/home/victo/experiments_hermes/
```

Suggested file names:

```text
CONTROLLER_PACKET_CALIBRATION_REAL_REPORT.md
controller_packet_calibration_real_summary.json
```

The report should include:

- commit hash tested;
- Python/environment notes;
- outcome log path;
- number of ask events;
- number of feedback events;
- whether ask events contained embedded `controller_evidence_packet/v1`;
- packet count;
- cluster count;
- proposal count;
- promotion candidate count;
- review item count;
- guard-ready count;
- guard-blocked count;
- examples of positive calibration candidates;
- examples of missing-support or stale review items;
- whether any mutation flags were present;
- all command outputs or relevant stderr if something failed.

## Interpretation Rules

Do not treat a calibration proposal as a promoted improvement.

Correct interpretation:

```text
proposal = evidence worth testing
guard ready = possible future promotion candidate
guard blocked = useful evidence, but not safe to promote
```

For this stage, a good Hermes result is:

```text
pipeline ok: true
packets: > 0
clusters: > 0
proposals: >= 0
guard-ready promotions: probably 0
mutation flags: false
```

The most valuable output is not a ready promotion. The most valuable output is a clean real packet dataset with linked feedback that future selector-side tests can replay.

