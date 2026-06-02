# Hermes Handover: Controller Packet Runtime Contract Test

Date: 2026-06-02

## Purpose

Validate the current CLC/GCL memory-core architecture after the selector/runtime contract restructuring.

The current development direction is to turn hardcoded and eval-local behavior into explicit, runtime-visible, report-only policy contracts before any learned/adaptive controller is allowed near runtime behavior. This version adds and protects three important shared surfaces:

- controller-packet calibration policy;
- adaptive residual shadow policy;
- resolver-shadow config policy.

Hermes should pull the latest GitHub version, run the tests below, and produce a report that says whether these contracts are visible, non-mutating, and usable during realistic memory work.

## Repository

```text
https://github.com/victorhamfler/clc-gcl-memory-core
```

Use the latest `main` branch after the upload that includes this handover file.

## Important Safety Rules

- Do not promote learned behavior.
- Do not edit `config.yaml` unless the test explicitly uses an isolated override or temp copy.
- Do not mutate live memory DBs unless the test intentionally creates a temp/test DB.
- Do not delete existing experiment artifacts.
- Write any new Hermes output under your normal `experiments_hermes` folder or another clearly named Hermes test folder.
- Report failures with the exact command, traceback, and artifact path.

## Required Setup

From the repo root:

```powershell
cd <repo-root>
```

If running from WSL, use the local Python environment Hermes normally uses for this repository. If running from Windows, `py -3` is acceptable.

The portable tests use hash embeddings and should not require Gemma. If you run optional realistic tests with configured embeddings, record whether Gemma was used.

## Required Tests

Run these first:

```powershell
py -3 eval/resolver_shadow_runtime_view_regression.py
py -3 eval/adaptive_residual_shadow_runtime_view_regression.py
py -3 eval/controller_packet_calibration_runtime_view_regression.py
py -3 eval/controller_packet_calibration_config_regression.py
```

Expected:

- all return `ok: true`;
- `/config` exposes `resolver_shadow`;
- `/config` exposes `adaptive_residual_shadow`;
- `/config` exposes `controller_packet_calibration`;
- all three surfaces include report-only/non-mutating guarantees.

Then run the focused behavior checks:

```powershell
py -3 eval/resolver_shadow_mode_regression.py
py -3 eval/resolver_shadow_runtime_context_log_regression.py
py -3 eval/adaptive_residual_shadow_suppressor_regression.py
py -3 eval/adaptive_residual_shadow_runtime_regression.py
py -3 eval/controller_packet_regression.py
py -3 eval/controller_packet_ogcf_bridge_scorer_feature_regression.py
py -3 eval/controller_packet_ogcf_bridge_leave_one_source_out_regression.py
```

Expected:

- all return `ok: true`;
- resolver shadow still behaves as report-only;
- adaptive residual shadow remains opt-in and non-mutating;
- controller packets preserve evidence-context features;
- OGCF bridge learned-scorer tests remain report-only and promotion-blocked unless policy evidence is sufficient.

Finally run the architecture gate:

```powershell
py -3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 16
```

Expected:

- top-level `ok: true`;
- required summary includes:
  - `resolver_shadow_runtime_view_ok: true`;
  - `adaptive_residual_shadow_runtime_view_ok: true`;
  - `controller_packet_calibration_runtime_view_ok: true`;
  - `controller_packet_ogcf_bridge_leave_one_source_out_ok: true`.

## Optional Realistic Runtime Test

If Hermes can run a short realistic memory session, create a temp/test DB and run a small ask/feedback flow that includes:

- `include_resolver_shadow: true`;
- `include_adaptive_residual_shadow: true`;
- `log_adaptive_residual_shadow: true`;
- at least one answer-level feedback row;
- at least one memory-level feedback row;
- at least one OGCF/bridge-like query;
- at least one ordinary fact/profile/scope-control query.

Then run the controller-packet pipeline on the produced outcome log:

```powershell
py -3 eval/controller_packet_calibration_pipeline.py --log <your-outcome-log.jsonl> --out-prefix <your-output-prefix>
```

If there are enough packet sources, also run:

```powershell
py -3 eval/controller_packet_ogcf_bridge_leave_one_source_out.py --packets <your-packets.jsonl> --out-json <your-loso.json> --out-md <your-loso.md>
```

Report whether the run is underpowered or candidate-worthy. Underpowered is acceptable; the key is that the report should explain why.

## What To Report Back

Create one Markdown report and one JSON summary. Include:

- repo commit hash tested;
- OS/runtime used;
- Python command used;
- pass/fail for every required command;
- paths to generated JSON/MD artifacts;
- whether `/config` exposed the three runtime policy contracts;
- whether any test mutated runtime behavior, answer text, selector policy, memory rows, or config;
- architecture-gate required summary;
- optional realistic runtime results, if run;
- any failure tracebacks or suspicious warnings.

## Development Interpretation To Check

The desired result is not runtime promotion. The desired result is that Hermes confirms the architecture can now show its active controller/shadow/calibration policies through runtime config, while controller packets and calibration artifacts continue to be report-only.

If this passes, the next development stage should be broader real-log collection for:

- controller-packet LOSO evidence across independent sources;
- OGCF bridge useful-vs-noisy separation;
- residual-shadow safety and benefit opportunities;
- resolver-shadow answer-feedback calibration.

Only after repeated real-log validation should we discuss promotion paths.
