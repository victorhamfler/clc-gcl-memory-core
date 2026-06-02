# Hermes Handover: Corrected OGCF v2 Geometry and Structural-Pressure Validation

Date: 2026-06-02

## Purpose

Validate the newest selector/memory architecture update after pulling from GitHub.

This update aligns the program with corrected OGCF-AI v2 math and carries the corrected interpretation through the selector, evidence-context feature contract, controller packets, and learned scorer datasets.

## What Changed

The OGCF math correction is:

```text
M_ij = B_j.T @ B_i      # raw overlap diagnostic
Q_ij = polar(M_ij)      # corrected finite-step transport
```

The code now separates:

- raw-overlap diagnostics for bridge overload / cross-domain structural pressure;
- corrected polar transport diagnostics for polar holonomy and polar interaction excess;
- factual contradiction signals, which must remain owned by evidence/claim/source/recency logic.

Important new feature:

```text
EvidenceContextFeatures.ogcf_structural_pressure
```

This should be present in controller packets and learned feature datasets. It is computed from explicit diagnostics when available, with fallback:

```text
ogcf_bridge_overload_score * ogcf_effective_affected_memory_ratio
```

## Required Pull

From the Hermes working clone:

```bash
git pull origin main
```

Then record the pulled commit SHA in your report:

```bash
git rev-parse HEAD
```

## Required Tests

Run these from the repository root.

```bash
python eval/ogcf_corrected_geometry_regression.py
python eval/ogcf_affected_pressure_calibration_regression.py
python eval/ogcf_selector_integration_eval.py
python eval/evidence_context_regression.py
python eval/controller_packet_regression.py
python eval/adaptive_behavior_feature_scorer_regression.py
python eval/adaptive_behavior_feature_challenge_regression.py
python eval/controller_packet_real_log_readiness_regression.py
python eval/controller_packet_calibration_config_regression.py
python eval/controller_packet_calibration_runtime_view_regression.py
python eval/controller_packet_calibration_pipeline_regression.py
python eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 8
```

If your environment uses `python3`, use `python3` instead of `python`.

## What To Inspect

Please inspect the generated JSON/MD artifacts under `experiments/` and report:

1. Whether all commands passed.
2. Whether `selector_architecture_gate` reports:

```text
ogcf_corrected_geometry_ok: true
controller_packet_real_log_readiness_regression_ok: true
controller_packet_calibration_pipeline_ok: true
adaptive_behavior_feature_challenge_ok: true
```

3. In `ogcf_corrected_geometry_regression_results.json`, confirm:

```text
raw_overlap_orientation: true
polar_transport_is_orthogonal: true
raw_and_polar_excess_are_separate: true
backward_compatible_aliases: true
```

4. In `ogcf_affected_pressure_calibration_regression_results.json`, confirm:

```text
bridge_overload_does_not_create_contradiction_peak: true
```

Also report the `true_loop.diagnostics` values for:

```text
adjusted_contradiction_peak
ogcf_structural_pressure
ogcf_bridge_overload_score
ogcf_effective_affected_memory_ratio
```

5. In `controller_packet_regression_results.json`, confirm the packet evidence-context features include:

```text
ogcf_structural_pressure
ogcf_bridge_overload_score
ogcf_effective_affected_memory_ratio
```

6. In `adaptive_behavior_feature_scorer_regression_results.json` or its report, confirm `ogcf_structural_pressure` is included in the feature keys if feature keys are emitted.

## Optional Real-Log Test

If you have real Hermes outcome logs available, run the calibration pipeline on at least two independent logs:

```bash
python eval/controller_packet_calibration_pipeline.py \
  --log /path/to/log1.jsonl \
  --log /path/to/log2.jsonl \
  --out-prefix /tmp/hermes_ogcf_v2_packet_calibration \
  --out-json /tmp/hermes_ogcf_v2_packet_calibration_results.json \
  --out-md /tmp/hermes_ogcf_v2_packet_calibration_report.md
```

Report the `real_log_readiness` object, especially:

```text
readiness
next_action
blockers
packet_count
source_log_count
evidence_context_feature_coverage
```

Do not promote or mutate runtime behavior from this. It is report-only.

## Expected Interpretation

The correct behavior is:

- OGCF bridge overload can make the selector more cautious.
- OGCF bridge overload must not create factual contradiction pressure by itself.
- Learned controllers should use `ogcf_structural_pressure` as a structural signal.
- Direct contradiction remains a semantic/evidence/source/recency responsibility.
- All new behavior remains report-only and non-mutating.

## Report Back

Please write a concise report with:

- commit SHA tested;
- platform/environment notes;
- pass/fail table for required tests;
- key JSON values listed above;
- any traceback or unexpected warning;
- whether real-log optional test was run;
- recommendation: `ready_for_dev_review`, `needs_fix`, or `needs_more_real_logs`.
