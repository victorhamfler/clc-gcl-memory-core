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
| OGCF | 6 protect, 5 verified refresh, 1 XSEQ | intent-aware bridge pressure changed 3/12 cases |
| combined | 2 protect, 9 verified refresh, 1 XSEQ | OGCF changed 1 case beyond canonical |

The raw fixture still has `bridge_overload_score=0.0`; the active OGCF signal came from bridge-cluster membership/affected-ratio, not loop interaction z-score. That is the next calibration target.

OGCF affected-pressure calibration:

- Bridge-cluster membership now reports raw, relevance-weighted, and effective affected-memory ratios.
- True loop overload still bypasses the membership gate and can raise memory-bad-rate directly.
- Bridge-cluster-only pressure is gated by relevance so weak incidental bridge membership does not add feature pressure.
- On the raw-Gemma fixture, OGCF-only deltas dropped from 5/12 to 2/12, and combined-vs-canonical extra deltas dropped from 2/12 to 0/12.
- `eval/ogcf_affected_pressure_calibration_regression.py` protects this behavior.

OGCF query/evidence intent gate:

- `core/ogcf_intent.py` classifies whether a query is an ordinary fact lookup, memory-maintenance question, cross-domain bridge synthesis, or explicit OGCF geometry query.
- The first intent controller is now configurable through the `ogcf_intent` section in `config.yaml`.
- Config includes bridge/geometry/maintenance/ordinary term vocabularies, intent scores, and affected-cluster gate thresholds.
- The selector now passes query text into OGCF feature augmentation when available.
- Weak passive bridge-cluster membership stays gated for ordinary calendar/profile/procedure questions.
- Explicit bridge/OGCF geometry questions can use bridge-cluster pressure even when there is no true loop-overload z-score.
- True loop overload still bypasses the intent gate.
- `eval/ogcf_intent_gate_regression.py` protects the three important cases: ordinary lookup suppression, explicit geometry escalation, and true-loop bypass.
- `eval/ogcf_intent_config_regression.py` proves new bridge terms and gate behavior can be changed through config without editing source code.
- `eval/mine_ogcf_intent_candidates.py` now mines dry-run `ogcf_intent_candidates/v1` artifacts from linked ask/feedback logs. Current local logs have no OGCF-specific feedback labels yet, so they produce zero candidates; Hermes needs to add these labels in future runs.
- The memory-session OGCF outcome workflow confirms the linked label loop works end to end. The selector-side miner now filters generic workflow terms before candidate emission, so controlled signals like `meshlink`, `manifolddrift`, `pruneflow`, and `lunar` remain while terms such as `note`, `memo`, `evidence`, `reviewed`, and `pressure` are suppressed.
- The memory-session neural-symbolic outcome workflow now emits answer-level feedback, answer holdout candidates, and non-empty OGCF diagnostics. `eval/answer_feedback_signal_eval.py` consumes this log into report-only `answer_feedback_controller_signals/v1` artifacts for future resolver/controller learning.
- `eval/answer_feedback_memory_bank.py` now aggregates multiple answer-feedback signal artifacts into a report-only `answer_feedback_memory_bank/v1`. The first local multi-run test found ready clusters for supported answer quality, useful bridge warnings with OGCF metadata, and missing-support refusal behavior.
- `eval/answer_feedback_bank_guard.py` now guards those ready clusters before any future resolver or answer-warning behavior change. It verifies bridge-warning clusters have OGCF diagnostics, supported-answer clusters have selected evidence, missing-support clusters do not contain selected memories or positive feedback, mixed-outcome clusters are not plain-ready, and the bank remains report-only.
- `eval/answer_behavior_proposal_eval.py` now converts guarded answer-feedback memory-bank clusters into report-only `answer_behavior_proposals/v1` artifacts. The first proposal artifact suggests three testable behavior candidates: evidence-backed supported answers, OGCF bridge-risk warnings when supported, and missing-support refusal preservation.
- `eval/answer_behavior_proposal_guard.py` now checks those proposals before any resolver implementation. It confirms the proposals are report-only, evidence-backed answers require selected evidence, bridge-warning proposals require OGCF and ordinary-lookup suppression guards, and missing-support refusal proposals do not encourage hallucinated answers from weak raw candidates.
- `eval/answer_behavior_shadow_eval.py` now simulates those guarded-ready answer behaviors over controlled answer cases before any resolver change. The first shadow pass covers evidence-backed supported answers, OGCF bridge-risk warnings, ordinary bridge-word suppression, missing-support refusal preservation, and stale-conflict disclosure. Current local result: 5/5 cases passed, with no runtime or config mutation.
- `eval/answer_behavior_real_log_shadow_replay.py` now replays the same guarded-ready answer behavior over linked ask/answer-feedback logs. The first replay passed 3/3 linked answer cases from the neural-symbolic workflow: supported answer, useful OGCF bridge warning, and missing-support refusal.
- `eval/answer_behavior_real_log_fixture.py` now creates a linked ask/answer-feedback fixture for the missing answer-behavior safety labels. Combined replay now passes 8/8 cases across supported answers, useful bridge warnings, bridge-warning noise suppression, missing-support refusal, stale-answer disclosure, conflict-not-disclosed disclosure, bad citation, and wrong-scope labels. The fixture is still report-only and exists to validate the log contract before Hermes produces more natural examples.
- `core/answer_behavior_shadow.py` now implements the first configurable resolver-shadow mode. `POST /ask` can include `resolver_shadow` when requested or when `resolver_shadow.enabled` is set in config. It emits report-only proposed actions and annotations beside the current answer, but does not change answer text, resolver ranking, runtime config, selector policy, or memory rows. Current regression passes 7/7 cases.
- On the raw-Gemma fixture, the intent gate kept ordinary fact queries protected while letting bridge synthesis and OGCF geometry questions escalate; combined-vs-canonical now has one targeted extra delta.

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

7. Replace the configurable symbolic OGCF intent classifier with a learned neural-symbolic controller:
   - collect query/evidence/decision/outcome rows from Hermes,
   - mine candidate bridge/geometry/maintenance terms and score shifts into a candidate artifact,
   - label OGCF false positives explicitly when ordinary factual queries should remain protected,
   - filter or reject generic terms before readiness evaluation,
   - parse answer-level feedback into holdout/controller signals before training resolver behavior,
   - aggregate answer-feedback signals across runs before promoting resolver or warning behavior,
   - train or calibrate a small local intent scorer against guard labels,
   - keep the current config-backed classifier as the transparent fallback.

8. Run the production shadow harness on real Hermes query logs with the new intent diagnostics:
   - inspect `ogcf_intent`, `ogcf_intent_score`, and `ogcf_effective_affected_memory_ratio`,
   - confirm ordinary factual queries are protected,
   - confirm bridge-maintenance and OGCF geometry queries receive pressure only when retrieved evidence supports it.

## Current Publication State

The codebase is suitable to publish as an experimental prototype if runtime databases, logs, local models, and generated artifacts are not committed. The database is a local runtime artifact and should be regenerated or provided separately from GitHub source control.
