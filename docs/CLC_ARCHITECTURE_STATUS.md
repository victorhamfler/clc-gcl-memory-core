# CLC/CSD/G-CL Architecture Status

This repository is an experimental local AI memory architecture. Its strongest current form is not a new frontier-scale LLM; it is a low-compute memory-control layer that helps an agent decide when to trust retrieval, protect existing memory, or perform a verified refresh.

## Current Architecture

The active architecture combines:

- Embedding-backed memory using the local `embeddinggemma-300M-Q8_0.gguf` model.
- CSD diagnostics for novelty, contradiction pressure, domain shift, and stale/current conflict signals.
- G-CL domain geometry for drift, curvature, effective dimension, and domain stability.
- Symbolic domain/type hints for preference, procedure, design-rule, and work-memory routing.
- Retrieval reranking with vector, source, feedback, supersession, relation, intent, and reliability signals.
- A CLC learned policy selector that chooses between:
  - `periodic_baseline`
  - `long_severe_r16_overwrite`
  - `xseq_memory_r45_badmajority`
- A guarded continual selector trainer that admits outcome-log samples only when they are conflict-safe and preserve guard evaluations.
- A retrieval-feature bridge that can derive selector features from live retrieved evidence rows.
- Retrieval-aware guardrails that use live retrieval diagnostics to protect clean contexts, suppress query-irrelevant stale clutter, and force verified refresh for real stale/current conflict.
- Source-version grouping by source file, so unrelated files inside `agent_memory_v1` / `agent_memory_v2` do not mark each other stale.
- Canonical memory support signals and OGCF bridge-overload geometry can now both feed the selector feature layer.

## Best Current Selector

The current default selector training source is:

```text
selector_reports/clc_selector_guarded_continual_training_report.json
```

It contains 34 samples:

- 20 broad live policy-matrix samples.
- 6 hard stale-boundary samples.
- 8 conflict-safe outcome-log samples.

The raw outcome log was useful but unsafe by itself. It contained identical feature signatures with conflicting oracle policies. The guarded trainer skips those conflicts before creating a candidate training report.

## Evidence So Far

Guarded continual selector results:

| Selector | Matrix utility | Matrix pass | Matrix oracle | V2 utility | V2 pass | V2 oracle |
|---|---:|---:|---:|---:|---:|---:|
| Combined baseline | 19.91 | 1.0 | 0.95 | 5.91 | 1.0 | 1.0 |
| Guarded continual candidate | 19.91 | 1.0 | 0.95 | 5.91 | 1.0 | 1.0 |

Live endpoint smoke with the guarded continual report passed on a temporary server:

| Case | Policy |
|---|---|
| `hard_budget144` | `periodic_baseline` |
| `standard_budget144` | `long_severe_r16_overwrite` |
| `long2_hard_budget288` | `periodic_baseline` |
| `v2_stale_boundary` | `long_severe_r16_overwrite` |
| `high_label_cost_guard` | `periodic_baseline` |

The HTTP API also exposes `POST /selector_explain`, which returns normalized features, the selected policy, active guardrails, nearest training samples, vote totals, and which neighbors were counted in the `k=3` decision. The same endpoint can now derive selector features from either explicit `retrieval_context` rows or from a live `query` retrieval.

Live retrieval pipeline bridge result:

| Case | stale ratio | current ratio | conflict | Policy |
|---|---:|---:|---:|---|
| corrected preference query | 0.5 | 1.0 | 1.0 | `long_severe_r16_overwrite` |

Retrieval calibration harness:

| Eval | Cases | Before guards | Current hash | Current config | Main signal |
|---|---:|---:|---:|---:|---|
| `selector_retrieval_calibration_eval.py` | 6 | 0.5 | 1.0 | 1.0 | retrieval guards fix clean over-escalation and chained-correction underfire |
| `selector_retrieval_guard_pressure_eval.py` | 6 | n/a | 1.0 | 1.0 | irrelevant stale clusters and mild updates stay protected |
| `selector_retrieval_guard_randomized_eval.py` | 32 | 0.9375 during development | 1.0 | 1.0 | randomized corrections, chains, mild updates, and stale clutter align |

The important finding is that the architecture can learn from real agent outcome logs without damaging known memory-boundary behavior, but only with conflict-safe admission, retrieval-aware guardrails, and guard tests that include query-irrelevant stale clutter.

Canonical + OGCF checkpoint:

| Eval | Result | Main signal |
|---|---:|---|
| `canonical_ogcf_combined_eval.py` | pass | canonical support and OGCF bridge risk can be composed |
| `canonical_ogcf_answer_quality_eval.py` | pass | answer quality cases preserve expected behavior |
| `clc_policy_feature_signal_regression.py` | pass | feature-risk boundaries remain stable |
| `canonical_ogcf_policy_distribution_regression.py` | pass | canonical can protect clean support, OGCF can override bridge risk, duplicate pressure blocks protection |

Production-style shadow eval:

- `eval/canonical_ogcf_production_shadow_eval.py` runs a read-only four-mode comparison over a real or copied DB: base, canonical, OGCF, and combined.
- It uses stored embeddings as-is by default because the OGCF experiments found unnormalized geometry more stable and interpretable for bridge detection.
- First smoke run against `memory_experiment_180_best.db` succeeded, but all generated probes landed in `XSEQ_MEMORY_REFRESH`. That does not invalidate the architecture; it means the stress DB/generated probes are already severe before canonical or OGCF has room to produce visible policy flips.
- Next Hermes validation should provide a mixed real query set with clean support, mild stale clutter, bridge/conflict, and duplicate-pressure cases, preferably against a copied DB.
- `eval/build_rich_gemma_shadow_fixture.py` now builds a small Gemma-backed fixture with exact support, duplicate pressure, stale/current relations, diverse domains, and bridge-like cross-domain memories.
- The normalized Gemma fixture exercised canonical/retrieval behavior but produced no OGCF bridge clusters because stored vectors had unit norm. The raw-Gemma fixture produced a real bridge cluster across five domains and made OGCF change policy distribution.

Raw-Gemma rich fixture result:

| Mode | Policy distribution | Main signal |
|---|---|---|
| base | 9 protect, 2 verified refresh, 1 XSEQ | mixed retrieval conditions |
| canonical | 3 protect, 8 verified refresh, 1 XSEQ | duplicate pressure and canonical support changed 8/12 cases |
| OGCF | 4 protect, 7 verified refresh, 1 XSEQ | bridge-cluster affected ratio changed 5/12 cases |
| combined | 1 protect, 10 verified refresh, 1 XSEQ | OGCF changed 2 cases beyond canonical |

The raw fixture still has `bridge_overload_score=0.0`; the active OGCF signal came from bridge-cluster membership/affected-ratio, not loop interaction z-score. That is the next calibration target.

## Technological Value

The promising direction is a small, local, auditable controller for agent memory. Instead of retraining or scaling a large model, the system improves behavior by controlling memory operations:

- when to preserve old memory,
- when to refresh from verified current evidence,
- when stale evidence is dominating retrieval,
- when cost or budget pressure should block an update,
- when outcome labels are too conflicted to learn from.

This makes the architecture relevant for local agents, personal memory systems, tool-using orchestrators, and long-running assistants that need continual learning without expensive model training.

## Next Development Steps

1. Run multi-day continued-work testing with Hermes:
   - daily isolated namespaces,
   - one continuous namespace,
   - repeated teach/correct/ask/retrieve/selector-explain cycles,
   - full failure logging and final report.

2. Build a holdout set from real Hermes long-run failures, not generated from the same scripts as training:
   - real Hermes tasks,
   - personal preference changes,
   - project-memory corrections,
   - tool-rule updates,
   - multi-domain distraction cases.

3. Promote the guarded trainer into a normal maintenance workflow:
   - read outcome log,
   - build conflict-safe candidate,
   - run guard suites,
   - write an accepted report only if all guards pass.

4. Add selector explanation and retrieval diagnostics to outcome logs so future guarded training can learn from the same evidence the selector used.

5. Compare against stronger baselines:
   - fixed CLC rules,
   - recency-only memory,
   - vector-only retrieval,
   - full-context stuffing,
   - small LLM reranker.

6. Run the production shadow harness on real Hermes query logs:
   - use `py eval/canonical_ogcf_production_shadow_eval.py --db-path <copied-db> --queries-json <mixed-query-file> --query-limit 40 --ogcf-sample-limit 384 --top-k 8`,
   - confirm policy distribution is not collapsed,
   - inspect where canonical reduces risk and where OGCF raises risk,
   - repeat with `--normalize-embeddings` only as an ablation.

7. Calibrate OGCF affected-cluster pressure:
   - separate bridge-cluster membership from true loop overload,
   - avoid escalating unrelated queries that merely touch a bridge cluster,
   - preserve escalation for queries directly about bridge routing, OGCF geometry, stale/current interaction, or cross-domain selector policy.

## Current Publication State

The codebase is suitable to publish as an experimental prototype if runtime databases, logs, local models, and generated artifacts are not committed. The database is a local runtime artifact and should be regenerated or provided separately from GitHub source control.
