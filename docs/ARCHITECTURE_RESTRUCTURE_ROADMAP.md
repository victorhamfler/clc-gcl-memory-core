# CLC-GCL Memory Architecture Restructure Roadmap

Date: 2026-05-21

## Purpose

The current CLC-GCL memory program has reached the point where the research prototype works well enough to justify restructuring. The next stage should preserve the useful discoveries from the experiments while reducing complexity and preparing the system to replace hardcoded rules with configurable, adaptive, and eventually learned mechanisms.

The goal is not a large rewrite. The goal is a controlled migration from a working prototype into a modular local memory-control architecture.

## North Star

The technological direction is:

1. Keep the system local, low-compute, auditable, and agent-controllable.
2. Preserve the CSD/G-CL idea: memory should react to novelty, contradiction, drift, curvature, and evidence state instead of only doing vector similarity.
3. Convert hardcoded behavior into explicit configuration first.
4. Convert configurable behavior into learned or self-improving behavior only when there is reliable outcome data and a safety gate.
5. Keep every learned mechanism guarded by tests that prove it does not damage known memory-boundary behavior.

In practice, that means the project should evolve from:

```text
hardcoded thresholds + growing heuristic functions
```

into:

```text
typed modules + configurable policies + logged outcomes + guarded adaptive updates
```

## Neural-Symbolic Adaptive Memory Brain Direction

The selected development direction is a neural-symbolic controller, not a purely term-based rule system and not a frontier-scale model.

The architecture should use symbolic mechanisms where auditability and safety matter, and learned mechanisms where the system needs language generalization:

- symbolic contracts for memory state, candidate artifacts, promotion gates, held-out terms, and rollback;
- configurable controller surfaces for retrieval signals, evidence states, claim scope, answer type, and CSD/G-CL thresholds;
- outcome-log mining to propose new controller knowledge;
- promotion-readiness evaluation to decide whether repeated evidence is strong enough for promotion;
- later semantic clustering or small local learned routers to group candidate phrases by meaning instead of exact terms.

This gives the system a realistic path from:

```text
single hardcoded term -> mined candidate term -> repeated candidate pattern -> semantic cluster -> guarded learned controller feature
```

The important principle is that the neural/learned part should propose or score controller features, while the symbolic gate decides whether the learned behavior is safe enough to affect memory decisions.

## Current Architectural Problem

The useful mechanisms are real, but too many of them now live inside large mixed-responsibility files:

- `core/pipeline.py` contains ingestion, retrieval, reranking, session context, correction handling, source-version logic, answer-type scoring, claim-scope scoring, authority logic, and logging.
- `core/resolver.py` contains evidence classification, evidence ranking, conflict detection, snippet selection, answer building, confidence estimation, and many query-intent helpers.
- `core/clc_policy_selector.py` is small and auditable, but much of its "learned" behavior is still guarded kNN around fixed rules.
- `serve.py` has accumulated controller orchestration for selector snapshots, OGCF feature augmentation, resolver-shadow attachment, and outcome logging.
- Many thresholds and coefficients are hardcoded in code rather than described by configuration, calibration artifacts, or learned outcome models.

The system is still valuable, but new behavior is increasingly being added as local patches instead of clean mechanisms.

## Current Direction After Full Codebase Review

The next roadmap target is a shared adaptive-memory controller context, not another isolated heuristic.

The codebase now has several useful signal families:

- canonical memory support/provenance and duplicate-pressure control;
- OGCF geometry and bridge-risk diagnostics;
- retrieval/evidence-state/claim-scope/answer-type signals;
- selector policy decisions and retrieval guardrails;
- resolver-shadow answer actions;
- answer-level feedback and compact outcome datasets.

The weakness is that these signals are still assembled in different places. The roadmap should move toward one reusable context object produced for every ask/retrieve/selector decision:

```text
query
retrieved evidence
canonical support/provenance
evidence-state summary
OGCF diagnostics
selector features and guarded decision
resolver-shadow actions
answer feedback link
outcome labels
```

This context is the bridge from the current symbolic/configurable system into the neural-symbolic adaptive memory brain. Later learned controllers should learn from this context, while symbolic gates continue deciding whether learned behavior is safe enough to affect runtime.

## What Must Be Preserved

These are the best findings from the development process and should remain first-class architecture concepts:

- CSD signals for novelty, contradiction pressure, domain shift, density, and information gain.
- G-CL memory geometry: angular drift, radial drift, orthogonal drift, curvature, stability, and domain health.
- Evidence states: `current`, `stale`, `historical`, `disputed`, and `summary`.
- Correction-chain awareness and source-version grouping.
- Claim-scope and answer-type signals that prevent near-topic evidence from winning over same-claim evidence.
- Guarded continual selector training from outcome logs.
- Retrieval-aware selector guardrails.
- Agent-controlled learning, where the agent decides when to learn instead of the system silently ingesting everything.

## Target Module Boundaries

The target architecture should separate the current monolith into these areas.

### 1. Memory Store

Responsible for SQLite access, schema ownership, memory rows, relation rows, source versions, feedback fields, and runtime persistence.

It should not contain retrieval policy, resolver policy, answer construction, or selector policy.

### 2. Signal Layer

Responsible for computing reusable signals from memories and queries:

- CSD diagnostics.
- G-CL domain health.
- claim-scope match.
- answer-type match.
- correction relevance.
- source and version signals.
- authority and supersession signals.

These signals should be explicit fields that downstream modules consume.

### 3. Retrieval Layer

Responsible for candidate generation and reranking:

- vector recall.
- lexical backfill.
- namespace filtering.
- source-version grouping.
- retrieval row assembly.

Retrieval should produce evidence candidates with signal fields, not build final answers.

### 4. Evidence Layer

Responsible for interpreting retrieved candidates:

- classify evidence state.
- detect stale/current conflicts.
- detect correction chains.
- detect disputed or weak evidence.
- compact evidence for API and logs.

### 5. Resolver Layer

Responsible for choosing evidence and composing answers:

- evidence ranking.
- preferred evidence selection.
- snippet selection.
- multi-intent composition.
- confidence estimation.

This layer should become modular enough to test each part without running the whole memory program.

### 6. Selector Layer

Responsible for memory-operation policy:

- convert retrieval diagnostics into selector features.
- choose a policy.
- explain the decision.
- admit outcome-log samples safely.
- run promotion gates before accepting a learned selector artifact.

The selector should remain small, inspectable, and conservative.

### 7. Learning Layer

Responsible for fact extraction, candidate routing, contradiction pre-checks, pending review, and feedback collection.

Learning must remain agent-controlled.

### 8. Evaluation Layer

Responsible for test suites and promotion gates:

- unit tests for modules.
- integration tests for teach/correct/ask flows.
- selector guard suites.
- long-run Hermes tests.
- holdout sets from real failures.
- scale and corruption tests.

## Hardcoded To Adaptive Migration

The architecture should treat every hardcoded number or vocabulary list as belonging to one of four maturity levels.

### Level 0: Hardcoded Prototype

The value is embedded directly in Python code. This is acceptable only for early experiments.

Examples:

- CSD novelty thresholds.
- resolver evidence weights.
- selector label-cost ceiling.
- answer-type and claim-scope vocabulary.
- broad-policy and scope-deflection heuristics.

### Level 1: Configurable

The value is moved into configuration with a default, documentation, and a regression test that confirms the config is honored.

This is the first required step for most existing hardcoded behavior.

### Level 2: Calibrated

The value is derived from an evaluation artifact or calibration script. It is still deterministic, but its source is measurable.

Examples:

- retrieval weight optimization.
- threshold search over a fixed validation set.
- selector candidate reports built from conflict-safe outcome logs.

### Level 3: Adaptive Or Learned

The value updates from real outcomes through a guarded workflow.

Examples:

- outcome-log sample injection for the selector.
- resolver ranking weights updated from feedback.
- per-domain CSD thresholds adjusted from false-positive and false-negative patterns.
- domain stability decay based on time, drift variance, and correction rate.

No Level 3 mechanism should be promoted unless it passes guard tests and a holdout set.

## Restructure Phases

### Phase 0: Freeze Current Behavior

Before refactoring, run the current regression and promotion tests and record the results.

Deliverables:

- baseline test report.
- list of accepted failures, if any.
- current commit hash.
- current config hash or copied config snapshot.

### Phase 1: Extract Selector Signal Logic

First extraction target:

- claim-scope affinity.
- answer-type affinity.
- correction relevance.
- broad generic note detection.
- scope-deflection detection.
- related token helpers.

Reason:

This is the safest first extraction because it belongs to the selector/retrieval work developed in this session, has many regression tests, and is less risky than starting with the full resolver.

Target module:

```text
core/retrieval_signals.py
```

or, if the selector package is created first:

```text
core/selector/signals.py
```

The first extraction must preserve behavior exactly.

### Phase 2: Extract Resolver Evidence Modules

Split `core/resolver.py` into:

- evidence classification.
- evidence ranking.
- conflict detection.
- answer snippet building.
- confidence estimation.

No learned resolver weights should be added before this split.

### Phase 3: Normalize Configuration

Create typed config loading for:

- CSD thresholds.
- CLC controller thresholds.
- G-CL drift weights.
- retrieval weights.
- resolver weights.
- selector guardrails.
- claim-scope aliases.
- answer-type rules.

Every config section needs defaults and a config-view endpoint or report.

### Phase 4: Add Guarded Adaptive Mechanisms

After the code is modular and configurable, add learned/adaptive updates:

- selector online sample admission.
- resolver preference-weight calibration.
- CSD threshold calibration.
- per-domain stability decay.
- contradiction pre-storage checks.

Each adaptive mechanism must have:

- an outcome log format.
- a conflict-safe admission rule.
- a promotion gate.
- an explanation report.
- a rollback path to the previous accepted config/artifact.

### Phase 5: Long-Run Validation

Use Hermes and the memory session to run longer realistic tests:

- daily isolated namespaces.
- one continuous namespace.
- repeated teach/correct/ask/retrieve/selector-explain cycles.
- real project-memory corrections.
- tool-rule updates.
- near-topic distractors.
- stale clutter.
- multi-intent questions.

The goal is to build a real holdout set from failures rather than only generated tests.

## Session Ownership

Development should stay split for now:

- This session owns the selector module, retrieval signals, guarded selector training, and architecture restructuring documents.
- The other memory-program session owns the broader memory program integration, storage behavior, learning endpoints, and Hermes workflow integration.

Both sessions should coordinate through handover documents in this repository before uploading changes that affect shared contracts.

## Current Restructure Checkpoint

The first restructure pass has now created two extracted, configurable adaptive control surfaces:

- retrieval-signal scoring in `core/retrieval_signals.py`;
- evidence-state classification in `core/evidence_states.py`.

Both now have:

- explicit config sections;
- candidate artifact formats;
- mining scripts from outcome/failure logs;
- candidate evals;
- promotion gates.

The current combined checkpoint is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

This gate should pass before selector-side candidate promotion, handoff to the memory-program session, or repository upload.

The selector candidate pipeline now also produces a report-only promotion-readiness artifact:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_candidate_pipeline_from_log.py --log <outcome-log.jsonl>
```

The readiness layer aggregates mined candidate artifacts and classifies each candidate as:

- `ready`: repeated support across enough source logs and distinct queries;
- `hold`: plausible but not mature enough;
- `reject`: generic/noisy term;
- `held_out`: intentionally preserved as evidence but blocked from promotion.

This is the first controller-level maturity evaluator. It does not promote config automatically.

## Immediate Next Step

Use the promotion-readiness reports from real Hermes runs to start building a cross-session candidate memory.

The next selector-side development should avoid adding more term lists by hand. Instead, it should:

- collect readiness reports from multiple real logs;
- identify repeated held/ready candidates across sessions;
- cluster semantically similar candidates with the local embedding model when available;
- produce a guarded semantic-candidate artifact before modifying runtime config.

The memory-program session does not need to change selector internals for this step. It only needs to keep producing linked `ask` and `feedback` outcome logs with enough raw retrieval fields for mining.

## Current Neural-Symbolic Step

The selector side now has a report-only semantic candidate memory:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\candidate_semantic_memory.py --readiness <promotion-readiness.json>
```

The one-command pipeline also writes semantic-memory artifacts next to the readiness artifacts:

```text
*_semantic_memory.json
*_semantic_memory.md
```

This is the first implementation of the cross-session candidate-memory idea. It clusters candidates by compatible controller surface, lexical/embedding similarity, support, source-log diversity, and query diversity. It still does not alter runtime config.

The next development after this should be a multi-run memory bank:

- collect semantic-memory reports from multiple Hermes sessions;
- compare which clusters recur naturally over time;
- test the configured Gemma embedding backend on candidate clustering;
- only then propose semantic cluster artifacts for promotion-gate evaluation.

## OGCF Intent Candidate Mining

The OGCF intent gate has moved from hardcoded terms to a config-backed controller surface:

```yaml
ogcf_intent:
  bridge_terms: ...
  geometry_terms: ...
  maintenance_terms: ...
  ordinary_fact_terms: ...
  scores: ...
  gate: ...
```

The selector side now has a dry-run miner for this surface:

```powershell
py .\eval\mine_ogcf_intent_candidates.py --log <outcome-log.jsonl>
```

It writes an `ogcf_intent_candidates/v1` artifact with proposed additions for:

- `bridge_terms`
- `geometry_terms`
- `maintenance_terms`
- `ordinary_fact_terms`

Regression:

```powershell
py .\eval\ogcf_intent_candidate_miner_regression.py
```

The current local `logs/memory_outcomes.jsonl` has hundreds of ask/feedback rows but no OGCF-specific labels, so the miner correctly produces zero real candidates. The memory-session controlled workflow now proves the linked label path can produce dry-run candidates for bridge, geometry, maintenance, and ordinary-suppression terms. The selector-side miner filters generic workflow terms before emitting candidates, so the controlled artifact keeps only the intended synthetic terms and does not propose filler vocabulary such as notes, memos, evidence, reviews, or pressure.

This means the next cross-session task is not to promote new terms yet. The memory-program session and Hermes need to produce explicit OGCF labels during real work:

- positive bridge labels: `bridge_relevant`, `cross_domain_bridge`, `ogcf_bridge`;
- positive geometry labels: `ogcf_geometry`, `bridge_geometry`, `loop_overload`;
- positive maintenance labels: `memory_maintenance`, `dedup`, `duplicate`, `bridge_maintenance`;
- suppression labels: `ogcf_false_positive`, `bridge_irrelevant`, `ordinary_lookup`, `no_ogcf_pressure`.

This keeps the roadmap consistent:

```text
config-backed symbolic gate -> labeled outcomes -> mined candidate artifact -> promotion/readiness gate -> later learned scorer
```

## Answer-Level Feedback Signals

The memory session now supports answer-level feedback that is log-only and separate from memory-row retrieval feedback. This gives the roadmap a second supervision stream:

```text
memory-row feedback -> retrieval/selector evidence quality
answer-level feedback -> resolver/answer/controller quality
```

The selector side consumes this with:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_signal_eval.py --log <outcome-log.jsonl>
```

It writes an `answer_feedback_controller_signals/v1` artifact. The current controlled workflow produces three `holdout_ready` signals:

- ordinary answer correctness;
- useful bridge-warning answer with non-empty OGCF diagnostics;
- missing-support refusal behavior.

This is report-only. It does not promote resolver weights, selector policy, or runtime config. The next learning step should be a multi-run answer-feedback memory bank that aggregates these signals across real Hermes sessions before any resolver scoring changes.

That first bank now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_memory_bank.py --signals <answer-feedback-signals.json> --signals <another-run.json>
```

It writes an `answer_feedback_memory_bank/v1` artifact. Local validation with one generated workflow artifact plus a second fixture artifact produced ready clusters for:

- supported answer quality;
- useful bridge warnings with OGCF metadata;
- missing-support refusal behavior.

This is the first answer-side equivalent of semantic candidate memory. It is still report-only. A later learned resolver or bridge-warning scorer should only use clusters that recur across real sessions and pass answer-quality guard tests.

The first answer-bank guard now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_feedback_bank_guard.py --bank <answer-feedback-memory-bank.json>
```

It writes an `answer_feedback_bank_guard/v1` artifact and verifies:

- bridge-warning ready clusters include OGCF metadata for all examples;
- supported-answer ready clusters include selected evidence;
- missing-support refusal clusters have no selected memories and negative feedback;
- mixed positive/negative clusters are not marked plain `ready`;
- the memory bank does not contain runtime mutation or config-promotion fields.

Current local guarded bank result: three ready clusters, zero issues, all guard checks passed.

The next report-only layer now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_eval.py --bank <answer-feedback-memory-bank.json> --guard <answer-feedback-bank-guard.json>
```

It writes an `answer_behavior_proposals/v1` artifact. Current local proposals are:

- require evidence-backed supported answers;
- emit an OGCF bridge-risk warning only when bridge diagnostics and evidence support it;
- preserve refusal or insufficient-support language when no selected memory supports the query.

This artifact still does not alter resolver behavior. The next step should be a proposal guard/eval that tests these proposed behaviors against answer-quality cases before any memory-session resolver implementation is attempted.

That proposal guard now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_proposal_guard.py --proposals <answer-behavior-proposals.json>
```

It writes an `answer_behavior_proposal_guard/v1` artifact and checks:

- proposals are report-only and cannot mutate config/runtime state;
- supported-answer proposals require selected evidence and citation/evidence language;
- bridge-warning proposals require OGCF diagnostics, selected evidence, ordinary-fact suppression, and negative-feedback suppressibility;
- missing-support proposals require no selected memories, negative feedback, refusal language, and protection for valid supported answers.

Current local guarded proposal result: three guarded-ready proposals, zero issues.

The shadow answer-behavior eval now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_shadow_eval.py --proposals ..\experiments\answer_behavior_proposals_results.json --guard ..\experiments\answer_behavior_proposal_guard_results.json
```

It writes `answer_behavior_shadow_eval/v1` and simulates guarded-ready behavior over controlled answer cases without changing `serve.py`, resolver code, runtime config, or learned artifacts. Current local result: 5/5 cases passed.

The shadow cases verify:

- supported answers require selected evidence;
- OGCF bridge warnings require support and diagnostics;
- ordinary factual queries containing bridge-like words suppress bridge warnings;
- unsupported private-code questions preserve missing-support refusal;
- stale/current supported answers disclose stale conflict.

The next selector-side step should be a real-log shadow replay or configurable resolver-shadow mode. Runtime resolver behavior should still not be changed until the memory-program session can validate the same behavior on real Hermes answer logs.

The first real-log answer-behavior shadow replay now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_shadow_replay.py --log ..\experiments\neural_symbolic_outcome_holdout_workflow.jsonl
```

It writes `answer_behavior_real_log_shadow_replay/v1` and checks linked `ask` plus answer-scope `feedback` rows. Current result: 3/3 replayed answer cases passed.

Covered by the current real-log replay:

- `answer_correct`: evidence-backed answer action was proposed;
- `answer_bridge_warning_useful`: evidence-backed answer plus OGCF bridge warning were proposed;
- `answer_missing_support`: missing-support refusal preservation was proposed.

Not yet covered by real logs:

- noisy bridge-warning suppression with `answer_bridge_warning_noise`;
- stale/conflict disclosure with `answer_stale` or `answer_conflict_not_disclosed`;
- bad citation or wrong-scope answer recovery.

The missing-label fixture now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_fixture.py
```

It writes:

```text
..\experiments\answer_behavior_real_log_missing_cases.jsonl
```

The combined replay command is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_shadow_replay.py --log ..\experiments\neural_symbolic_outcome_holdout_workflow.jsonl --log ..\experiments\answer_behavior_real_log_missing_cases.jsonl --out-json ..\experiments\answer_behavior_real_log_shadow_replay_full_coverage_results.json --out-md ..\experiments\answer_behavior_real_log_shadow_replay_full_coverage_report.md
```

Current result: 8/8 replayed answer cases passed.

Covered labels:

- `answer_correct`;
- `answer_bridge_warning_useful`;
- `answer_bridge_warning_noise`;
- `answer_missing_support`;
- `answer_stale`;
- `answer_conflict_not_disclosed`;
- `answer_bad_citation`;
- `answer_wrong_scope`.

This means the answer-behavior proposal stack now has controlled-case coverage and linked-log coverage.

The first configurable resolver-shadow mode now exists:

```yaml
resolver_shadow:
  enabled: false
  include_in_outcome_log: false
  bridge_warning_score_threshold: 0.70
  bridge_warning_effective_ratio_threshold: 0.50
```

Runtime behavior:

- default config leaves the user-facing API unchanged;
- `POST /ask` can include `include_resolver_shadow: true` to return a `resolver_shadow` object beside the normal answer;
- setting `resolver_shadow.enabled: true` enables the field by default;
- setting `resolver_shadow.include_in_outcome_log: true` logs the shadow object with ask events;
- shadow mode is report-only and declares `mutates_answer: false`, `mutates_config: false`.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_mode_regression.py
```

Current result: 7/7 cases passed.

The next step should be Hermes validation with `include_resolver_shadow: true` during normal work. The memory session should compare shadow annotations with real answer-level feedback before making any user-facing resolver changes.

## Adaptive Memory Controller Context

The first implementation of the shared context layer now exists:

```text
core/controller_context.py
```

It defines `adaptive_memory_context/v1` and centralizes:

- retrieval-derived selector features;
- canonical-memory diagnostics already attached to retrieval rows;
- optional OGCF feature augmentation and intent-gated bridge pressure;
- guarded selector decision creation;
- selector snapshots consumed by `/ask`, `/selector_decide`, `/selector_explain`, resolver-shadow, and outcome logs.

The API no longer owns this selector/OGCF orchestration directly. `serve.py` now calls the context builder and remains a thinner transport/logging layer.

Outcome logging now writes this same context shape:

- `ask` events keep the legacy `selector_snapshot` field for backward compatibility;
- `ask` events also include `adaptive_memory_context` with schema, features, diagnostics, compact retrieval context, OGCF presence, and the selector snapshot;
- `selector_explain` events write `selector_context` using the same `adaptive_memory_context/v1` shape;
- answer feedback can link back to the ask operation id, so later datasets can join answer labels to the exact runtime context used at answer time.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\controller_context_regression.py
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
```

This regression verifies that the new context builder matches the previous direct selector + OGCF + retrieval-guard path, exposes the `adaptive_memory_context/v1` schema, preserves non-empty OGCF diagnostics, and still handles condition-only selector payloads.
The outcome logging regression verifies the logged context schema, legacy selector snapshot parity, feature presence, retrieval-context presence, and linked answer/memory feedback.

The resolver-shadow outcome collector now consumes this context directly:

- if an `ask` event has `adaptive_memory_context`, the collector uses its `selector_snapshot` and diagnostics;
- if an older log only has `selector_snapshot`, the collector falls back to the legacy path;
- each collected example records `context_source` so later datasets can distinguish new-context examples from legacy examples;
- raw-log threshold calibration uses the same context preference.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_outcome_context_regression.py
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_runtime_context_log_regression.py
```

Current result: pass. The regression proves adaptive-context logs and legacy selector-snapshot logs produce the same semantic resolver-shadow outcome fields.
The runtime-context regression goes one step further: it creates a real `MemoryApi` ask log with `adaptive_memory_context`, writes linked answer-level feedback, and verifies the resolver-shadow collector produces a valid `answer_correct` outcome example with `context_source=adaptive_memory_context`.

This is the architectural pivot for the next phase:

```text
runtime signals -> adaptive context -> report-only datasets -> calibrated/learned scorer -> symbolic promotion gate
```

The next learning work should consume context artifacts instead of bespoke eval-specific rows whenever possible.

The first shared outcome table now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_outcome_dataset.py --log <outcome-log.jsonl>
```

It writes:

```text
..\experiments\adaptive_context_outcome_dataset_results.json
..\experiments\adaptive_context_outcome_dataset_report.md
```

Schema:

```text
adaptive_context_outcome_dataset/v1
```

This dataset joins linked ask/feedback rows and preserves:

- feedback scope, label, rating, and outcome family;
- query and answer preview;
- selected memory ids;
- selector policy/action/reason;
- adaptive context features;
- compact diagnostics for CSD, stale/conflict, canonical memory, and OGCF;
- compact retrieval context;
- optional resolver-shadow actions when they were logged;
- context source, so migrated legacy examples and new adaptive-context examples remain distinguishable.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_outcome_dataset_regression.py
```

Current result: pass. The regression creates real runtime logs with both answer-level and memory-level linked feedback and verifies both become adaptive-context examples. The collector also runs on existing legacy and local outcome logs and currently produces 192 examples with no skipped rows.

The first readiness guard for this shared dataset now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_dataset_guard.py --dataset ..\experiments\adaptive_context_outcome_dataset_results.json
```

It writes:

```text
..\experiments\adaptive_context_dataset_guard_results.json
..\experiments\adaptive_context_dataset_guard_report.md
```

Schema:

```text
adaptive_context_dataset_guard/v1
```

The guard separates structural safety from learning readiness:

- `ok` means the dataset is report-only, linked, context-bearing, retrieval-bearing, and has no hard errors.
- `readiness` says whether the examples are only useful for analysis, ready for runtime collection, or strong enough to become a promotion candidate.
- capability checks report whether answer feedback, memory feedback, adaptive-context examples, and OGCF families are present.

Current accumulated result: structurally safe with 192 examples and no errors, but `analysis_only` because all accumulated rows still come from legacy selector snapshots. The regression creates fresh runtime rows and proves adaptive-context answer + memory feedback can reach `ready_for_runtime_collection`. The next data task is therefore to collect more fresh `adaptive_memory_context/v1` logs with answer, memory, and OGCF labels before training or promoting any learned scorer.

That fresh local collection fixture now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_rich_runtime_fixture.py
```

It creates a temporary runtime DB, teaches diverse local memories, runs real `ask` calls through `adaptive_memory_context/v1`, writes linked answer-level and memory-level feedback, and then builds plus guards the resulting dataset.

It writes:

```text
..\experiments\adaptive_context_rich_runtime_examples.jsonl
..\experiments\adaptive_context_rich_runtime_dataset_results.json
..\experiments\adaptive_context_rich_runtime_guard_results.json
..\experiments\adaptive_context_rich_runtime_fixture_results.json
```

Current fresh result:

- 48 examples;
- 24 answer-feedback examples;
- 24 memory-feedback examples;
- all 48 from `adaptive_memory_context`;
- OGCF positive and OGCF negative coverage;
- guard readiness: `promotion_candidate`.

Combining this fresh fixture with the existing legacy/local outcome logs gives 208 structurally clean examples:

- 48 adaptive-context examples;
- 192 legacy selector-snapshot examples;
- 32 answer examples;
- 208 memory examples;
- guard readiness: `promotion_candidate`.

This still should not auto-promote any runtime behavior. It means the next learned-control experiment can start as report-only training/evaluation against the combined dataset, with the fresh adaptive-context slice treated as the primary validation target and the legacy slice treated as historical support.

The first report-only learned scorer now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_tiny_scorer.py --dataset ..\experiments\adaptive_context_combined_dataset_results.json
```

It writes:

```text
..\experiments\adaptive_context_tiny_scorer_results.json
..\experiments\adaptive_context_tiny_scorer_report.md
```

Schema:

```text
adaptive_context_tiny_scorer/v1
```

The scorer is a deterministic tiny logistic model over adaptive-context features, diagnostics, selector action/policy fields, and compact retrieval statistics. It compares against two baselines:

- majority-class baseline;
- symbolic retrieval-health baseline.

Current combined result:

- 240 labeled examples;
- 97 positive and 143 negative outcomes;
- combined 5-fold learned accuracy: 0.591873;
- combined 5-fold majority accuracy: 0.595866;
- combined 5-fold learned Brier: 0.284305;
- combined 5-fold majority Brier: 0.404134;
- adaptive-only learned accuracy: 0.895542;
- adaptive-only majority accuracy: 0.562646;
- adaptive-only learned Brier: 0.075683.

Interpretation:

- The fresh `adaptive_memory_context/v1` slice is learnable and beats baselines in accuracy and calibration.
- Training only on legacy selector-snapshot rows transfers poorly to fresh adaptive-context rows, which proves the architecture should not treat legacy rows as equivalent training data.
- Legacy rows remain useful as historical support and calibration pressure, but the learned controller should be promoted only from fresh adaptive-context examples.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_tiny_scorer_regression.py
```

Current regression result: pass. It verifies the fresh adaptive-context dataset produces a report-only scorer where the learned model beats majority accuracy and symbolic-health Brier on the adaptive slice.

The scorer now also runs a harder behavior-family holdout:

```text
adaptive_behavior_holdout
```

This trains while holding out each answer-behavior family in turn, then tests on that unseen family. Current fresh result:

- weighted learned accuracy: 0.229167;
- weighted learned Brier: 0.6288;
- weighted symbolic-health accuracy: 0.520833;
- weighted symbolic-health Brier: 0.265518;
- scorer readiness: `blocked_behavior_generalization`.

Interpretation:

- The tiny scorer is learning the controlled fixture patterns, and it is useful as an analysis signal.
- It is not yet a promotion-ready controller because it does not generalize to unseen behavior families.
- Symbolic health remains the better fallback for out-of-family behavior.

This changes the next development target: the learned controller should become a hybrid neural-symbolic controller that combines the tiny learned score with explicit behavior-family/answer-type signals, rather than replacing symbolic guards with a single polarity model.

The first behavior-aware hybrid scorer now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_behavior_aware_scorer.py --dataset ..\experiments\adaptive_context_rich_runtime_dataset_results.json
```

It writes:

```text
..\experiments\adaptive_context_behavior_aware_scorer_results.json
..\experiments\adaptive_context_behavior_aware_scorer_report.md
```

Schema:

```text
adaptive_context_behavior_aware_scorer/v1
```

The scorer is deliberately conservative:

- route by answer-behavior family;
- use a family model only when that family has enough mixed evidence;
- blend family learned scores with symbolic retrieval health;
- fall back to symbolic health for unseen behavior families.

Current behavior-holdout result:

- hybrid weighted accuracy: 0.520833;
- hybrid weighted Brier: 0.265518;
- symbolic-health weighted accuracy: 0.520833;
- symbolic-health weighted Brier: 0.265518;
- readiness: `analysis_ready`.

This does not yet improve beyond the symbolic fallback on unseen families, but it fixes the unsafe failure mode of the generic tiny scorer. It is now a safer architecture for the next stage: learned scoring can be admitted inside known behavior families while unseen behavior remains symbolic.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_behavior_aware_scorer_regression.py
```

Current regression result: pass.

The semantic behavior map is now configurable:

```yaml
adaptive_behavior:
  superfamilies:
    supported_evidence: answer_correct,answer_good_citation,answer_bad_citation
    ogcf_bridge_warning: answer_bridge_warning_useful,answer_bridge_warning_noise
    missing_support: answer_missing_support,answer_overconfident
    stale_conflict: answer_stale,answer_conflict_not_disclosed
```

Core normalization lives in:

```text
core/adaptive_behavior.py
```

The scorer now loads this config by default and emits `adaptive_behavior_config/v1` in its report. The promotion-readiness guard now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_behavior_guard.py --scorer ..\experiments\adaptive_context_semantic_behavior_scorer_results.json
```

It writes:

```text
..\experiments\adaptive_context_semantic_behavior_guard_results.json
..\experiments\adaptive_context_semantic_behavior_guard_report.md
```

Schema:

```text
adaptive_context_semantic_behavior_guard/v1
```

The guard requires:

- report-only scorer output;
- `adaptive_behavior_config/v1` present;
- behavior holdout present;
- semantic hybrid accuracy greater than symbolic fallback;
- semantic hybrid Brier lower than symbolic fallback.

Current guard result:

- readiness: `promotion_candidate`;
- semantic accuracy: 0.583333;
- symbolic accuracy: 0.520833;
- semantic Brier: 0.233237;
- symbolic Brier: 0.265518.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_behavior_guard_regression.py
```

Current regression result: pass.

This is still not an automatic runtime promotion. It means the semantic scorer is now a valid report-only candidate artifact for the next shadow-controller stage.

The first semantic adaptive-behavior shadow-controller artifact now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_shadow_controller.py --dataset ..\experiments\adaptive_context_rich_runtime_dataset_results.json --guard ..\experiments\adaptive_context_semantic_behavior_guard_results.json
```

It writes:

```text
..\experiments\adaptive_context_semantic_shadow_controller_results.json
..\experiments\adaptive_context_semantic_shadow_controller_report.md
```

Schema:

```text
adaptive_context_semantic_shadow_controller/v1
```

The artifact is advisory only. It requires the semantic behavior guard to be `promotion_candidate`, loads the configurable `adaptive_behavior_config/v1`, trains semantic family routes on the adaptive-context dataset, and emits per-example shadow advisories:

- `likely_helpful`;
- `likely_harmful`;
- `uncertain_keep_symbolic`.

Current result:

- readiness: `shadow_candidate`;
- 48 adaptive examples;
- advisory counts: 21 `likely_helpful`, 4 `likely_harmful`, 23 `uncertain_keep_symbolic`;
- route counts: 6 `exact_family_model`, 42 `exact_family_prior_blend`;
- shadow remains disabled by default in config;
- no runtime/config mutation.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_shadow_controller_regression.py
```

Current regression result: pass.

This is the first full neural-symbolic controller chain:

```text
adaptive context -> outcome dataset -> semantic scorer -> promotion guard -> shadow-controller artifact
```

The next stage should test this shadow artifact on new live logs rather than promoting it directly.

The first fresh live-style shadow validation now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_shadow_live_style_eval.py
```

It generates a new local runtime log, builds an adaptive-context outcome dataset from that log, guards the dataset, trains the semantic shadow controller from the earlier rich fixture, and evaluates on the fresh live-style examples.

It writes:

```text
..\experiments\adaptive_context_semantic_shadow_live_style_examples.jsonl
..\experiments\adaptive_context_semantic_shadow_live_style_dataset_results.json
..\experiments\adaptive_context_semantic_shadow_live_style_dataset_guard_results.json
..\experiments\adaptive_context_semantic_shadow_live_style_eval_results.json
```

Schema:

```text
adaptive_context_semantic_shadow_live_style_eval/v1
```

Current result:

- readiness: `live_style_shadow_candidate`;
- 20 fresh adaptive-context examples;
- 9 actioned advisories;
- 11 `uncertain_keep_symbolic` advisories;
- actioned precision: 1.0;
- coverage: 0.45;
- no runtime/config mutation.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_shadow_live_style_regression.py
```

Current regression result: pass.

This is stronger evidence than the internal fixture tests because the trained shadow controller is evaluated on newly generated logs with different wording and scenarios. It remains conservative: it only acts on high-confidence cases and leaves the rest to symbolic handling.

The stricter multi-batch validation now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_shadow_multibatch_eval.py
```

It creates three independent fresh live-style batches, each in a separate temporary runtime, builds/guards each adaptive-context dataset, and evaluates the same trained semantic shadow controller on each batch.

It writes:

```text
..\experiments\adaptive_context_semantic_shadow_multibatch_eval_results.json
..\experiments\adaptive_context_semantic_shadow_multibatch_eval_report.md
..\experiments\adaptive_context_semantic_shadow_multibatch_<batch>*.json/jsonl/md
```

Schema:

```text
adaptive_context_semantic_shadow_multibatch_eval/v1
```

Current result:

- readiness: `multibatch_shadow_candidate`;
- 3 independent batches;
- 48 total fresh adaptive-context examples;
- 20 actioned advisories;
- weighted actioned precision: 1.0;
- weighted coverage: 0.416667;
- no runtime/config mutation.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_shadow_multibatch_regression.py
```

Current regression result: pass.

This is the strongest current evidence for the adaptive memory brain direction: the semantic shadow controller stays conservative, high precision, and non-mutating across several fresh generated batches.

The next behavior-signal improvement now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_behavior_scorer.py --dataset ..\experiments\adaptive_context_rich_runtime_dataset_results.json
```

It writes:

```text
..\experiments\adaptive_context_semantic_behavior_scorer_results.json
..\experiments\adaptive_context_semantic_behavior_scorer_report.md
```

Schema:

```text
adaptive_context_semantic_behavior_scorer/v1
```

This scorer maps exact behavior labels into broader semantic behavior superfamilies:

- `supported_evidence`: supported answers, good citation, bad citation;
- `ogcf_bridge_warning`: useful bridge warnings and bridge-warning noise;
- `missing_support`: missing support;
- `stale_conflict`: stale and undisclosed conflict.

On the same exact-behavior holdout, semantic superfamily routing improves over symbolic health:

- semantic hybrid weighted accuracy: 0.583333;
- symbolic-health weighted accuracy: 0.520833;
- semantic hybrid weighted Brier: 0.233237;
- symbolic-health weighted Brier: 0.265518;
- readiness: `analysis_ready`.

This is the first evidence that the controller can generalize between related answer-behavior families instead of only memorizing exact labels or falling back to symbolic health.

Protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_semantic_behavior_scorer_regression.py
```

Current regression result: pass.

Hermes validation passed, but it correctly identified one remaining coverage gap: natural live OGCF bridge-risk answer cases were still thin. Because Hermes was unavailable for the next iteration, the selector side added a local live-log-shaped OGCF bridge worklog fixture:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_ogcf_bridge_worklog_fixture.py
```

It writes:

```text
..\experiments\answer_behavior_ogcf_bridge_worklog.jsonl
```

The new direct runtime-shadow regression is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_ogcf_bridge_worklog_regression.py
```

Current result: 8/8 cases passed.

The combined replay with Hermes-collected logs and the new local OGCF worklog is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\answer_behavior_real_log_shadow_replay.py --log <hermes-neural-symbolic-log> --log <hermes-missing-cases-log> --log ..\experiments\answer_behavior_ogcf_bridge_worklog.jsonl
```

Current result: 16/16 cases passed.

The balanced worklog also strengthens the answer-feedback learning path:

- `answer_feedback_memory_bank_ogcf_bridge_results.json`: 11 signals, 5 clusters, 3 ready clusters;
- `answer_feedback_bank_guard_ogcf_bridge_results.json`: pass, zero issues;
- `answer_behavior_proposals_ogcf_bridge_results.json`: 3 proposals;
- `answer_behavior_proposal_guard_ogcf_bridge_results.json`: pass, zero issues.

This means the local controller can now be developed further without Hermes by generating scoped worklogs, as long as every generated worklog remains report-only and is validated by replay plus direct runtime-shadow regression.

The first threshold calibration artifact now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_threshold_calibration.py
```

By default, this now consumes the compact `resolver_shadow_outcome_dataset/v1` artifact when it exists. Raw ask/feedback log replay is still available with explicit `--log` arguments for traceability and parity checks.

It writes:

```text
..\experiments\resolver_shadow_threshold_calibration_results.json
..\experiments\resolver_shadow_threshold_calibration_report.md
```

Current result:

- calibration cases: 16;
- perfect threshold candidates: 37;
- current default `0.70/0.50`: 0 failures;
- advisory strict candidate `0.95/0.75`: 0 failures.

No config was changed. The strict candidate is useful evidence, but the current defaults remain acceptable until more natural live logs exist. The next threshold decision should compare defaults and strict candidate on real `include_resolver_shadow: true` answer logs.

Dataset/raw-log parity is protected by:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_threshold_calibration_dataset_regression.py
```

Current result: pass. The dataset-driven calibration and raw-log calibration have the same 16-case label counts and the same recommended candidate.

The first resolver-shadow outcome collector now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_outcome_collector.py
```

It writes:

```text
..\experiments\resolver_shadow_outcome_dataset_results.json
..\experiments\resolver_shadow_outcome_dataset_report.md
```

Schema:

```text
resolver_shadow_outcome_dataset/v1
```

The dataset contains compact per-example rows with:

- source log and linked operation ids;
- answer label/family/rating;
- selected evidence count and memory ids;
- OGCF bridge score, effective affected ratio, and intent;
- ordinary-fact and stale-conflict diagnostics;
- shadow actions, expected actions, forbidden actions;
- outcome bucket such as `bridge_warning_true_positive`, `bridge_warning_true_negative`, `missing_support_correct`, `stale_disclosure_correct`, and `supported_answer_correct`.

Current result:

- 16 examples;
- 0 skipped;
- default threshold dataset passes;
- strict threshold dataset passes;
- collector regression passes.

This is now the preferred intermediate artifact for future calibration. Threshold sweeps consume this compact dataset by default, while later learned bridge-warning scorers should use it as their first training/evaluation table instead of repeatedly parsing full ask/feedback logs.

## OGCF Memory Maintenance Branch

Hermes' OGCF tests should be incorporated as a complementary memory-maintenance branch, not as a replacement for the selector roadmap.

The correct integration pattern is the same conservative pattern used for selector candidates:

```text
OGCF geometry / dedup evidence -> dry-run maintenance candidates -> gate -> Hermes validation -> optional runtime integration
```

The first selector-side port is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\ogcf_maintenance_candidate_gate.py
```

This gate validates:

- the OGCF maintenance candidate generator compiles;
- the regression fixture finds exact duplicate, semantic duplicate, and stale-version candidates;
- the candidate artifact declares `mutates_db: false`;
- a real DB sample can produce dry-run candidates without changing memory rows.

Runtime memory mutation is still out of scope until the dry-run candidates have been reviewed and benchmarked.

## Canonical Memory View Layer

The OGCF duplicate-origin diagnostics showed that `memory_experiment_180_best.db` is a stress-test DB, not a clean diverse memory benchmark:

- `6955` active memory rows;
- `192` exact-distinct texts;
- `6763` extra exact-duplicate rows;
- most duplicate pressure came from generated Hermes escalation/policy test namespaces.

The next architecture layer is now implemented as a non-destructive canonical view:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_memory_view_eval.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_memory_view_regression.py
```

This layer turns repeated rows into canonical claims with support/provenance metadata:

- one canonical text/keeper memory per exact claim;
- support count and all supporting memory IDs;
- duplicate memory IDs;
- domain, namespace, and source counts;
- first-seen and last-seen timestamps;
- semantic edges marked as either clean paraphrases or conflict/update signals.

The key policy decision is that exact dedup should become canonicalization, not blind deletion. Repeated rows usually do not add new text content, but they can carry useful evidence: support count, source provenance, namespace spread, and time range. Semantic dedup remains review-first because near-duplicate claims can encode corrections or opposite facts.

The next selector-side integration should consume this canonical view as a retrieval/OGCF feature source:

- reduce duplicate pressure in retrieval ranking;
- expose `support_count` as confidence evidence;
- penalize duplicate-dominated bridge clusters;
- route `semantic_conflict_or_update` edges into stale/correction guards instead of merge actions.

## Canonical Retrieval Scoring

The first retrieval-side canonical integration is implemented behind the `canonical_memory` config section:

```yaml
canonical_memory:
  enabled: true
  support_weight: 0.08
  duplicate_penalty: 0.18
  support_reference_count: 10
  lexical_backfill_enabled: true
  lexical_backfill_min_affinity: 0.75
  lexical_backfill_max_additions: 20
```

The retrieval pipeline now attaches these fields to each retrieved row when enabled:

- `canonical_claim_key`
- `canonical_keeper_memory_id`
- `canonical_support_count`
- `canonical_duplicate_count`
- `canonical_is_keeper`
- `canonical_support_bonus`
- `canonical_duplicate_penalty`
- `canonical_score_adjustment`

The scoring rule is intentionally conservative:

- exact-claim keepers receive a bounded support bonus;
- redundant non-keeper duplicate rows receive a stronger duplicate penalty;
- duplicate rows remain retrievable if requested, but should no longer dominate the top ranks only because the same text was inserted many times.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_retrieval_scoring_regression.py
```

The next improvement should test whether retrieval recall needs a canonical lexical backfill. A live exact-text probe against the stress DB did not surface the old duplicate rows in top vector results, so canonical scoring is working, but the recall candidate pool may still miss exact claims when the embedding index is noisy or document chunks dominate.

Canonical lexical backfill is now implemented before final retrieval scoring. It scans the active namespace scope for exact or strong lexical claim matches, chooses the canonical keeper for each repeated exact claim, and injects only those keepers into the candidate pool. This recovers important exact claims without reintroducing duplicate flooding.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_lexical_backfill_regression.py
```

The regression verifies:

- an exact claim can be missed by vector top-k when many vector-near distractors exist;
- canonical lexical backfill recovers the exact canonical keeper;
- recovered keeper ranks first after scoring;
- support metadata attaches correctly;
- cross-namespace support is excluded from scoped retrieval.

Namespace isolation remains intentional. A default global query will not search generated `agent:*` stress-test namespaces. When the exact stress-test namespace is requested, the backfill recovers the matching claim and keeps support scoped to that namespace.

## Canonical Selector Signals

The selector now consumes canonical retrieval metadata through `selector_features_from_retrieval_context()`.

New diagnostics:

- `canonical_max_support_count`
- `canonical_supported_keeper_rows`
- `canonical_supported_keeper_ratio`
- `canonical_nonkeeper_rows`
- `canonical_duplicate_pressure`
- `canonical_support_strength`
- `canonical_confidence_signal`
- `canonical_confidence_credit`
- `canonical_duplicate_penalty`

The feature shaping is deliberately small:

- clean canonical keeper support can slightly reduce `memory_bad_rate` and `probe_drop`;
- duplicate non-keeper clutter increases `memory_bad_rate`, `probe_drop`, and `csd_ratio`;
- stale or conflict-heavy contexts do not receive the clean support credit, even when they have repeated support.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_selector_features_regression.py
```

This is the first full selector path for canonical memory:

```text
canonical view -> retrieval keeper/backfill/scoring -> selector diagnostics/features
```

## Canonical + OGCF Combined Eval

The canonical branch and OGCF branch are now tested together with a four-mode eval:

- canonical off, OGCF off;
- canonical on, OGCF off;
- canonical off, OGCF on;
- canonical on, OGCF on.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_combined_eval.py
```

The combined eval verifies:

- canonical lexical backfill recovers an exact claim missed by vector-only retrieval;
- support metadata attaches to the recovered canonical keeper;
- duplicate clutter becomes visible to selector diagnostics instead of being silently erased;
- OGCF bridge overload still increases selector risk after canonical support is present;
- stale/current conflict contexts do not receive canonical confidence credit;
- the exact-unique shadow DB strongly reduces OGCF maintenance noise compared with the duplicate-heavy stress DB.

Current interpretation:

```text
canonical memory = claim support/provenance and duplicate-pressure control
OGCF = geometry-level bridge/composition risk detector
selector = controller that combines both into conservative action choice
```

This means the two methods should stay combined, not treated as competing alternatives. Canonical memory cleans and structures local evidence; OGCF remains useful for graph-level failure modes that are not visible from exact duplicate counts alone.

The next best step after this checkpoint is a real answer-quality and agent-loop eval: run representative memory questions through retrieval with canonical/OGCF diagnostics enabled, then score whether answers choose the correct current claim, cite support/provenance, avoid stale claims, and surface bridge/conflict warnings when needed.

## Canonical + OGCF Answer Quality Eval

The first answer-level eval for the combined architecture is now implemented:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_answer_quality_eval.py
```

This eval creates isolated temporary memory databases and tests:

- canonical off vs canonical on for an exact-miss answer case;
- canonical support metadata in answer evidence;
- current/stale correction handling through the real `ask()` path;
- stale context preservation for auditability;
- OGCF bridge-risk augmentation over the answer retrieval context.

The key result is that canonical-on answers the exact-miss launch-window question correctly, while canonical-off answers from a vector-near distractor. This proves the canonical layer has user-visible answer-quality value, not only better internal ranking.

Current combined architecture:

```text
canonical lexical backfill -> canonical support/provenance scoring -> answer resolver
                                     |
                                     v
                         selector diagnostics/features
                                     |
                                     v
                         OGCF bridge-risk augmentation
```

The next best development step is to turn this eval into a Hermes handoff / longer agent-loop benchmark:

- run the same canonical-off/on and OGCF-off/on comparisons over real Hermes working logs;
- collect answer correctness, stale avoidance, support citation, duplicate pressure, bridge warning, and selector-policy metrics;
- add at least one multi-day or multi-session replay so support/provenance and duplicate pressure can evolve naturally.

## Hermes Agent-Loop Result And Selector Fix

Hermes ran the canonical + OGCF handoff against commit `2cea5e6`.

Result:

- baseline evals passed: `4/4`;
- canonical support effects were measurable;
- OGCF feature augmentation was wired correctly;
- two retrieval failures were judged by Hermes as synthetic hash-embedding artifacts;
- the real blocker was selector policy collapse: all `18` queries in all `4` modes returned `XSEQ_MEMORY_REFRESH`.

The blocker was in `CLCPolicySelector.select()`: it still mostly followed condition labels such as `hard_budget144` and did not branch on measured `memory_bad_rate`, `probe_drop`, or `csd_ratio`.

The selector now has a conservative feature-aware branch:

- cost and budget guards still protect first;
- condition-only calls with no measured memory signals preserve the old default behavior;
- clean measured contexts can choose `PROTECT_PERIODIC`;
- moderate memory risk chooses `LONG_SEVERE_VERIFIED_REFRESH`;
- severe short-stream risk chooses `XSEQ_MEMORY_REFRESH`;
- severe long-stream risk chooses verified refresh rather than XSEQ.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\clc_policy_feature_signal_regression.py
```

This regression is now part of the required Hermes baseline before rerunning the agent-loop benchmark.

Next test:

- push the selector fix;
- have Hermes pull the new commit;
- rerun the same `hermes_canonical_ogcf_agent_loop_test.py`;
- confirm policy distribution is no longer all XSEQ and that canonical/OGCF signal changes produce policy changes.

## Hermes Validation Of Selector Fix

Hermes validated commit `bb49b00`.

Result:

- `clc_policy_feature_signal_regression`: `8/8` checks passed;
- policy distribution no longer collapsed to all XSEQ;
- canonical mode changed policy in `8/18` agent-loop queries;
- canonical and combined modes produced `PROTECT_PERIODIC` for clean supported contexts and verified refresh for riskier contexts;
- OGCF did not move policy in Hermes' copied agent-loop test because the test passed empty `ogcf_meta = {}`.

The next improvement is therefore not another selector threshold change. The next test gap is non-empty OGCF metadata in the agent-loop harness.

New regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_policy_distribution_regression.py
```

This regression verifies that:

- canonical clean support can protect;
- duplicate pressure blocks clean protection;
- non-empty OGCF bridge metadata pushes clean supported retrieval into verified refresh;
- combined canonical + OGCF diagnostics remain visible;
- policy distribution does not collapse to one action.

Next Hermes run should use real or simulated non-empty OGCF metadata for bridge-risk cases instead of `{}`.

## Gemma-Backed Adaptive Shadow Gate

The adaptive semantic shadow controller has now been validated on real local Gemma retrieval, not only generated hash/test-runtime fixtures.

The new eval is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_gemma_shadow_eval.py
```

It builds a report-only `adaptive_context_outcome_dataset/v1` holdout from the raw-Gemma canonical/OGCF fixture:

- DB: `..\experiments\rich_gemma_raw_canonical_ogcf_fixture.db`;
- namespace: `agent:rich-gemma-canonical-ogcf`;
- embedding backend: `wsl_llama_cpp`;
- embedding dimension: `768`;
- adaptive-context examples: `24`;
- all examples come from `adaptive_memory_context/v1`;
- retrieval coverage is full.

Current result:

- readiness: `gemma_shadow_candidate`;
- actioned advisories: `14`;
- actioned precision: `1.0`;
- coverage: `0.583333`;
- runtime/config mutation: none.

The regression is:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_context_gemma_shadow_regression.py
```

The production shadow harness also now has a retrieval-coverage guard:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_shadow_coverage_regression.py
```

This prevents a bad namespace, empty DB, or broken query encoder from looking like a safe protect-all selector result. Low retrieval coverage now fails by default unless the caller explicitly passes `--allow-low-retrieval-coverage`.

The unified selector architecture gate now includes both new regressions:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

Current required summary:

```json
{
  "retrieval_signal_gate_ok": true,
  "evidence_state_gate_ok": true,
  "shadow_coverage_guard_ok": true,
  "gemma_shadow_regression_ok": true
}
```

This changes the roadmap status: the next step is no longer proving that the semantic shadow controller can survive Gemma retrieval. That is now protected.

## Runtime Adaptive Behavior Shadow Surface

The runtime report-only surface now exists on `POST /ask`.

It is disabled by default:

```yaml
adaptive_behavior:
  shadow:
    enabled: false
    include_in_outcome_log: false
```

An agent can request advisories for one ask call with:

```json
{
  "include_adaptive_behavior_shadow": true
}
```

It can also explicitly log those advisories for later feedback/outcome analysis:

```json
{
  "include_adaptive_behavior_shadow": true,
  "log_adaptive_behavior_shadow": true
}
```

The response/log payload uses:

```text
adaptive_behavior_shadow/v1
```

It emits report-only semantic behavior-family advisories for:

- `supported_evidence`;
- `missing_support`;
- `stale_conflict`;
- `ogcf_bridge_warning` when OGCF diagnostics are present.

The runtime surface does not change answer text, selector policy, retrieval rows, memory rows, or config. It exposes advisory, route, probability, behavior family, reasons, and compact diagnostics so later real feedback can be joined to the exact adaptive context used at answer time.

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_shadow_runtime_regression.py
```

Current result: pass. It verifies the shadow is absent by default, present when requested, logged only when explicitly requested, report-only, and does not change the answer, evidence, or selector decision.

The unified selector architecture gate now includes this runtime regression:

```json
{
  "retrieval_signal_gate_ok": true,
  "evidence_state_gate_ok": true,
  "shadow_coverage_guard_ok": true,
  "gemma_shadow_regression_ok": true,
  "adaptive_behavior_shadow_runtime_ok": true
}
```

The next development step should collect real agent ask/feedback logs with `include_adaptive_behavior_shadow=true` and `log_adaptive_behavior_shadow=true`, then build a calibration/replay artifact that compares shadow advisories against real answer-level and memory-level feedback. Promotion remains out of scope until that real-log calibration exists.
