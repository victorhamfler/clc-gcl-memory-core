# Hermes Handover: Portable Gate Rerun

Date: 2026-06-02

## Purpose

Rerun the runtime-contract and portable architecture gate after the `shadow_coverage_guard_ok` blocker found in the previous Hermes test.

The previous Hermes run confirmed the requested runtime contracts passed, but the full architecture gate failed because `shadow_coverage_guard_ok` was false. The dev-side fix makes `eval/canonical_ogcf_shadow_coverage_regression.py` self-contained and adds `eval/portable_gate_dependency_regression.py` so the portable gate protects that boundary.

## Repository

```text
https://github.com/victorhamfler/clc-gcl-memory-core
```

Pull latest `main` after the upload containing this handover file.

## Safety Rules

- Do not edit source files.
- Do not edit `config.yaml`.
- Do not use or mutate live memory DBs.
- Run from a clean clone or isolated test copy.
- Write Hermes artifacts under your normal isolated `experiments_hermes` test folder.

## Required Commands

From the repo root in WSL:

```bash
python3 eval/portable_gate_dependency_regression.py
python3 eval/canonical_ogcf_shadow_coverage_regression.py
python3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 16
```

Then rerun the runtime-contract subset from the previous handover:

```bash
python3 eval/resolver_shadow_runtime_view_regression.py
python3 eval/adaptive_residual_shadow_runtime_view_regression.py
python3 eval/controller_packet_calibration_runtime_view_regression.py
python3 eval/controller_packet_calibration_config_regression.py
python3 eval/controller_packet_ogcf_bridge_leave_one_source_out_regression.py
```

## Expected Result

All commands should return `ok: true`.

The architecture gate must include:

```json
{
  "shadow_coverage_guard_ok": true,
  "portable_gate_dependency_ok": true,
  "resolver_shadow_runtime_view_ok": true,
  "adaptive_residual_shadow_runtime_view_ok": true,
  "controller_packet_calibration_runtime_view_ok": true,
  "controller_packet_ogcf_bridge_leave_one_source_out_ok": true
}
```

## What To Report Back

Create one Markdown report and one JSON summary with:

- tested commit hash;
- OS/runtime and Python version;
- pass/fail for each required command;
- full `required_summary` from `selector_architecture_gate.py`;
- whether `shadow_coverage_guard_ok` is now fixed;
- whether `portable_gate_dependency_ok` passed;
- artifact paths for generated JSON/MD files;
- any traceback or stderr if a command fails.

## Interpretation

If this passes, the previous Hermes blocker should be considered fixed. The next development direction can return to real-log controller-packet collection and OGCF bridge/source-holdout validation instead of portable-gate repair.
