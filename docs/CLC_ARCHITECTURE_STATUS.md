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

The important finding is that the architecture can learn from real agent outcome logs without damaging known memory-boundary behavior, but only with conflict-safe admission and guard tests.

## Technological Value

The promising direction is a small, local, auditable controller for agent memory. Instead of retraining or scaling a large model, the system improves behavior by controlling memory operations:

- when to preserve old memory,
- when to refresh from verified current evidence,
- when stale evidence is dominating retrieval,
- when cost or budget pressure should block an update,
- when outcome labels are too conflicted to learn from.

This makes the architecture relevant for local agents, personal memory systems, tool-using orchestrators, and long-running assistants that need continual learning without expensive model training.

## Next Development Steps

1. Calibrate retrieval-derived selector features on larger real task sets:
   - stale/current retrieval ratio,
   - top evidence age/source reliability,
   - contradiction count,
   - supersession strength,
   - answer confidence and evidence coverage.

2. Build a holdout set that is not generated from the same scripts as training:
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

4. Add selector explanation data to outcome logs so future guarded training can learn from the same evidence the selector used.

5. Compare against stronger baselines:
   - fixed CLC rules,
   - recency-only memory,
   - vector-only retrieval,
   - full-context stuffing,
   - small LLM reranker.

## Current Publication State

The codebase is suitable to publish as an experimental prototype if runtime databases, logs, local models, and generated artifacts are not committed. The database is a local runtime artifact and should be regenerated or provided separately from GitHub source control.
