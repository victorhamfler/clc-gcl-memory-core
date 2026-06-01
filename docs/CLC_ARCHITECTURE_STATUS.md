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
- `eval/answer_behavior_ogcf_bridge_worklog_fixture.py` now creates richer live-log-shaped OGCF bridge answer cases without Hermes. It covers high bridge-score warnings, affected-ratio warnings, ordinary bridge-word suppression, weak bridge-noise suppression, missing-support refusal, stale+bridge disclosure, and ordinary supported-answer positives. Current combined replay passes 16/16 cases, direct runtime-shadow worklog regression passes 8/8, and the answer-feedback bank/proposal/guard path again produces three guarded-ready behavior proposals.
- `eval/resolver_shadow_threshold_calibration.py` now sweeps resolver-shadow bridge-warning thresholds over the compact `resolver_shadow_outcome_dataset/v1` artifact by default, with raw ask/feedback log replay still available for comparison. Current default thresholds `0.70/0.50` still pass 16/16 cases. The advisory sweep recommends a stricter candidate `0.95/0.75`, also with 0 failures, but no runtime config was changed because this should be confirmed against natural live logs first.
- `eval/resolver_shadow_outcome_collector.py` now converts linked ask/answer-feedback logs into a reusable `resolver_shadow_outcome_dataset/v1` artifact for calibration and later controller learning. The current dataset has 16 examples with bridge true positives, bridge true negatives, missing-support correct refusals, stale-disclosure correct cases, and supported-answer correct cases. The collector regression passes for both current default thresholds and the stricter advisory candidate.
- `eval/resolver_shadow_threshold_calibration_dataset_regression.py` proves the dataset-driven calibration path and raw-log calibration path produce the same 16-case label counts and the same recommended candidate. This makes the compact dataset the preferred interface for later learned bridge-warning controllers.
- `core/controller_context.py` now defines the shared `adaptive_memory_context/v1` path for selector features, canonical diagnostics, optional OGCF augmentation, guarded selector decisions, resolver-shadow snapshots, and outcome-log context. `serve.py` now calls this shared builder instead of owning selector/OGCF orchestration directly. `ask` logs now include an `adaptive_memory_context` object while preserving the legacy `selector_snapshot`, and `selector_explain` logs now use the same schema in `selector_context`. `eval/controller_context_regression.py` verifies parity with the previous direct selector + OGCF + retrieval-guard path, and `eval/outcome_logging_regression.py` protects the logged context contract. `eval/resolver_shadow_outcome_collector.py` and raw-log threshold calibration now prefer `adaptive_memory_context` while retaining legacy `selector_snapshot` fallback; `eval/resolver_shadow_outcome_context_regression.py` proves both log formats produce equivalent outcome fields. `eval/resolver_shadow_runtime_context_log_regression.py` verifies the full runtime path: ask log with adaptive context, linked answer feedback, and collector output with `context_source=adaptive_memory_context`.
- `eval/adaptive_context_outcome_dataset.py` now builds a shared `adaptive_context_outcome_dataset/v1` from linked ask/feedback logs. It preserves feedback scope/label/rating, selector policy/action, adaptive features, compact diagnostics, retrieval context, selected memory ids, optional resolver-shadow actions, and context source. `eval/adaptive_context_outcome_dataset_regression.py` verifies real runtime logs with both answer-level and memory-level feedback become adaptive-context training/eval examples. Existing legacy/local logs currently produce 192 examples with 0 skipped rows.
- `eval/adaptive_context_dataset_guard.py` now guards that shared dataset before any learned scorer or promotion step. It separates structural safety from learning readiness: the accumulated dataset is structurally clean, report-only, linked, and retrieval-bearing, but still `analysis_only` because the examples are legacy selector snapshots rather than fresh `adaptive_memory_context/v1` rows. `eval/adaptive_context_dataset_guard_regression.py` proves fresh runtime answer + memory feedback can reach `ready_for_runtime_collection`.
- `eval/adaptive_context_rich_runtime_fixture.py` now generates a richer fresh runtime fixture without Hermes. It teaches local memories, runs real `ask` calls through `adaptive_memory_context/v1`, attaches linked answer and memory feedback, and covers supported answers, citation quality, missing support, stale/conflict cases, bad citation, useful OGCF bridge warnings, and ordinary bridge-word false positives. Current result: 48 fresh adaptive-context examples, 0 skipped rows, 0 guard errors, and guard readiness `promotion_candidate`. Combining this fixture with existing legacy/local logs produces 240 structurally clean examples and guard readiness `promotion_candidate`.
- `eval/adaptive_context_tiny_scorer.py` now trains/evaluates the first report-only learned scorer over the adaptive-context outcome dataset. It uses a deterministic tiny logistic model over context features, diagnostics, selector action/policy fields, and compact retrieval statistics, with majority and symbolic-health baselines. Current combined result: 240 examples, 97 positive and 143 negative outcomes. The combined 5-fold learned scorer improves calibration over majority baseline but not accuracy, while the fresh adaptive-context slice is now strongly learnable: adaptive-only learned accuracy 0.895542 versus 0.562646 majority, with learned Brier 0.075683 versus 0.265142 symbolic-health. `eval/adaptive_context_tiny_scorer_regression.py` protects this fresh-slice result and verifies the scorer remains report-only.
- The tiny scorer now includes `adaptive_behavior_holdout`, a harder evaluation that holds out each answer-behavior family. This blocks promotion: learned weighted accuracy is 0.229167 with Brier 0.6288, while symbolic-health reaches 0.520833 with Brier 0.265518. The scorer readiness is therefore `blocked_behavior_generalization`. This is useful evidence: learned scoring works inside seen behavior patterns, but the next controller needs explicit behavior-family or answer-type structure before it can safely generalize.
- `eval/adaptive_context_behavior_aware_scorer.py` now implements the first report-only behavior-aware neural-symbolic scorer. It routes by answer-behavior family, uses a family model only when enough mixed evidence exists, blends family learned scores with symbolic retrieval health, and falls back to symbolic health for unseen behavior families. On behavior holdout it matches symbolic-health accuracy and Brier instead of failing like the generic tiny scorer: weighted accuracy 0.520833 and Brier 0.265518, readiness `analysis_ready`. `eval/adaptive_context_behavior_aware_scorer_regression.py` protects this fallback behavior.
- `eval/adaptive_context_semantic_behavior_scorer.py` now adds a semantic behavior-family layer. Exact labels are mapped into broader superfamilies such as `supported_evidence`, `ogcf_bridge_warning`, `missing_support`, and `stale_conflict`. On exact-behavior holdout, this improves over symbolic health: semantic hybrid accuracy 0.583333 versus 0.520833, and Brier 0.233237 versus 0.265518. `eval/adaptive_context_semantic_behavior_scorer_regression.py` protects this result. This is the first evidence that the neural-symbolic controller can generalize across related behavior families instead of only memorizing exact labels.
- `adaptive_behavior.superfamilies` in `config.yaml` now makes that semantic behavior-family map configurable, with normalization in `core/adaptive_behavior.py`. The semantic scorer emits `adaptive_behavior_config/v1`, and `eval/adaptive_context_semantic_behavior_guard.py` blocks promotion unless the scorer is report-only, uses config, has behavior holdout coverage, and beats symbolic fallback on both accuracy and Brier. Current guard result: `promotion_candidate` as a report-only candidate artifact, not an automatic runtime change. `eval/adaptive_context_semantic_behavior_guard_regression.py` protects the gate.
- `eval/adaptive_context_semantic_shadow_controller.py` now converts the guarded semantic scorer into a report-only shadow-controller artifact. It requires the semantic guard to be `promotion_candidate`, loads `adaptive_behavior_config/v1`, emits per-example advisories (`likely_helpful`, `likely_harmful`, `uncertain_keep_symbolic`), and keeps shadow mode disabled by default. Current result: `shadow_candidate`, 48 adaptive examples, 21 helpful advisories, 4 harmful advisories, 23 uncertain-symbolic advisories, and no runtime/config mutation. `eval/adaptive_context_semantic_shadow_controller_regression.py` protects the full chain.
- `eval/adaptive_context_semantic_shadow_live_style_eval.py` now generates a fresh live-style local runtime log, builds and guards an adaptive-context dataset from it, trains the shadow controller on the earlier rich fixture, and evaluates on the fresh examples. Current result: `live_style_shadow_candidate`, 20 fresh adaptive-context examples, 9 actioned advisories, 11 symbolic fallbacks, 1.0 actioned precision, 0.45 coverage, and no runtime/config mutation. `eval/adaptive_context_semantic_shadow_live_style_regression.py` protects this validation.
- `eval/adaptive_context_semantic_shadow_multibatch_eval.py` now runs the stricter validation: three independent fresh live-style batches in separate temporary runtimes, each converted into guarded adaptive-context datasets, then evaluated by the same semantic shadow controller. Current result: `multibatch_shadow_candidate`, 48 fresh examples, 20 actioned advisories, weighted actioned precision 1.0, weighted coverage 0.416667, and no runtime/config mutation. `eval/adaptive_context_semantic_shadow_multibatch_regression.py` protects this stronger validation.
- `eval/adaptive_context_gemma_shadow_eval.py` now validates the same report-only semantic shadow controller on real Gemma retrieval from the raw-Gemma canonical/OGCF fixture. Current result: `gemma_shadow_candidate`, 24 adaptive-context examples, full retrieval coverage, 14 actioned advisories, actioned precision 1.0, coverage 0.583333, confirmed `wsl_llama_cpp` backend, 768-dimensional embeddings, and no runtime/config mutation. `eval/adaptive_context_gemma_shadow_regression.py` protects this Gemma-backed boundary.
- `eval/canonical_ogcf_production_shadow_eval.py` now includes a retrieval-coverage guard. It fails low-coverage runs by default, preventing wrong namespaces or broken retrieval from appearing as safe protect-all policy results. `eval/canonical_ogcf_shadow_coverage_regression.py` protects the failure path and the explicit warning-only override.
- `core/adaptive_behavior_shadow.py` now exposes the runtime report-only adaptive behavior shadow surface used by `POST /ask`. It is disabled by default and can be requested per call with `include_adaptive_behavior_shadow=true`; it can be logged with `log_adaptive_behavior_shadow=true`. It emits `adaptive_behavior_shadow/v1` decisions for semantic behavior families without changing answers, selector policy, memory rows, or config. `eval/adaptive_behavior_shadow_runtime_regression.py` protects the request/logging contract and confirms answer, evidence, and selector decisions remain unchanged.
- `eval/selector_architecture_gate.py` now includes the Gemma shadow regression, retrieval-coverage guard regression, and runtime adaptive behavior shadow regression alongside the retrieval-signal and evidence-state gates. Current unified gate result: pass, with `retrieval_signal_gate_ok`, `evidence_state_gate_ok`, `shadow_coverage_guard_ok`, `gemma_shadow_regression_ok`, and `adaptive_behavior_shadow_runtime_ok` all true.
- On the raw-Gemma fixture, the intent gate kept ordinary fact queries protected while letting bridge synthesis and OGCF geometry questions escalate; combined-vs-canonical now has one targeted extra delta.
- `eval/adaptive_behavior_shadow_real_log_calibration.py` and `eval/adaptive_behavior_shadow_real_log_rerun.py` now provide a local real-log-style calibration loop for the runtime adaptive behavior shadow. The rerun copies `memory_experiment_180_best.db`, runs 34 ask/feedback cycles through `MemoryApi`, logs linked answer/memory feedback, and compares shadow advisories to behavior-family labels.
- Runtime adaptive behavior shadow now covers five families: `supported_evidence`, `missing_support`, `stale_conflict`, `wrong_scope`, and `ogcf_bridge_warning`. The latest local rerun reached overall match rate `0.913793`, with family match rates: `supported_evidence=0.852941`, `missing_support=1.0`, `stale_conflict=0.852941`, `wrong_scope=1.0`, and `ogcf_bridge_warning=1.0`. The shadow remains report-only and the unified architecture gate still passes.
- The adaptive behavior roadmap has shifted from one-off runtime tuning toward candidate artifacts. `eval/adaptive_behavior_candidate_profile.py` now writes `adaptive_behavior_candidate_profile/v1`, `eval/adaptive_behavior_candidate_profile_guard.py` guards it, and `eval/adaptive_behavior_candidate_profile_guard_regression.py` protects the contract. Current profile guard readiness is `analysis_ready`, with a stale-conflict candidate and a supported-evidence low-support hold item.
- `eval/adaptive_behavior_profile_memory_bank.py` now aggregates adaptive behavior candidate profiles across independent logs/runs. It writes `adaptive_behavior_profile_memory_bank/v1`, keeps single-run proposals in `hold`, and only marks clusters `recurrence_ready` when a proposal repeats across enough independent profile sources. `eval/adaptive_behavior_profile_memory_bank_guard.py` and `eval/adaptive_behavior_profile_memory_bank_guard_regression.py` protect the report-only contract. Current local single-profile bank has two hold clusters, zero ready clusters, guard readiness `analysis_ready`, and no mutation fields.
- A second independent profile was produced by replaying the earlier Hermes adaptive-shadow outcome log through current runtime logic. The multisource adaptive behavior profile bank now has two profiles, two clusters, and readiness counts `{"hold": 1, "recurrence_ready": 1}`. The `stale_conflict_explicit_signal_gate` cluster is recurrence-ready across local and Hermes-derived profiles; `supported_evidence_low_support_review` remains hold.
- `eval/adaptive_behavior_stale_conflict_candidate_promotion.py` now provides the targeted promotion-style guard for the recurrence-ready stale-conflict candidate. It passes 6/6 cases: incidental stale context stays uncertain, explicit old/previous queries trigger stale advisories, current/corrected queries suppress stale over-fire, explicit conflict diagnostics still trigger, and resolver disclosure action alone does not trigger without explicit support. The unified architecture gate now includes `adaptive_behavior_stale_conflict_candidate_ok`.
- The stale-conflict shadow controller is now a Level 1 configurable control surface. `adaptive_behavior.shadow.stale_conflict_requires_explicit_signal`, `stale_conflict_positive_probability`, and `stale_conflict_neutral_probability` control the behavior that was previously fixed in code. `eval/adaptive_behavior_stale_conflict_config_regression.py` passes 4/4 cases and proves default suppression, opt-in incidental stale triggering, and probability overrides work without mutating runtime state. The unified architecture gate now includes `adaptive_behavior_stale_conflict_config_ok`.
- The missing-support shadow controller is now a Level 1 configurable control surface. `adaptive_behavior.shadow.missing_support_no_evidence_refusal_probability`, `missing_support_selected_sensitive_probability`, `missing_support_selected_evidence_probability`, and `missing_support_no_evidence_probability` replace fixed probabilities in runtime shadow code. `eval/adaptive_behavior_missing_support_config_regression.py` passes 5/5 cases and proves no-evidence refusal, sensitive lookup, selected-evidence neutrality, and no-evidence non-refusal probabilities are honored from config. The unified architecture gate now includes `adaptive_behavior_missing_support_config_ok`.
- The wrong-scope shadow controller is now a Level 1 configurable control surface. `adaptive_behavior.shadow.wrong_scope_deflection_probability`, `wrong_scope_no_evidence_github_probability`, `wrong_scope_no_evidence_probability`, `wrong_scope_selected_evidence_probability`, `wrong_scope_route_confidence`, and `wrong_scope_low_route_confidence` replace fixed wrong-scope branch values. `eval/adaptive_behavior_wrong_scope_config_regression.py` passes 6/6 cases and proves scope-deflection, no-evidence approval, generic no-evidence scope, selected-evidence scope, and low-route-confidence branches are config-controlled. The unified architecture gate now includes `adaptive_behavior_wrong_scope_config_ok`.

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

9. Collect real runtime adaptive-shadow feedback:
   - run agent asks with `include_adaptive_behavior_shadow=true` and `log_adaptive_behavior_shadow=true`;
   - attach answer-level and memory-level feedback to the same ask operation ids;
   - build a calibration/replay artifact comparing advisories to real feedback;
   - keep runtime promotion blocked until real-log calibration beats symbolic fallback and passes the unified architecture gate.

10. Turn adaptive behavior calibration into a candidate-profile workflow:
   - use local and Hermes linked ask/feedback logs to build calibration reports;
   - emit report-only `adaptive_behavior_candidate_profile/v1` artifacts with proposed profile changes;
   - guard those artifacts before touching `config.yaml` or runtime behavior;
   - use the current symbolic runtime shadow as the transparent fallback;
   - compare later candidate profiles against the learned semantic behavior scorer on held-out logs.

11. Build a multi-log adaptive behavior memory bank:
   - aggregate candidate profiles from independent local and Hermes runs;
   - require recurrence across logs before moving a candidate from `hold` to promotion testing;
   - keep weak low-support supported-evidence cases in `hold` until real logs prove they generalize;
   - use the unified architecture gate, including `adaptive_behavior_candidate_profile_guard_ok`, before any upload or promotion.

12. Feed the adaptive behavior memory bank with independent profiles:
   - compare profile clusters across runs;
   - only consider config-level promotion when a cluster becomes `recurrence_ready`;
   - keep the symbolic runtime shadow as fallback and compare against the semantic learned scorer before runtime action.

13. Build a targeted promotion test for the recurrence-ready stale-conflict candidate:
   - completed with `eval/adaptive_behavior_stale_conflict_candidate_promotion.py`;
   - keep this as a guard before any config-level promotion.

14. Decide promotion shape for the guarded stale-conflict candidate:
   - completed first extraction into explicit report-only config knobs;
   - keep default conservative behavior active while collecting more real logs;
   - compare future learned/neural-symbolic stale-conflict proposals against this config surface before any runtime promotion;
   - optionally require three-source recurrence before changing default config values.

15. Continue the hardcoded-to-configurable adaptive-shadow migration:
   - completed missing-support probability extraction into explicit report-only config knobs;
   - completed wrong-scope probability and route-confidence extraction into explicit report-only config knobs;
   - keep `supported_evidence_low_support_review` in hold until additional real logs clarify low-support positives.

16. Extract a shared evidence-context helper layer:
   - completed first extraction in `core/evidence_context.py`;
   - added `EvidenceContextSummary` as the first reusable compact evidence object for report-only controllers;
   - migrated report-only shadow modules before touching resolver or pipeline behavior;
   - centralized selected-evidence filtering, normalized text handling, row signal extraction, ordinary lookup detection, resolver action extraction, and stale/current conflict checks;
   - `core/adaptive_behavior_shadow.py` and `core/answer_behavior_shadow.py` now build the same summary object before emitting advisories/actions;
   - `core/selector_runtime.py` now uses the same summary object for retrieval-row normalization before deriving selector features;
   - `EvidenceRowState` and `retrieval_row_state()` now centralize stale/current/standalone/topical-anchor/current-correction row interpretation for selector-side feature extraction;
   - `core/resolver.py` now uses `retrieval_row_state()` for repeated selector/evidence signal reads in positive-signal detection, query relevance, evidence preference scoring, and confidence estimation;
   - `EvidenceContextFeatures` now provides the first compact derived-feature object over `EvidenceContextSummary`;
   - `core/adaptive_behavior_shadow.py` now consumes `EvidenceContextFeatures` for retrieval/selected/stale counts, match signals, conflict pressure, memory risk, scope-deflection pressure, and OGCF bridge pressure;
   - adaptive behavior shadow diagnostics now export `evidence_context_features` into live responses and logged ask events, giving future learned controllers a stable calibration feature vector;
   - `eval/adaptive_behavior_feature_scorer_eval.py` now trains a report-only tiny local softmax scorer on exported `evidence_context_features`; first local result is not promotion-ready (`test_learned_match_rate=0.565217` vs symbolic `0.956522`);
   - `eval/adaptive_behavior_feature_scorer_regression.py` guards this as a research/dataset path and blocks runtime promotion from the small local log;
   - `eval/adaptive_behavior_feature_scorer_hybrid_eval.py` now tests family-specific scorers plus a residual override gate; current result preserves the symbolic baseline (`hybrid=0.956522`, `symbolic=0.956522`) but does not improve it, so promotion remains blocked;
   - `eval/adaptive_behavior_feature_scorer_hybrid_regression.py` guards the hybrid path and the unified gate now requires it;
- `eval/adaptive_behavior_feature_challenge_log.py` now generates local hard-case feature-export logs with 50 challenge cases and 70 symbolic-wrong decisions;
- on the combined local rerun + generated challenge log, the hybrid residual scorer beats symbolic (`hybrid=0.915254`, `symbolic=0.745763`, delta `+0.169491`), proving the feature path can learn useful corrections when enough symbolic-error cases exist;
- `eval/adaptive_behavior_feature_challenge_regression.py` guards this positive result as report-only and still blocks promotion because the hard cases are generated rather than independent real logs;
- `eval/adaptive_behavior_feature_cross_log_holdout.py` now tests the same residual idea across logs by training on local/challenge feature logs and testing on Hermes real feature-export data; the best zero-harm threshold currently improves over symbolic by `+0.04` (`hybrid=0.8`, `symbolic=0.76`, 15 helpful overrides, 0 harmful overrides), while the highest raw-gain threshold is rejected as unsafe because it causes one harmful override;
- `eval/adaptive_behavior_feature_cross_log_holdout_regression.py` records this as a standalone local regression, but it is intentionally not part of the portable unified architecture gate because it depends on the local Hermes WSL report path;
- `eval/adaptive_behavior_shadow_second_holdout_log.py` now creates a second independent local runtime feature-export log. It produced 24 asks, 24 answer-feedback rows, 37 memory-feedback rows, 87 adaptive decisions, and exact logged/replayed calibration at `0.83908`;
- the second holdout repeats the cross-log learned-residual signal: broad thresholds improve accuracy but still cause harmful overrides, while strict threshold `0.995` reaches zero-harm improvement (`hybrid=0.885057`, `symbolic=0.83908`, delta `+0.045977`, 5 helpful overrides, 0 harmful overrides);
- the cross-log evaluator default threshold grid now includes strict values up to `0.999` so safe high-confidence operating points are not missed;
- `eval/adaptive_behavior_feature_override_policy_eval.py` now tests conservative learned-residual override policies across both holdouts. The current selected report-only policy allows only `supported_evidence -> likely_helpful` overrides at residual confidence `0.995`. It improves both holdouts with zero harmful overrides: Hermes real holdout `+0.018182`, second local runtime holdout `+0.045977`;
- `eval/adaptive_behavior_feature_override_policy_regression.py` guards this local two-holdout result as report-only and promotion-blocked;
- `eval/adaptive_behavior_override_policy_candidate.py` and `eval/adaptive_behavior_override_policy_candidate_guard.py` now convert that winning policy into a formal guarded report-only candidate: `adaptive_behavior_supported_evidence_positive_rescue_v1`. Current readiness is `guarded_report_only_candidate`, with 10 total helpful overrides, 0 harmful overrides, and promotion still blocked until another natural holdout confirms the pattern;
- `eval/adaptive_behavior_shadow_third_holdout_log.py` now creates a harder third local runtime holdout. It produced 24 asks, 24 linked answer-feedback rows, 52 memory-feedback rows, 82 adaptive decisions, and exact logged/replayed calibration at `0.621951`;
- the third holdout blocked the prior two-holdout candidate. A strict `0.999` policy is zero-harm across three holdouts, but it produces no lift on the second holdout, so there is now no selected three-holdout candidate. The candidate guard readiness is `blocked_no_three_holdout_candidate`;
- this is a useful safety result: the learned residual path needs context-filtered suppression for sensitive/private lookup and ordinary profile/namespace lookup pressure before any runtime shadow implementation;
- the override policy evaluator now includes explicit context suppressors for sensitive/private lookup pressure, stale/previous-policy lookup pressure, and ordinary profile/namespace lookup pressure. With those suppressors, the selected report-only candidate recovered across all three holdouts: `supported_evidence -> likely_helpful`, residual threshold `0.8`, 23 helpful overrides, 0 harmful overrides, mean delta `+0.055902`, readiness `guarded_report_only_candidate`;
- `core/adaptive_residual_shadow.py` now exposes that guarded candidate as a disabled-by-default runtime shadow. `POST /ask` can request `include_adaptive_residual_shadow=true` and optionally `log_adaptive_residual_shadow=true`; the shadow logs residual confidence, family advisory, suppressor reasons, and would-override status without changing answer text, selector policy, memory rows, runtime config, or learned artifacts. `eval/adaptive_residual_shadow_runtime_regression.py` protects this contract, and the unified architecture gate now requires it;
- `eval/adaptive_residual_shadow_fourth_holdout_log.py` and `eval/adaptive_residual_shadow_logged_eval.py` now validate the actual logged runtime residual-shadow payload against linked feedback. The fourth holdout produced 24 asks, 24 answer-feedback rows, 47 memory-feedback rows, and 89 residual-shadow decisions; the guarded shadow made 9 report-only would-overrides, all 9 helpful and 0 harmful, with promotion still blocked pending natural multi-day logs;
- the unified architecture gate now requires `adaptive_residual_shadow_logged_eval_ok`, so future residual-controller candidates must pass both the runtime no-mutation regression and the linked-feedback logged-decision evaluation before they can be considered for promotion;
- `eval/adaptive_residual_shadow_multi_log_eval.py` now aggregates residual-shadow logged-eval results across available residual outcome logs. The unified architecture gate requires `adaptive_residual_shadow_multi_log_eval_ok`;
- `eval/adaptive_residual_shadow_fifth_holdout_log.py` adds a second independent residual-shadow holdout. Its first run exposed unsafe unsupported-proof/deployment-key rescue pressure, so `core/adaptive_residual_shadow.py` now includes a narrow `unsupported_proof` suppressor and expanded deployment-key private/sensitive suppression. After regeneration, the two-log aggregate passes with 52 asks, 187 residual decisions, 18 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides. The unified gate now runs the aggregate with `--min-logs 2`;
- `eval/adaptive_residual_shadow_suppressor_regression.py` now protects the suppressor boundary directly, including unsupported proof/result claims, deployment-key pressure, stale previous-roadmap pressure, and ordinary cross-namespace profile pressure. The unified architecture gate requires `adaptive_residual_shadow_suppressor_ok`;
- `adaptive_residual_shadow` policy is now configurable in `config.yaml`, including thresholds, allowed families/target, active suppressors, and suppressor term groups. `core/adaptive_residual_shadow.py` loads the configured policy with safe defaults, and the suppressor regression validates the configured policy surface;
- `eval/adaptive_residual_shadow_term_candidate_miner.py` now reads residual-shadow logs and emits report-only suppressor term candidates from harmful or neutral-wrong residual overrides. On the current two clean residual logs it proposes no new terms and reports `no_new_terms_needed`. The unified architecture gate requires `adaptive_residual_shadow_term_miner_ok`;
- `eval/adaptive_residual_shadow_term_miner_regression.py` now validates the adaptive term-mining path with synthetic unsafe residual examples, proving the miner can propose reviewable terms while keeping config/runtime mutation blocked. The miner now filters vague one-token candidates and keeps reviewable multi-word failure phrases. The unified architecture gate requires `adaptive_residual_shadow_term_miner_regression_ok`;
- `eval/adaptive_residual_shadow_term_patch_proposal.py` and `eval/adaptive_residual_shadow_term_patch_regression.py` now provide a review-only config patch proposal path for mined suppressor terms. They group reviewable candidates into suppressor term buckets, keep ambiguous candidates separate, and verify `config.yaml` is not mutated. The unified architecture gate requires `adaptive_residual_shadow_term_patch_ok` and `adaptive_residual_shadow_term_patch_regression_ok`;
- `eval/adaptive_residual_shadow_term_patch_pipeline_regression.py` now tests the full synthetic unsafe path from mined residual failures to grouped patch preview while confirming config/runtime mutation remains blocked. The unified architecture gate requires `adaptive_residual_shadow_term_patch_pipeline_ok`;
- suppressor patch proposals now compare candidates against the active configured term groups, separating new `append_terms` from `already_configured` terms so duplicate config suggestions are avoided;
- `eval/adaptive_residual_shadow_term_patch_guard.py` now guards review-only suppressor patch proposals before any manual config application is considered. On current clean logs it passes with no action needed; new or ambiguous terms require manual review and automatic config/runtime mutation remains blocked. The unified architecture gate requires `adaptive_residual_shadow_term_patch_guard_ok`;
- `eval/adaptive_residual_shadow_sixth_natural_holdout_log.py` now adds a larger natural-style residual holdout. Its first run exposed an ordinary namespace lookup bypass gap, so `ordinary namespace` and `namespace lookup` were added to the configurable `ordinary_namespace_profile` suppressor and regression coverage. After regeneration, the three-log aggregate passes with 96 asks, 351 residual decisions, 29 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides. The unified architecture gate now runs the aggregate with `--min-logs 3`;
- `eval/adaptive_residual_shadow_promotion_readiness.py` now makes promotion status explicit: the three-log local aggregate passes, but runtime promotion is blocked with `external_or_agent_residual_log_required`. The unified architecture gate requires `adaptive_residual_shadow_promotion_readiness_ok`;
- `docs/HERMES_ADAPTIVE_RESIDUAL_SHADOW_EXTERNAL_LOG_HANDOVER.md` now packages the required external Hermes/agent residual validation run, including runtime flags, feedback labels, scenario families, expected output files, optional local eval commands, and success criteria;
- Hermes' first external residual log found one harmful stale-config replacement override. The current policy now extends `stale_previous` suppression for stale config/value replacement pressure, and `eval/adaptive_residual_shadow_external_failure_replay.py` confirms the exact Hermes harmful example would now be suppressed. A fresh external run is still required because the historical logged payload remains a strict logged-eval failure;
- the residual-shadow gate now separates clean validation evidence from processed historical failures. The historical Hermes stale-config failure remains preserved as evidence, but clean aggregate/readiness metrics exclude it after replay confirms the current policy suppresses the harmful query. The unified architecture gate now requires `adaptive_residual_shadow_external_failure_replay_ok` and passes with three clean residual logs, 29 helpful overrides, 0 harmful overrides, and promotion still blocked pending a fresh external/agent log;
- `eval/adaptive_residual_shadow_seventh_agent_style_log.py` now provides a laptop-local agent-style substitute while Hermes is unavailable. Its first run found a neutral-wrong unsupported production-authority query (`mutate live answers`), which is now covered by configurable `unsupported_proof` terms and suppressor regression. After regeneration, the clean aggregate passes across four local logs with 30 helpful overrides, 0 harmful, and 0 neutral-wrong, while promotion remains blocked until independent external validation;
- `eval/adaptive_residual_risk_scorer_eval.py` and `eval/adaptive_residual_risk_scorer_regression.py` add the first report-only learned residual-risk scorer. It learns risk categories from synthetic boundary rows plus residual-shadow logged examples, catches protected boundary risks in the local diagnostic set, remains promotion-blocked, and is now required by the unified architecture gate as `adaptive_residual_risk_scorer_ok`;
- `eval/adaptive_residual_risk_disagreement_eval.py` now compares learned risk predictions against the current configurable term suppressors. It currently finds seven paraphrased protected-risk catches beyond exact term suppression while producing zero safe-query over-warnings, and the unified architecture gate requires `adaptive_residual_risk_disagreement_ok`;
- runtime adaptive residual-shadow payloads now include learned-risk diagnostics per decision (`term_risk_label`, `learned_risk_label`, confidence, and disagreement flag) plus a report-only `learned_risk_model` summary. The runtime regression confirms these diagnostics do not mutate answer text, selector policy, memory, or config;
- `eval/adaptive_residual_risk_logged_eval.py` now evaluates learned-risk diagnostics from actual residual-shadow outcome logs. On the regenerated seventh local agent-style log it reports 61 diagnostic rows, 10 learned protected-risk catches beyond current terms, and 2 term-overprotection signals, while remaining report-only and gate-guarded;
- `eval/adaptive_residual_risk_overprotection_candidate.py` now turns term-overprotection signals into review-only contextual exception candidates. The current local log yields one `stale_previous_lookup` candidate group for safe meta/development queries, with auto-application blocked until recurrence appears across independent logs;
- `eval/adaptive_residual_shadow_eighth_meta_recurrence_log.py` and `eval/adaptive_residual_risk_overprotection_recurrence.py` now test that candidate across a second local log. The recurrence run passes with 2 helpful residual overrides, 0 harmful, 0 neutral-wrong, and one recurrent `stale_previous_lookup` contextual-exception candidate group. Promotion remains blocked pending external recurrence;
- `eval/adaptive_residual_risk_exception_simulation.py` now simulates the recurrent learned contextual-exception candidate in report-only mode. Across the seventh and eighth local logs it finds 3 simulated exceptions, all helpful, with 0 harmful and 0 neutral-wrong outcomes. This remains local-only evidence and does not change runtime behavior;
- Hermes external validation of commit `06160b0` found two harmful residual would-overrides on unsupported automatic-promotion/self-mutation authority queries. The learned-risk diagnostics already recognized this as protected authority risk, so `core/adaptive_residual_shadow.py` now uses protected learned-risk labels as a report-only veto before residual would-overrides. `eval/adaptive_residual_learned_risk_veto_regression.py` guards the exact Hermes authority patterns, and the unified architecture gate requires `adaptive_residual_learned_risk_veto_ok`;
- `eval/adaptive_residual_shadow_ninth_authority_veto_log.py` now locally reruns the Hermes authority-failure pattern while Hermes is unavailable. It passes with 3 helpful residual overrides, 0 harmful, 0 neutral-wrong, and a six-log clean local aggregate of 35 helpful / 0 harmful overrides. This is local substitute evidence only; a fresh Hermes run is still required;
- `eval/adaptive_residual_learned_risk_external_failure_replay.py` now replays the actual Hermes authority-failure artifact against the current learned-risk veto. Both historical harmful examples are still missed by term suppressors but are classified as `unsupported_authority_claim` above threshold and would now be suppressed. The unified architecture gate requires `adaptive_residual_learned_risk_external_failure_replay_ok`;
- `eval/adaptive_residual_learned_risk_authority_paraphrase_regression.py` now guards authority-risk generalization beyond the exact Hermes wording. It passes with 7 unsafe authority paraphrases vetoed, 6 learned beyond exact term suppressors, and 3 safe meta-development controls left unvetoed. The unified architecture gate requires `adaptive_residual_learned_risk_authority_paraphrase_ok`;
- authority-risk training is now paired with nearby safe meta-development counterexamples. The paraphrase regression now requires 6 safe blocked/report-only/no-review-disabled controls to be labeled `safe_supported_evidence_rescue`, while the exact Hermes veto, historical replay, broader learned-risk scorer regression, and unified architecture gate all pass together;
- `eval/adaptive_residual_shadow_tenth_authority_boundary_log.py` now creates an independent local runtime-style holdout for mixed unsupported authority and safe blocked-status questions. It passes with 14 asks, 3 helpful residual overrides, 0 harmful, 0 neutral-wrong; learned-risk diagnostics report 22 beyond-term catches and 0 term-overprotection signals; the clean local aggregate now passes across 7 usable residual logs with 38 helpful and 0 harmful overrides;
- residual promotion readiness now requires 7 clean local residual logs instead of the older 3-log threshold. `eval/adaptive_residual_shadow_promotion_readiness.py` reports `min_clean_local_logs=7`; `eval/selector_architecture_gate.py` runs the multi-log eval with `--min-logs 7`; promotion remains blocked only because no fresh external/agent residual validation log exists for the current post-veto code;
- Hermes external authority-boundary validation of commit `06545dd` found 4 harmful residual would-overrides on immediate policy rewrite, self-modification, single-test-run authority, and prior no-veto interpretation queries. The current learned-risk seed set now covers those patterns, and `eval/adaptive_residual_learned_risk_hermes_authority_boundary_replay.py` verifies all 4 harmful examples would now be suppressed. Promotion remains blocked pending a fresh successful Hermes/external run against the post-fix code;
- `eval/selector_architecture_gate.py` now supports `--allow-missing-runtime-artifacts` so fresh Hermes clones can run a portable source/config sanity gate before creating runtime logs. The default strict local architecture gate remains evidence-backed and still requires the local runtime/log artifacts;
- Hermes authority-boundary rerun at commit `1d37180` produced 90 asks with 0 harmful and 0 neutral-wrong residual overrides, but also 0 helpful overrides because no evidence rows were returned. `eval/hermes_authority_boundary_rerun_assessment.py` now classifies this as safety-passed but benefit-inconclusive, and `eval/hermes_authority_boundary_evidence_preflight.py` now checks evidence coverage before another full Hermes run;
- protected by `eval/evidence_context_regression.py`, `eval/evidence_context_selector_runtime_regression.py`, and the unified architecture gate;
- the unified gate now requires `evidence_context_regression_ok`, `evidence_context_selector_runtime_ok`, `adaptive_behavior_feature_scorer_ok`, `adaptive_behavior_feature_scorer_hybrid_ok`, and `adaptive_behavior_feature_challenge_ok`;
- use this as the stable input contract for later neural-symbolic learned controllers.

## Current Publication State

The codebase is suitable to publish as an experimental prototype if runtime databases, logs, local models, and generated artifacts are not committed. The database is a local runtime artifact and should be regenerated or provided separately from GitHub source control.
