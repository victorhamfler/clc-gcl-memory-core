# Answer Behavior Shadow Eval Handover

Date: 2026-05-24

## Purpose

This handover records the first report-only shadow eval for answer behavior proposals. The goal is to test guarded resolver/controller behavior before the memory-program session changes `serve.py` or the answer resolver.

The implementation is advisory only. It does not modify runtime config, resolver code, selector policy, memory rows, or learned artifacts.

## New Files

- `eval/answer_behavior_shadow_eval.py`
- `eval/answer_behavior_shadow_regression.py`
- `eval/answer_behavior_real_log_shadow_replay.py`
- `eval/answer_behavior_real_log_fixture.py`
- `core/answer_behavior_shadow.py`
- `eval/resolver_shadow_mode_regression.py`
- `eval/answer_behavior_ogcf_bridge_worklog_fixture.py`
- `eval/resolver_shadow_ogcf_bridge_worklog_regression.py`
- `eval/resolver_shadow_threshold_calibration.py`
- `eval/resolver_shadow_threshold_calibration_dataset_regression.py`
- `eval/resolver_shadow_outcome_collector.py`
- `eval/resolver_shadow_outcome_collector_regression.py`

## Inputs

The shadow eval consumes the existing report-only proposal stack:

- `experiments/answer_behavior_proposals_results.json`
- `experiments/answer_behavior_proposal_guard_results.json`

Expected schemas:

- `answer_behavior_proposals/v1`
- `answer_behavior_proposal_guard/v1`

## Outputs

The eval writes:

- `experiments/answer_behavior_shadow_eval_results.json`
- `experiments/answer_behavior_shadow_eval_report.md`

The regression writes:

- `experiments/answer_behavior_shadow_regression_results.json`
- `experiments/answer_behavior_shadow_regression_report.md`

The real-log replay writes:

- `experiments/answer_behavior_real_log_shadow_replay_results.json`
- `experiments/answer_behavior_real_log_shadow_replay_report.md`

The missing-label fixture writes:

- `experiments/answer_behavior_real_log_missing_cases.jsonl`

The combined full-coverage replay writes:

- `experiments/answer_behavior_real_log_shadow_replay_full_coverage_results.json`
- `experiments/answer_behavior_real_log_shadow_replay_full_coverage_report.md`

The resolver-shadow mode regression writes:

- `experiments/resolver_shadow_mode_regression_results.json`
- `experiments/resolver_shadow_mode_regression_report.md`

The OGCF bridge worklog fixture writes:

- `experiments/answer_behavior_ogcf_bridge_worklog.jsonl`
- `experiments/answer_behavior_ogcf_bridge_worklog_replay_results.json`
- `experiments/answer_behavior_ogcf_bridge_worklog_replay_report.md`
- `experiments/resolver_shadow_ogcf_bridge_worklog_regression_results.json`
- `experiments/resolver_shadow_ogcf_bridge_worklog_regression_report.md`

The threshold calibration writes:

- `experiments/resolver_shadow_threshold_calibration_results.json`
- `experiments/resolver_shadow_threshold_calibration_report.md`
- `experiments/resolver_shadow_threshold_calibration_current_default_results.json`
- `experiments/resolver_shadow_threshold_calibration_current_default_report.md`
- `experiments/resolver_shadow_threshold_calibration_raw_log_compare_results.json`
- `experiments/resolver_shadow_threshold_calibration_raw_log_compare_report.md`
- `experiments/resolver_shadow_threshold_calibration_dataset_regression_results.json`
- `experiments/resolver_shadow_threshold_calibration_dataset_regression_report.md`

The outcome collector writes:

- `experiments/resolver_shadow_outcome_dataset_results.json`
- `experiments/resolver_shadow_outcome_dataset_report.md`
- `experiments/resolver_shadow_outcome_dataset_strict_results.json`
- `experiments/resolver_shadow_outcome_dataset_strict_report.md`
- `experiments/resolver_shadow_outcome_collector_regression_results.json`
- `experiments/resolver_shadow_outcome_collector_regression_report.md`

Output schema:

- `answer_behavior_shadow_eval/v1`
- `answer_behavior_real_log_shadow_replay/v1`

## Controlled Cases

The first shadow suite covers five answer-behavior cases:

- `supported_answer_with_evidence`
- `bridge_warning_supported`
- `ordinary_fact_with_bridge_word`
- `unsupported_private_code`
- `stale_conflict_supported`

It verifies these behavior targets:

- evidence-backed supported answers;
- OGCF bridge-risk warning only when supported by evidence and OGCF diagnostics;
- suppression of bridge warnings for ordinary factual uses of bridge-like words;
- preservation of missing-support refusal when no selected memory supports the query;
- stale/current disclosure when selected evidence contains stale conflict.

## Commands Run

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_shadow_regression.py
```

Result: pass.

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_shadow_eval.py --proposals ..\experiments\answer_behavior_proposals_results.json --guard ..\experiments\answer_behavior_proposal_guard_results.json --out-json ..\experiments\answer_behavior_shadow_eval_results.json --out-md ..\experiments\answer_behavior_shadow_eval_report.md
```

Result: pass, 5/5 controlled cases.

```powershell
..\.venv-torch\Scripts\python.exe -m py_compile .\eval\answer_behavior_shadow_eval.py .\eval\answer_behavior_shadow_regression.py
```

Result: pass.

Additional architecture guards were rerun:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_guard.py --proposals ..\experiments\answer_behavior_proposals_results.json --out-json ..\experiments\answer_behavior_proposal_guard_results.json --out-md ..\experiments\answer_behavior_proposal_guard_report.md
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_policy_distribution_regression.py
```

Result: pass.

The first real-log replay was also run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_shadow_replay.py --log ..\experiments\neural_symbolic_outcome_holdout_workflow.jsonl
```

Result: pass, 3/3 linked answer-feedback cases.

Covered labels:

- `answer_correct`
- `answer_bridge_warning_useful`
- `answer_missing_support`

A broader combined replay against `logs/memory_outcomes.jsonl` did not add extra answer-scope cases. The OGCF intent workflow currently contains memory-level labels only, so it is not yet usable for answer-behavior replay.

The missing-label fixture was then generated locally:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_fixture.py
```

Result: pass, 5 linked ask/answer-feedback fixture cases.

The full-coverage replay was run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_shadow_replay.py --log ..\experiments\neural_symbolic_outcome_holdout_workflow.jsonl --log ..\experiments\answer_behavior_real_log_missing_cases.jsonl --out-json ..\experiments\answer_behavior_real_log_shadow_replay_full_coverage_results.json --out-md ..\experiments\answer_behavior_real_log_shadow_replay_full_coverage_report.md
```

Result: pass, 8/8 linked answer-feedback cases.

Covered labels:

- `answer_correct`
- `answer_bridge_warning_useful`
- `answer_bridge_warning_noise`
- `answer_missing_support`
- `answer_stale`
- `answer_conflict_not_disclosed`
- `answer_bad_citation`
- `answer_wrong_scope`

The configurable resolver-shadow mode was then implemented. It is disabled by default in `config.yaml`:

```yaml
resolver_shadow:
  enabled: false
  include_in_outcome_log: false
  bridge_warning_score_threshold: 0.70
  bridge_warning_effective_ratio_threshold: 0.50
```

When `POST /ask` receives `include_resolver_shadow: true`, the response includes a `resolver_shadow` object beside the normal answer. The object contains:

- `actions`
- `reasons`
- `annotations`
- `diagnostics`
- `mutates_answer: false`
- `mutates_config: false`

The normal answer text is not changed.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_mode_regression.py
```

Result: pass, 7/7 cases.

After Hermes validation, a local OGCF bridge worklog was added to cover the remaining thin area without needing Hermes live runs:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_ogcf_bridge_worklog_fixture.py
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_ogcf_bridge_worklog_regression.py
```

Result: pass, 8/8 direct runtime-shadow cases.

The combined replay across Hermes-collected answer logs plus the new OGCF bridge worklog now passes 16/16 cases. The answer-feedback bank built from Hermes answer signals plus the OGCF bridge worklog now has three guarded-ready clusters and produces three guarded-ready proposals again:

- supported answer quality;
- bridge warning disclosure;
- missing-support refusal.

Threshold calibration was then added:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_threshold_calibration.py
```

The default calibration input is now the compact `resolver_shadow_outcome_dataset/v1` artifact when it exists. Raw ask/feedback logs can still be supplied explicitly with `--log` for traceability.

Result:

- 16 cases;
- 37 perfect threshold candidates;
- advisory strict candidate: bridge score `0.95`, effective affected-ratio `0.75`;
- current default `0.70/0.50` also passes all 16 cases.

No config change was made. Treat the strict candidate as evidence for future calibration, not as a promoted runtime setting.

Dataset/raw-log parity was then added:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_threshold_calibration_dataset_regression.py
```

Result: pass. It confirms dataset calibration and raw-log calibration produce the same 16-case label counts and the same recommended candidate.

The resolver-shadow outcome collector was then added:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_outcome_collector.py
```

Result:

- schema: `resolver_shadow_outcome_dataset/v1`;
- examples: 16;
- skipped: 0;
- bridge true positives: 4;
- bridge true negatives: 3;
- missing-support correct: 2;
- stale-disclosure correct: 2;
- supported-answer correct: 5.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_outcome_collector_regression.py
```

Result: pass. It validates both default thresholds and strict advisory thresholds over the same collected dataset.

## Interpretation

The answer-side neural-symbolic path has now advanced from:

```text
answer feedback signals -> memory bank -> guarded proposals -> shadow behavior eval
```

This is still not a runtime resolver implementation. It proves only that the guarded-ready proposal set can be simulated safely over controlled cases.

## Recommended Next Step

The next memory-session or Hermes task should not yet change user-facing answer behavior. It should test the configurable resolver-shadow mode during normal work:

- send `include_resolver_shadow: true` on ask calls;
- log the returned `resolver_shadow` object with answer-level feedback;
- compare shadow actions to labels such as `answer_correct`, `answer_bridge_warning_useful`, `answer_bridge_warning_noise`, `answer_stale`, and `answer_conflict_not_disclosed`;
- report false positive and false negative shadow actions.

Hermes can then compare the shadow annotations with normal answers during real work before the resolver changes any user-visible output.

Only after that should the memory-program session consider a configurable resolver-shadow mode that can emit proposed answer annotations without changing the user-facing answer by default.
