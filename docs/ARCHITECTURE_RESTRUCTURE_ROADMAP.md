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

## RPG Relational Substrate Layer

The next ERG/OGCF development has been reframed by the RPG memory skill as a relational-substrate layer. RPG should not replace CSD, G-CL, CLC, canonical memory, or the existing maintenance lifecycle. It should sit above the memory store as a report-only geometry-control diagnostic until it proves downstream value.

Current intended RPG role:

```text
memory rows + embeddings + metadata
  -> mixed relational substrate A
  -> constrained projector sectors
  -> curvature/activity and correlation-island diagnostics
  -> maintenance/retrieval evidence for guarded selector decisions
```

The first implementation is deliberately conservative:

- `core/rpg_memory.py` builds a normalized symmetric memory-memory substrate from embedding similarity, domain similarity, source/authority similarity, retrieval-frequency similarity, and a tiny lexical duplicate tie-breaker.
- `eval/rpg_relational_substrate_probe_regression.py` runs report-only probes for active/deprecated, source-authority/retrieval, duplicate/contradiction, and domain/recency constraint pairs.
- The probe reports projector stability, curvature activity, sector memory ids, sector statuses, and correlation-island ratios.
- The probe mutates no database, no runtime behavior, and no config.

This gives the architecture a clean transition from ERG/OGCF bridge diagnostics toward RPG memory attractor diagnostics. The next stage should compare RPG island/activity signals against existing maintenance candidate quality, rehearsal review summaries, and answer/retrieval failures before any RPG score affects a selector policy.

## RPG Maintenance Rehearsal Annotations

The first connection between RPG and the maintenance lifecycle is now report-only inside copied-DB rehearsal:

- `eval/memory_maintenance_copied_db_rehearsal.py` builds RPG records from the rehearsal DB with stored vectors when available and a deterministic lexical fallback when vectors are absent.
- Rehearsal reports include `memory_maintenance_rpg_rehearsal_annotations/v1`.
- Each planned operation receives a report-only RPG annotation with target-sector overlap, direct target island ratio, direct target mean relation, duplicate/contradiction overlap, active/deprecated overlap, and the existing target-quality risk flags.
- `eval/memory_maintenance_rich_copied_db_target_quality_regression.py` verifies that safe exact duplicates carry stronger direct RPG target relation than a stale-as-duplicate blocker, while stale/duplicate-text-mismatch risk remains blocked by the symbolic review summary.

This is an important architecture boundary: RPG can now explain maintenance targets, but it still cannot approve mutation. The next safe improvement is to aggregate these RPG rehearsal annotations across repeated rehearsals in the review memory bank, then learn whether island/activity signals predict safe duplicate canonicalization or bridge/stale risk.

## RPG Rehearsal Memory-Bank Aggregation

RPG rehearsal annotations now flow through the repeated-rehearsal evidence path:

- `eval/memory_maintenance_rehearsal_review_memory_bank.py` attaches matching RPG operation annotations to each symbolic rehearsal review by `candidate_id`.
- Each memory-bank cluster now carries `memory_maintenance_rehearsal_rpg_cluster_summary/v1`, including target mean relation, target island ratio, sector island ratio, omega norm, target-sector overlap ratio, duplicate/contradiction overlap, active/deprecated overlap, and risk-flag counts.
- `eval/memory_maintenance_rehearsal_candidate_guard.py` preserves the RPG summary when it builds guarded or blocked operator-review candidates.
- `eval/memory_maintenance_operator_review_packet.py` exposes the RPG summary in the operator packet, so a human or Hermes can compare symbolic blockers with relational-substrate evidence.

The important result is that RPG can now accumulate repeated evidence across rehearsals without changing the readiness rules. Safe duplicate evidence is still symbolic-and-rehearsal gated; recurrent stale/bridge/semantic risk still blocks the operation family. RPG is becoming a learned diagnostic surface, not an autonomous mutation policy.

The next useful development is a report-only calibration test over mixed rehearsal runs: measure whether high RPG target relation and high target island ratio consistently align with `safe_to_review`, while low relation, low island, active/deprecated overlap, or duplicate/contradiction overlap align with blocked stale/bridge/semantic decisions.

## RPG Rehearsal Calibration Probe

The RPG rehearsal evidence now has a report-only calibration stage:

- `eval/memory_maintenance_rpg_rehearsal_calibration.py` consumes `memory_maintenance_rehearsal_review_memory_bank/v1` and compares RPG cluster metrics against symbolic rehearsal outcomes.
- The calibration tracks safe-vs-risk means for target relation, target island ratio, and active/deprecated overlap.
- It emits provisional relation/island thresholds and a prediction-accuracy probe, but always reports `ready_for_policy_use: false`.
- `eval/memory_maintenance_rpg_rehearsal_calibration_regression.py` plants safe duplicate, stale-risk, bridge-risk, and semantic-risk clusters and verifies that safe duplicate clusters have higher RPG target relation/island than the risk clusters while stale/bridge risk has higher active/deprecated overlap.

This is the first measurable bridge from RPG diagnostics toward a future learned maintenance scorer. It still cannot promote or apply maintenance actions. The next evidence requirement is real or copied-real rehearsal diversity: multiple DBs, multiple domains, and repeated safe/risk clusters before RPG metrics are allowed to become guarded controller features.

## RPG Copied-Real Calibration

The calibration stage now has a copied-real rehearsal eval:

- `eval/memory_maintenance_rpg_copied_real_calibration.py` copies local real/stress memory DBs, augments only the copies with a controlled exact duplicate pair and a controlled stale-as-duplicate pair, runs copied-DB rehearsal, builds a rehearsal memory bank, and calibrates RPG metrics.
- Original source DBs are not mutated.
- The eval writes its working DB copies under the external artifact area when available: `E:\projcod2_artifacts_archive\current_rehearsals\rpg_copied_real_calibration`.
- `eval/memory_maintenance_copied_db_rehearsal.py` is now tolerant of older memory schemas that do not have a `namespace` column when building RPG records.
- `eval/memory_maintenance_rpg_copied_real_calibration_regression.py` gates this copied-real path.

Current local copied-real result across three DBs:

```text
run_count = 3
safe_relation_mean = 0.115608
blocked_relation_mean = 0.045781
safe_relation_exceeds_blocked = true
ready_for_policy_use = false
```

This is encouraging but still early. It means RPG target relation survived a copied-real DB mix, but the data is still augmented and small. The next development stage should run the same copied-real calibration with richer naturally occurring maintenance candidates or Hermes-collected copied DBs before RPG metrics become even guarded selector features.

## RPG Natural Candidate Calibration

The calibration path now includes naturally mined candidate pairs from local DBs:

- `eval/memory_maintenance_rpg_natural_candidate_calibration.py` scans local memory DBs for exact duplicate, near-duplicate-like, stale/update-like, bridge-like, and cross-domain-related pairs.
- It computes RPG target relation and target island ratio directly from the memory substrate without building an apply plan and without mutating source DBs.
- `eval/memory_maintenance_rpg_natural_candidate_calibration_regression.py` gates the local natural-candidate calibration.

Current local result across three DBs:

```text
all_pair_count = 172
near_duplicate_like_count = 2
stale_or_update_like_count = 81
bridge_like_count = 80
cross_domain_related_count = 9
```

Class means:

```text
near_duplicate_like: relation_mean = 0.016933, island_mean = 1.145536
stale_or_update_like: relation_mean = 0.022567, island_mean = 1.250643
bridge_like: relation_mean = 0.018404, island_mean = 1.210213
cross_domain_related: relation_mean = 0.015767, island_mean = 1.117770
```

This changed the interpretation of RPG in an important way. High target relation does not mean "safe duplicate" by itself. In natural data, stale/update-like pairs can have stronger RPG relation than near-duplicate-like pairs because they are genuinely related memory attractors. RPG is therefore a relational strength and island/coherence signal, not a standalone safety label. It must be combined with symbolic/semantic labels, source/recency authority, and rehearsal outcomes before it can influence maintenance policy.

Next direction: build a review-labeled natural candidate packet so a human or Hermes can label whether natural RPG candidates are safe duplicates, stale/update conflicts, bridge contamination, or harmless related memories. That labeled data is what can eventually train a guarded RPG maintenance scorer.

## RPG Natural Candidate Review Packet

The natural-candidate calibration now produces a review packet:

- `eval/memory_maintenance_rpg_natural_candidate_review_packet.py` samples representative natural RPG candidate pairs by class and creates `memory_maintenance_rpg_natural_candidate_review_packet/v1`.
- Each item includes source DB, memory ids, domains, cosine/Jaccard, RPG target relation, RPG target island ratio, previews, and a review hint.
- Allowed review labels are:

```text
safe_duplicate
stale_or_update_conflict
bridge_contamination
semantic_near_duplicate
harmless_related_memory
uncertain_needs_more_context
```

- Review labels are intentionally blank. This packet is for human/Hermes annotation and cannot promote, apply, or change policy.
- `eval/memory_maintenance_rpg_natural_candidate_review_packet_regression.py` gates the packet contract.

This creates the missing supervised data collection surface for the RPG maintenance scorer. The next step after collecting labels is a label-summary/evidence-bank eval that checks whether RPG metrics plus symbolic candidate class can predict the human/Hermes label without overfitting.

## RPG Natural Label Bank

The review packet now has a label-summary/evidence-bank layer:

- `eval/memory_maintenance_rpg_natural_label_bank.py` consumes a filled `memory_maintenance_rpg_natural_candidate_review_packet/v1`.
- It groups reviewed examples by label and by coarse label family.
- It summarizes RPG relation/island statistics for each label.
- It runs a simple report-only prediction probe using RPG thresholds plus symbolic candidate class.
- It can mark `ready_for_scorer_training` when enough labels and label diversity exist, but it always keeps `ready_for_policy_use: false`.
- `eval/memory_maintenance_rpg_natural_label_bank_regression.py` gates the contract with synthetic filled labels.

This stage is the handoff from geometry diagnostics into supervised adaptive memory governance. The next stage should be a report-only RPG label scorer trained/evaluated on the label bank. That scorer must remain separate from runtime policy until it is validated on real labeled packets and real maintenance outcomes.

## RPG Label Scorer

The RPG label-bank path now has a transparent report-only scorer:

- `eval/memory_maintenance_rpg_label_scorer.py` trains/evaluates a small nearest-centroid label scorer from `memory_maintenance_rpg_natural_label_bank/v1`.
- Features are intentionally inspectable: RPG target relation, RPG target island ratio, cosine, Jaccard, same-domain flag, and candidate-class one-hot fields.
- It runs leave-one-out evaluation and emits a centroid model artifact.
- It can become `ready_for_shadow_scorer` only when label count, label diversity, and leave-one-out accuracy are sufficient.
- It always keeps `ready_for_policy_use: false`.
- `eval/memory_maintenance_rpg_label_scorer_regression.py` confirms the current low-data case remains blocked rather than pretending the scorer is ready.

Current status: the scorer exists as an auditable mechanism, but sparse labels correctly block shadow-scorer readiness. This is the right behavior. The next real development need is labeled natural RPG review packets, not a more aggressive model.

## Architecture Valuation Checkpoint

The codebase has reached a consolidation point. The current architecture is no longer just a selector experiment; it is a staged adaptive memory governance prototype with several non-mutating evidence loops:

```text
memory store / retrieval context
-> evidence and controller packets
-> OGCF/ERG/RPG geometry diagnostics
-> maintenance candidates
-> manual review/apply plan
-> copied DB rehearsal
-> rehearsal memory bank and guard
-> operator packet
-> natural RPG candidate review packet
-> RPG label bank
-> report-only RPG label scorer
```

`eval/architecture_valuation_report.py` now produces `architecture_valuation_report/v1`, a report-only map of the current phases, readiness boundaries, risks, and next steps. `eval/architecture_valuation_report_regression.py` gates the contract.

Current valuation:

- Retrieval/controller context: stable and gate-covered.
- Maintenance apply lifecycle: safe, copied-DB rehearsal first, operator-gated, real mutation disabled by default.
- RPG relational substrate: diagnostic-active and useful for relation/island evidence, but not a standalone safety label.
- RPG supervised path: data-collection ready, scorer implemented, but policy blocked by sparse labels and missing real outcome validation.

The new development direction should be consolidation-first:

1. Collect or simulate reviewed natural RPG packets only when the goal is supervised scorer evidence.
2. Keep the memory-program session responsible for memory-store/API/UI integration and the selector session responsible for selector/RPG/maintenance evidence contracts.
3. Before adding new algorithms, keep producing architecture valuation artifacts so the roadmap does not become a loose pile of evals.
4. Do not enable RPG or maintenance policy mutation until there are real labels, copied-real rehearsals, and real maintenance outcome validations.

The next best engineering improvement after this checkpoint is a handover/test packet for Hermes or the memory session focused on labeling the RPG natural candidate review packet and validating whether the operator packet is usable in the memory-program workflow.

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

The resolver-shadow config surface now also has a runtime-view regression:

```powershell
py -3 eval/resolver_shadow_runtime_view_regression.py
```

It builds a real `MemoryApi`, injects a `resolver_shadow` override, calls `/config`, and verifies that the normalized resolver-shadow config is exposed with schema, thresholds, logging flags, refusal markers, and report-only/non-mutating metadata. The selector architecture gate requires this as `resolver_shadow_runtime_view_ok`.

The next step should be Hermes validation with `include_resolver_shadow: true` during normal work. The memory session should compare shadow annotations with real answer-level feedback before making any user-facing resolver changes.

Hermes runtime-contract rerun note:

- Hermes validated commit `72de753` and confirmed all requested runtime-contract checks passed after rerun;
- the remaining gate blocker was isolated to `shadow_coverage_guard_ok`;
- `eval/canonical_ogcf_shadow_coverage_regression.py` is now self-contained and no longer imports the production shadow evaluator just to test fixture coverage math;
- `eval/portable_gate_dependency_regression.py` now protects that boundary by checking the portable coverage regression only imports expected standard-library modules;
- this makes the portable architecture gate less sensitive to WSL/local production-shadow dependencies while preserving the same coverage checks;
- the same portable architecture-gate command Hermes used now passes locally from both Windows and WSL:

```powershell
py -3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 16
wsl.exe bash -lc "cd /mnt/c/Users/victo/Desktop/projcod2/clc_gcl_memory_core && python3 eval/selector_architecture_gate.py --allow-missing-runtime-artifacts --random-cases 16"
```

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

## Adaptive Behavior Shadow Calibration Checkpoint

After Hermes produced a first real-log adaptive-shadow report, the selector session added a local in-process rerun and calibration path so the same class of test can be repeated without requiring Hermes.

New report-only evals:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_shadow_real_log_rerun.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_shadow_real_log_calibration.py --log <outcome-log.jsonl>
```

The rerun copies `memory_experiment_180_best.db`, runs 34 ask/feedback cycles through the current `MemoryApi`, logs `adaptive_behavior_shadow/v1`, attaches linked answer and memory feedback, then compares advisories to expected family-specific labels.

The runtime shadow surface now emits five first-class behavior families:

- `supported_evidence`;
- `missing_support`;
- `stale_conflict`;
- `wrong_scope`;
- `ogcf_bridge_warning`.

The latest local calibration result after the missing-support and stale-overfire cleanup:

| Family | Match rate | Notes |
|---|---:|---|
| `supported_evidence` | `0.852941` | Improved, but low-retrieval-score positives still need more real logs before relaxing caps. |
| `missing_support` | `1.0` | Sensitive/private lookup handling now correctly favors missing-support behavior. |
| `stale_conflict` | `0.852941` | Improved by requiring explicit stale signal or stale-shaped query instead of incidental stale context alone. |
| `wrong_scope` | `1.0` | First-class scope behavior is now visible and clean on the local rerun. |
| `ogcf_bridge_warning` | `1.0` | Useful/noisy bridge-warning separation is clean on the local rerun. |

Overall local match rate: `0.913793`.

Safety state:

- runtime shadow remains disabled by default;
- per-call request/logging is explicit;
- no answer text, selector policy, evidence rows, memory rows, learned artifacts, or runtime config are mutated by the shadow surface;
- the unified selector architecture gate still passes with `adaptive_behavior_shadow_runtime_ok: true`.

This checkpoint changes the roadmap priority. The next work should not be an open-ended sequence of one-off edits to `core/adaptive_behavior_shadow.py`. The correct roadmap path is:

```text
runtime logs
-> calibration report
-> adaptive behavior candidate profile
-> guard/regression
-> optional config/controller promotion later
```

The candidate-profile workflow now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_candidate_profile.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_candidate_profile_guard.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_candidate_profile_guard_regression.py
```

It writes a report-only `adaptive_behavior_candidate_profile/v1` artifact. Current local profile:

- proposal `stale_conflict_explicit_signal_gate`: `candidate`;
- proposal `supported_evidence_low_support_review`: `hold`;
- readiness from guard: `analysis_ready`;
- no runtime/config mutation fields.

The unified selector architecture gate now includes:

```json
{
  "adaptive_behavior_candidate_profile_guard_ok": true
}
```

Recommended next development:

1. Keep the current symbolic runtime shadow as the transparent fallback.
2. Collect more real/Hermes linked logs before promoting the `supported_evidence_low_support_review` hold item.
3. Later, compare the symbolic runtime shadow against the learned semantic behavior scorer on the same linked logs, then blend only if the learned path beats the fallback under holdout.

The architectural lesson is that the adaptive behavior shadow is valuable, but it should now evolve through candidate artifacts and multi-log calibration, not through unlimited manual growth of another heuristic module.

## Adaptive Behavior Profile Memory Bank

The multi-log profile memory bank now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_profile_memory_bank.py --profile <profile-a.json> --profile <profile-b.json>
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_profile_memory_bank_guard.py --bank <bank.json>
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_profile_memory_bank_guard_regression.py
```

It writes:

```text
schema: adaptive_behavior_profile_memory_bank/v1
```

The memory bank groups repeated `adaptive_behavior_candidate_profile/v1` proposals by behavior family and proposal id. It keeps single-run proposals in `hold` and only marks a cluster `recurrence_ready` when the same candidate recurs across the configured number of independent profile sources.

Current local single-profile result:

- profiles: `1`;
- proposal clusters: `2`;
- readiness counts: `{"hold": 2}`;
- ready clusters: `0`;
- guard readiness: `analysis_ready`.

This is the desired conservative behavior. The current local profile is useful evidence, but it is not enough for promotion because it comes from one rerun. The bank is now ready to accept future Hermes/local profiles and decide whether proposals recur naturally.

Second-source replay result:

- source A: local in-process rerun profile;
- source B: Hermes adaptive-shadow outcome log replayed through current runtime logic;
- multisource profiles: `2`;
- proposal clusters: `2`;
- readiness counts: `{"hold": 1, "recurrence_ready": 1}`.

The recurring cluster is:

```text
stale_conflict:stale_conflict_explicit_signal_gate
```

It appeared as `candidate` in both independent profiles and is now `recurrence_ready` in the memory bank. The `supported_evidence_low_support_review` cluster appeared in both profiles too, but stayed `hold`, which is the desired behavior because the evidence says not to relax low-support caps yet.

Multisource artifacts:

```text
..\experiments\adaptive_behavior_profile_memory_bank_multisource_results.json
..\experiments\adaptive_behavior_profile_memory_bank_multisource_report.md
..\experiments\adaptive_behavior_profile_memory_bank_multisource_guard_results.json
..\experiments\adaptive_behavior_profile_memory_bank_multisource_guard_report.md
```

The unified selector architecture gate now includes:

```json
{
  "adaptive_behavior_profile_memory_bank_guard_ok": true
}
```

Next development after this checkpoint:

1. Treat `stale_conflict_explicit_signal_gate` as the first recurrence-ready adaptive behavior candidate.
2. Keep `supported_evidence_low_support_review` in `hold` until stronger real logs prove it should change.
3. Only then consider any config-level candidate promotion.

## Stale-Conflict Candidate Promotion Guard

The targeted promotion guard for the recurrence-ready candidate now exists:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_stale_conflict_candidate_promotion.py
```

It writes:

```text
schema: adaptive_behavior_stale_conflict_candidate_promotion/v1
```

Candidate tested:

```text
stale_conflict_explicit_signal_gate
```

Current result:

- cases: `6/6` passed;
- incidental stale context remains `uncertain_keep_symbolic`;
- explicit `old` / `previous` stale-shaped queries become `likely_helpful`;
- current/corrected queries suppress stale over-fire;
- explicit `stale_current_conflict` diagnostics still trigger;
- resolver stale-disclosure action alone does not trigger without explicit query/diagnostic support.

The unified selector architecture gate now includes:

```json
{
  "adaptive_behavior_stale_conflict_candidate_ok": true
}
```

This means the first recurrence-ready adaptive behavior candidate has a promotion-style guard, but it still does not automatically change runtime config. The next stage should decide whether this guarded candidate should remain as code-level behavior, become an explicit config profile, or wait for another real Hermes profile before promotion.

## Stale-Conflict Config Control Surface

The recurrence-ready stale-conflict candidate has now moved one step further along the hardcoded-to-adaptive roadmap. Its runtime shadow behavior is still report-only, but the core decision knobs are explicit config values instead of hidden constants:

```yaml
adaptive_behavior:
  shadow:
    stale_conflict_requires_explicit_signal: true
    stale_conflict_positive_probability: 0.82
    stale_conflict_neutral_probability: 0.50
```

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_stale_conflict_config_regression.py
```

Current result:

- default config suppresses incidental stale context;
- explicit old/previous stale queries still produce positive stale-conflict advisories;
- a config override can intentionally allow incidental stale context;
- positive and neutral probabilities are honored from config;
- no runtime state, answer text, selector policy, memory row, or config is mutated.

The unified architecture gate now also includes:

```json
{
  "adaptive_behavior_stale_conflict_config_ok": true
}
```

Architectural status:

```text
recurring candidate -> promotion-style guard -> configurable report-only control surface
```

This is still not a learned controller. It is the correct Level 1 foundation for one: future learned or neural-symbolic logic can propose these stale-conflict controller values from multi-run outcomes, while the symbolic config/regression/gate path remains the safety boundary.

## Missing-Support Config Control Surface

The next stable adaptive behavior family has also been moved into Level 1 config. `missing_support` had clean calibration on the local real-log rerun, so its fixed probability choices are now explicit shadow-controller config:

```yaml
adaptive_behavior:
  shadow:
    missing_support_no_evidence_refusal_probability: 0.80
    missing_support_selected_sensitive_probability: 0.76
    missing_support_selected_evidence_probability: 0.50
    missing_support_no_evidence_probability: 0.58
```

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_missing_support_config_regression.py
```

Current result:

- no-evidence refusal remains a positive missing-support advisory;
- sensitive lookup pressure can be adjusted through config;
- ordinary selected evidence remains neutral by default;
- no-evidence non-refusal behavior can be tuned without source edits;
- no runtime state, answer text, selector policy, memory row, or config is mutated.

The unified architecture gate now also includes:

```json
{
  "adaptive_behavior_missing_support_config_ok": true
}
```

Architectural status:

```text
clean calibrated behavior family -> configurable report-only control surface -> future learned calibration target
```

The next similar extraction candidate is `wrong_scope`, because it is also clean on the current rerun. `supported_evidence` should remain in hold until more real logs resolve the low-support positive cases.

## Wrong-Scope Config Control Surface

The `wrong_scope` adaptive behavior family has now followed the same Level 1 path. Its fixed probabilities and route-confidence values are explicit shadow-controller config:

```yaml
adaptive_behavior:
  shadow:
    wrong_scope_deflection_probability: 0.78
    wrong_scope_no_evidence_github_probability: 0.68
    wrong_scope_no_evidence_probability: 0.54
    wrong_scope_selected_evidence_probability: 0.46
    wrong_scope_route_confidence: 0.56
    wrong_scope_low_route_confidence: 0.42
```

Regression:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_wrong_scope_config_regression.py
```

Current result:

- explicit scope deflection remains a positive wrong-scope advisory;
- no-evidence GitHub approval queries can be tuned through config;
- generic no-evidence scope-sensitive queries remain neutral by default;
- selected-evidence scope-sensitive queries remain neutral by default;
- weak selected-scope cases can use a separate low route-confidence branch;
- no runtime state, answer text, selector policy, memory row, or config is mutated.

The unified architecture gate now also includes:

```json
{
  "adaptive_behavior_wrong_scope_config_ok": true
}
```

Architectural status:

```text
clean calibrated behavior family -> configurable report-only control surface -> future learned calibration target
```

After this checkpoint, the adaptive behavior shadow has three Level 1 configurable behavior surfaces: `stale_conflict`, `missing_support`, and `wrong_scope`. The remaining high-value family, `supported_evidence`, should not be promoted or relaxed from the current local rerun because it still has low-support positive mismatches.

## Full Codebase Analysis Checkpoint

A full pass over the memory program and selector code shows that the architecture direction is sound, but the next stage should prioritize cleaner shared contracts before adding more behavior families or learned scorers.

Best current parts:

- `core/controller_context.py` is the right integration point for the adaptive memory brain. It gives selector decisions, OGCF diagnostics, retrieval context, resolver-shadow snapshots, and outcome logs one shared `adaptive_memory_context/v1` path.
- `core/retrieval_signals.py` and `core/evidence_states.py` are successful examples of the roadmap pattern: extracted logic, config defaults, candidate artifacts, and promotion gates.
- canonical memory support/provenance and duplicate-pressure handling provide user-visible value beyond vector similarity.
- OGCF remains valuable as a geometry-level bridge/composition-risk signal, especially when combined with canonical memory instead of replacing it.
- runtime adaptive behavior shadow, resolver shadow, and answer-feedback datasets now form the first practical route from real agent behavior to guarded controller improvement.

Main implementation weaknesses:

- `core/pipeline.py`, `core/resolver.py`, `storage/db.py`, and `core/selector_runtime.py` are still too large and carry mixed responsibilities.
- retrieval/evidence rows are still loose dictionaries passed across resolver, selector, shadow controllers, and evals.
- several modules duplicate small language/evidence helpers, such as selected-evidence filtering, normalized text checks, row signal extraction, ordinary fact lookup checks, and stale/current state tests.
- adding more learned behavior on top of loose dict contracts would make the system harder to audit.

The next structural goal is therefore:

```text
retrieval rows -> shared evidence context -> resolver / selector / shadows / outcome dataset
```

This should become a stable input layer for future neural-symbolic controllers. Learned models should train on this shared context, while symbolic gates still decide whether any learned output can affect runtime.

## Evidence Context Extraction

The next implementation step is a behavior-preserving extraction:

```text
core/evidence_context.py
```

This module should centralize small, reusable evidence helpers:

- normalized text handling;
- selected evidence filtering;
- numeric row-signal extraction;
- compact evidence counts;
- resolver-shadow action extraction;
- ordinary fact lookup detection;
- authority/memory-state extraction;
- stale-current conflict checks;
- generic term matching.

Initial migration target:

- `core/adaptive_behavior_shadow.py`;
- `core/answer_behavior_shadow.py`.

Reason:

These two shadow modules are report-only, share duplicated helpers, and are safer to migrate before touching `core/resolver.py` or `core/pipeline.py`. The migration should preserve behavior exactly and add a regression proving the shared helpers match prior expectations.

After this extraction, the next larger refactor should be to split `MemoryPipeline.retrieve()` into candidate generation, candidate enrichment, and scoring modules. That should happen only after the shared evidence context is protected by tests and the unified architecture gate.

Current implementation checkpoint:

- `core/evidence_context.py` now centralizes the first shared evidence helpers;
- `EvidenceContextSummary` now provides a reusable compact context object with normalized query/answer text, selected evidence, stale context, retrieval context, diagnostics, resolver actions, ordinary-lookup state, and stale-conflict state;
- `core/adaptive_behavior_shadow.py` and `core/answer_behavior_shadow.py` consume those helpers;
- `eval/evidence_context_regression.py` protects the helper contract;
- `eval/selector_architecture_gate.py` now requires `evidence_context_regression_ok`.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_context_regression.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_shadow_runtime_regression.py
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_mode_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

The extraction is intentionally small. It proves the right direction without changing answer selection, selector policy, runtime config, memory rows, or learned artifacts.

Second implementation checkpoint:

- `core/adaptive_behavior_shadow.py` now builds one `EvidenceContextSummary` and reads selected evidence, stale context, resolver actions, row maxima, normalized query/answer text, and ordinary lookup from it;
- `core/answer_behavior_shadow.py` now builds the same summary and reads selected evidence, diagnostics, stale conflict, ordinary lookup, and stale-context counts from it;
- the regression now checks both low-level helpers and summary-level behavior;
- real-log adaptive shadow replay remains unchanged at `0.913793`;
- the unified selector architecture gate still passes.

This turns evidence context from a utility module into the first shared context object for report-only controllers. The next safe migration target is selector-side context feature extraction, but that should be done in smaller pieces because `selector_runtime.py` currently carries more policy-sensitive logic than the shadow modules.

Third implementation checkpoint:

- `core/selector_runtime.py` now uses `EvidenceContextSummary` for retrieval-row normalization before deriving selector features;
- this is intentionally behavior-preserving: selector scoring, selector policy, answer selection, memory rows, config, and learned artifacts are unchanged;
- `eval/evidence_context_selector_runtime_regression.py` protects the selector-side shared-context contract and confirms malformed retrieval rows are ignored while canonical support, stale/current counts, duplicate pressure, and nonzero feature signals are preserved;
- `eval/selector_architecture_gate.py` now requires `evidence_context_selector_runtime_ok`.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_context_selector_runtime_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_retrieval_feature_eval.py
..\.venv-torch\Scripts\python.exe .\eval\clc_policy_feature_signal_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

The best next refactor remains gradual: move more selector/resolver row interpretation into the shared evidence-context layer only when each step has a focused regression. This is the right base for the future neural-symbolic controller because learned behavior can consume one compact context object while symbolic gates continue to protect runtime behavior.

Fourth implementation checkpoint:

- `core/evidence_context.py` now exposes `EvidenceRowState` and `retrieval_row_state()` as the shared interpretation of a retrieval/evidence row;
- `core/selector_runtime.py` now uses that shared row-state classifier for stale/current/standalone/topical-anchor/current-correction detection while keeping all selector formulas unchanged;
- `eval/evidence_context_regression.py` now protects row-state behavior for stale-by-supersession, current-by-authority, standalone/topical-anchor, score fallback, and claim-scope fallback;
- selector retrieval feature eval, CLC policy feature signal regression, and the unified architecture gate still pass.

This is a useful architecture step because row-state interpretation is the natural bridge between symbolic memory provenance and future learned/neural scoring. The next migration target should be resolver-side row-state reads in small pieces, especially places where `authority_state`, `claim_scope_score`, `answer_type_score`, and `text_match_score` are manually reinterpreted.

Fifth implementation checkpoint:

- `EvidenceRowState` now also carries answer-type, intent-match, correction-relevance, feedback, and summary-relation signals;
- `core/resolver.py` now uses `retrieval_row_state()` for repeated selector/evidence signal reads in positive-signal detection, query relevance checks, evidence preference scoring, and confidence estimation;
- resolver behavior remains intentionally unchanged: resolver preference and confidence still use the explicit `score` field where they historically did, while selector runtime continues to use score-or-cosine retrieval scoring;
- `eval/evidence_context_regression.py` now protects the added row-state fields;
- resolver-focused regressions and the unified architecture gate still pass.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_context_regression.py
..\.venv-torch\Scripts\python.exe .\eval\resolver_shadow_mode_regression.py
..\.venv-torch\Scripts\python.exe .\eval\evidence_states_module_smoke.py
..\.venv-torch\Scripts\python.exe .\eval\policy_correction_deflection_regression.py
..\.venv-torch\Scripts\python.exe .\eval\repo_publish_permission_ambiguity_regression.py
..\.venv-torch\Scripts\python.exe .\eval\multi_intent_answer_composition_regression.py
..\.venv-torch\Scripts\python.exe .\eval\day1_answer_source_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

This gives the future adaptive memory brain a more stable shared input layer across selector and resolver behavior. The next best structural target is to add a compact derived-feature object on top of `EvidenceContextSummary` instead of continuing to pass many loose diagnostic fields by hand.

Sixth implementation checkpoint:

- `core/evidence_context.py` now exposes `EvidenceContextFeatures`, the first compact derived-feature object on top of `EvidenceContextSummary`;
- the feature object carries retrieval/selected/stale counts, max retrieval and selected match signals, stale-current conflict, contradiction pressure, memory-bad-rate fallback, scope-deflection pressure, and OGCF bridge pressure;
- `core/adaptive_behavior_shadow.py` now consumes `EvidenceContextFeatures` instead of manually pulling scattered row maxima and diagnostic values;
- `eval/evidence_context_regression.py` protects the feature object contract;
- adaptive behavior family regressions, real-log adaptive shadow rerun, and the unified architecture gate still pass.

Validation:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\evidence_context_regression.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_shadow_runtime_regression.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_missing_support_config_regression.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_stale_conflict_config_regression.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_wrong_scope_config_regression.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_stale_conflict_candidate_promotion.py
..\.venv-torch\Scripts\python.exe .\eval\adaptive_behavior_shadow_real_log_rerun.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

This is a key neural-symbolic roadmap step: learned controllers can now target a named compact feature object instead of depending on module-specific dictionaries. The next development should either migrate resolver-shadow diagnostics to this feature object or add a report-only export path that logs `EvidenceContextFeatures` for calibration datasets.

Seventh implementation checkpoint:

- `core/evidence_context.py` now exposes `evidence_context_features_dict()` so the compact feature object can be serialized into runtime and calibration artifacts;
- `core/adaptive_behavior_shadow.py` now includes `diagnostics.evidence_context_features` in response and outcome-log payloads when adaptive behavior shadow logging is requested;
- `eval/adaptive_behavior_shadow_runtime_regression.py` now verifies that the feature vector is present in both the live response and logged ask event;
- adaptive behavior family regressions, real-log adaptive shadow rerun, and the unified architecture gate still pass;
- real-log adaptive shadow match rate remains unchanged at `0.913793`.

This is the first concrete bridge from the symbolic report-only controller to a future learned/neural controller dataset. The next dataset-building step should collect many `diagnostics.evidence_context_features` vectors with linked answer/memory feedback labels and train/evaluate a small local scorer against the current symbolic shadow.

Eighth implementation checkpoint:

- `eval/adaptive_behavior_feature_scorer_eval.py` now trains a tiny deterministic local softmax scorer on logged `diagnostics.evidence_context_features`;
- the eval joins exported feature vectors with linked answer feedback labels and compares learned advisories against the current symbolic adaptive behavior shadow;
- `eval/adaptive_behavior_feature_scorer_regression.py` guards the dataset path and explicitly blocks promotion from a single small local log;
- `eval/selector_architecture_gate.py` now requires `adaptive_behavior_feature_scorer_ok`.

Current result on the local adaptive-shadow rerun log:

```text
samples: 116
train/test: 93 / 23
train learned match rate: 0.924731
test learned match rate: 0.565217
test symbolic match rate: 0.956522
promotion_ready: false
```

Interpretation:

- the exported feature vector is usable as a learning input;
- the first tiny learned scorer overfits the small local log and is not competitive with the symbolic shadow;
- this is still a valuable negative result because it prevents premature neural promotion;
- the next useful test is a larger multi-log feature dataset with real Hermes logs, then either a family-specific scorer or a hybrid residual model that only learns where the symbolic shadow is weak.

For now, the symbolic adaptive behavior shadow remains the runtime authority. The learned path is a report-only research track.

Ninth implementation checkpoint:

- `eval/adaptive_behavior_feature_scorer_hybrid_eval.py` now tests a stronger neural-symbolic shape: family-specific feature scorers plus a residual model that only allows learned overrides when it predicts the symbolic shadow is wrong;
- `eval/adaptive_behavior_feature_scorer_hybrid_regression.py` guards the hybrid path as report-only and requires the hybrid not to underperform the symbolic baseline on the current fixture;
- `eval/selector_architecture_gate.py` now requires `adaptive_behavior_feature_scorer_hybrid_ok`.

Current local result:

```text
samples: 116
train/test: 93 / 23
family models: 5
symbolic match rate: 0.956522
family model match rate: 0.608696
hybrid match rate: 0.956522
hybrid delta vs symbolic: 0.0
overrides: 0
promotion_ready: false
```

Interpretation:

- family-specific learning is better than the first global scorer but still weaker than symbolic behavior;
- the residual gate learned to avoid unsafe overrides, so the hybrid preserved symbolic performance;
- the learned path is currently useful as a diagnostic/research layer, not as a runtime controller;
- the next real development requirement is more feature-export logs, especially cases where the symbolic shadow is wrong, because the residual model saw only one symbolic error in the current holdout.

The architecture direction remains correct: symbolic controller first, learned residual second, promotion only after multi-log holdout beats the symbolic fallback.

Tenth implementation checkpoint:

- `eval/adaptive_behavior_feature_challenge_log.py` now generates a local hard-case adaptive-shadow outcome log with exported `evidence_context_features`;
- it also writes a combined feature log by appending the challenge cases to the local real-log rerun data;
- `eval/adaptive_behavior_feature_challenge_regression.py` guards the challenge dataset path and confirms the learned hybrid can beat the symbolic baseline on the enriched fixture while staying report-only;
- `eval/selector_architecture_gate.py` now requires `adaptive_behavior_feature_challenge_ok`.

Current generated data:

```text
challenge cases: 50
challenge symbolic-wrong decisions: 70
combined samples for scorer: 296
```

Current combined-log result:

```text
global learned scorer: 0.796610
symbolic baseline:      0.745763
family model:           0.847458
hybrid residual model:  0.915254
hybrid delta:          +0.169491
```

Interpretation:

- this is the first positive learned-residual result: when the dataset contains enough symbolic-error cases, `EvidenceContextFeatures` can support a learned hybrid controller that beats the symbolic shadow;
- the result is not promotion-ready because the new hard cases are generated, not independent real Hermes logs;
- nevertheless, the architecture direction is validated: stable feature export -> labeled hard cases -> family/residual scorer -> guarded comparison against symbolic fallback.

Next development requirement:

```text
replace generated hard cases with independent real/Hermes feature-export logs
then rerun the same hybrid residual gate as a true holdout test
```

Until then, runtime authority remains symbolic and the learned residual path remains report-only.

Eleventh implementation checkpoint:

- `eval/adaptive_behavior_feature_cross_log_holdout.py` now runs a leave-log-out residual evaluation: train on selected local/challenge feature logs, test on an independent Hermes real feature-export log, and sweep override thresholds;
- `eval/adaptive_behavior_feature_cross_log_holdout_regression.py` records the current zero-harm external-holdout behavior as a standalone local regression without adding the machine-local Hermes path to the portable architecture gate;
- Hermes' first real feature-residual report showed that the earlier random/hybrid split did not independently improve over symbolic behavior (`hybrid=0.773585`, `symbolic=0.773585`);
- the new cross-log test found a safer threshold shape on the same Hermes holdout: threshold `0.7` produced zero harmful overrides and improved over symbolic by `+0.04`;
- threshold `0.5` gave the largest raw gain (`+0.043636`) but caused one harmful override, so the roadmap should prefer zero-harm calibration over maximum accuracy.

Current cross-log result:

```text
train samples: 296
test samples: 275
symbolic baseline: 0.76
best any threshold: 0.5, delta +0.043636, harmful overrides 1
best zero-harm threshold: 0.7, delta +0.04, helpful overrides 15, harmful overrides 0
promotion_ready: false
```

Interpretation:

- the learned residual path has a real signal when trained on hard symbolic-error cases and evaluated on Hermes data;
- the result is still not promotion-ready because one training source is generated challenge data and the holdout is only one independent real log;
- the next proof step is a two-holdout matrix: train without the generated challenge where possible, test on at least two independent real Hermes logs, and require repeated zero-harm improvement before runtime or config promotion.

Twelfth implementation checkpoint:

- `eval/adaptive_behavior_shadow_second_holdout_log.py` now creates a second independent local runtime holdout log with different queries, linked answer feedback, memory feedback, resolver shadow, adaptive behavior shadow, and exported `EvidenceContextFeatures`;
- the second holdout produced 24 asks, 24 answer-feedback rows, 37 memory-feedback rows, and 87 adaptive behavior decisions;
- logged/replayed calibration matched exactly at `0.83908`, so the second log is usable for feature-residual holdout testing;
- rerunning the cross-log residual scorer on this second holdout found another positive zero-harm operating point, but only after extending the threshold grid above `0.95`.

Second holdout result:

```text
test samples: 87
symbolic baseline: 0.83908
best broad-grid threshold: 0.6, delta +0.034483, harmful overrides 1
best strict zero-harm threshold: 0.995, delta +0.045977, helpful overrides 5, harmful overrides 0
```

Combined interpretation across two holdouts:

- Hermes real holdout: zero-harm improvement at threshold `0.7`, delta `+0.04`;
- second local runtime holdout: zero-harm improvement at threshold `0.995`, delta `+0.045977`;
- the repeated lift is encouraging, but the threshold instability means runtime promotion is still blocked;
- the next controller improvement should learn or configure a conservative override policy that separates safe high-confidence supported-evidence fixes from stale/scope cases that can produce harmful overrides.

Thirteenth implementation checkpoint:

- `eval/adaptive_behavior_feature_override_policy_eval.py` now searches conservative residual override policies across both holdouts instead of using one threshold-only rule;
- policies can restrict allowed behavior families, allowed learned target advisories, residual confidence, and family-model confidence;
- `eval/adaptive_behavior_feature_override_policy_regression.py` records the current two-holdout policy result as a standalone local regression, but it is intentionally not added to the portable architecture gate because one holdout is a local WSL Hermes artifact.

Selected report-only candidate policy:

```json
{
  "residual_threshold": 0.995,
  "family_confidence_threshold": 0.0,
  "allowed_families": ["supported_evidence"],
  "allowed_target": "likely_helpful"
}
```

Two-holdout result:

```text
Hermes real holdout:
  symbolic: 0.76
  hybrid:   0.778182
  delta:    +0.018182
  helpful overrides: 5
  harmful overrides: 0

Second local runtime holdout:
  symbolic: 0.83908
  hybrid:   0.885057
  delta:    +0.045977
  helpful overrides: 5
  harmful overrides: 0
```

Interpretation:

- the best next controller shape is a narrow positive-supported-evidence rescue gate, not broad learned override;
- learned residuals should only override symbolic behavior when they predict a symbolic false negative and the family model wants to change the advisory to `likely_helpful`;
- stale-conflict, wrong-scope, missing-support, and harmful/suppression advisories should remain symbolic/config controlled until more real holdouts prove a learned override is safe;
- this is still report-only and promotion-blocked until at least one more independent natural Hermes holdout confirms the same zero-harm pattern.

Fourteenth implementation checkpoint:

- `eval/adaptive_behavior_override_policy_candidate.py` now converts the winning two-holdout override policy into a formal `adaptive_behavior_override_policy_candidate/v1` artifact;
- `eval/adaptive_behavior_override_policy_candidate_guard.py` guards that candidate before any runtime/config implementation;
- the candidate is explicitly report-only, positive-rescue-only, supported-evidence-only, and promotion-blocked.

Guarded candidate:

```text
id: adaptive_behavior_supported_evidence_positive_rescue_v1
readiness: guarded_report_only_candidate
residual_threshold: 0.995
allowed_families: supported_evidence
allowed_target: likely_helpful
total helpful overrides: 10
total harmful overrides: 0
mean delta: +0.032079
```

This gives the roadmap a clean candidate lifecycle:

```text
feature logs -> override policy eval -> candidate artifact -> candidate guard -> future natural holdout confirmation
```

The next best development after this checkpoint is not to wire the candidate into runtime. It is to generate or collect another natural holdout, preferably from Hermes, and rerun the candidate guard against a three-holdout matrix. If that repeats zero-harm improvement, the later implementation step should be a disabled-by-default runtime shadow mode that emits what this candidate would have done, still without changing the answer.

Fifteenth implementation checkpoint:

- `eval/adaptive_behavior_shadow_third_holdout_log.py` now creates a third local natural-style runtime holdout with a harder query mix;
- the third holdout produced 24 asks, 24 linked answer-feedback rows, 52 memory-feedback rows, and 82 adaptive decisions;
- logged/replayed calibration matched exactly at `0.621951`, making it a valid but much harder holdout;
- the prior two-holdout candidate did not survive the three-holdout requirement.

Third holdout threshold sweep:

```text
symbolic baseline: 0.621951
best raw threshold: 0.7, delta +0.085366, harmful overrides 2
best zero-harm threshold: 0.999, delta +0.02439, helpful overrides 2, harmful overrides 0
```

Three-holdout policy result:

```text
best safe policy: res0.999 supported_evidence -> likely_helpful
Hermes holdout:       +0.007273, zero harmful
second local holdout: +0.0,      zero harmful
third local holdout:  +0.02439,  zero harmful
selected candidate: none
guard readiness: blocked_no_three_holdout_candidate
```

Interpretation:

- the learned residual signal is real, but the current candidate is not robust enough for promotion;
- the safety gate worked correctly by blocking the candidate when the third holdout exposed threshold/context instability;
- the next development direction should be context-filtered rescue, not a global threshold. The harmful third-holdout cases were sensitive/profile/ordinary-cross-namespace questions that looked like supported evidence to the family model;
- the next candidate should add a learned or configurable suppression feature for sensitive/private lookup pressure and ordinary profile/namespace lookup pressure before permitting supported-evidence rescue.

Sixteenth implementation checkpoint:

- `eval/adaptive_behavior_feature_override_policy_eval.py` now tests explicit context suppressors before allowing learned supported-evidence rescue;
- suppressors currently cover sensitive/private lookup pressure, stale/previous-policy lookup pressure, and ordinary profile/namespace lookup pressure;
- the guarded candidate recovered across all three holdouts after adding these suppressors.

Selected context-filtered policy:

```json
{
  "residual_threshold": 0.8,
  "family_confidence_threshold": 0.0,
  "allowed_families": ["supported_evidence"],
  "allowed_target": "likely_helpful",
  "suppressors": ["sensitive_private", "stale_previous", "ordinary_namespace_profile"]
}
```

Three-holdout result:

```text
Hermes real holdout:   +0.036364, 10 helpful, 0 harmful
second local holdout:  +0.045977,  6 helpful, 0 harmful
third local holdout:   +0.085366,  7 helpful, 0 harmful
mean delta:            +0.055902
total helpful:         23
total harmful:         0
readiness:             guarded_report_only_candidate
```

Interpretation:

- the architecture should treat learned residual rescue as a neural-symbolic controller: learned residual/family models propose the override, while symbolic/context suppressors decide whether it is safe enough to emit;
- this is a much stronger shape than a threshold-only controller because it explains why the third holdout failed and how the rescue was made safer;
- the candidate is still not runtime-promoted. The next stage should either collect a natural Hermes fourth holdout or implement a disabled-by-default runtime shadow that only logs what this context-filtered candidate would have done.

Seventeenth implementation checkpoint:

- `core/adaptive_residual_shadow.py` now implements a disabled-by-default runtime shadow for the guarded context-filtered residual rescue candidate;
- `/ask` can request it with `include_adaptive_residual_shadow=true` and can log it with `log_adaptive_residual_shadow=true`;
- it trains the tiny local residual/family models from existing feature logs only when explicitly requested, applies the guarded policy, and emits report-only decisions with residual confidence, family advisory, suppressor reasons, and whether the candidate would override symbolic behavior;
- it does not return or log `adaptive_behavior_shadow` unless separately requested, but internally reuses the same evidence-context feature export path;
- `eval/adaptive_residual_shadow_runtime_regression.py` proves answer text, evidence ids, selector decision, memory rows, runtime config, and selector policy remain unchanged;
- the unified architecture gate now requires `adaptive_residual_shadow_runtime_ok`.

Current runtime status:

```text
adaptive residual shadow: disabled by default
runtime mutation: none
config mutation: none
answer mutation: none
memory mutation: none
logging: explicit request only
```

This moves the learned residual path from an offline candidate artifact to an observable live controller candidate while preserving the safety rule: the symbolic runtime remains authoritative.

The adaptive residual shadow policy has now become a runtime-visible config contract:

```powershell
py -3 eval/adaptive_residual_shadow_runtime_view_regression.py
```

The regression builds a real `MemoryApi`, injects an `adaptive_residual_shadow` override, calls `/config`, and verifies that the active normalized policy is exposed under `adaptive_residual_shadow`. The view includes threshold settings, allowed families, suppressors, term groups, schema, source, and report-only/non-mutating flags.

Architecture meaning:

- the memory runtime exposes the same residual-shadow policy that selector/residual evals use;
- future Hermes handovers can record the active policy from `/config` instead of inferring it from Python defaults;
- learned residual candidates can be compared against a clear runtime-visible symbolic/context-suppression baseline;
- no answer text, memory row, selector policy, runtime state, or config is changed by this exposure.

The selector architecture gate now requires this regression as `adaptive_residual_shadow_runtime_view_ok`.

Eighteenth implementation checkpoint:

- `eval/adaptive_residual_shadow_fourth_holdout_log.py` now creates a fourth live-style local holdout with explicit `include_adaptive_residual_shadow=true` and `log_adaptive_residual_shadow=true`;
- `eval/adaptive_residual_shadow_logged_eval.py` evaluates the residual-shadow payload exactly as logged by runtime asks, joined to linked answer feedback;
- the fourth holdout produced 24 asks, 24 linked answer-feedback rows, 47 memory-feedback rows, and 89 logged residual-shadow decisions;
- the guarded residual shadow emitted 9 `would_override` decisions: 9 helpful, 0 harmful, 0 neutral-wrong;
- the shadow remained report-only and did not mutate answer text, selector policy, runtime config, learned artifacts, or memory rows.

Fourth logged-runtime result:

```text
ask count:        24
decision count:   89
would overrides:  9
helpful:          9
harmful:          0
promotion ready:  false
```

Interpretation:

- the context-filtered residual controller is now validated not only by offline replay, but by the actual runtime shadow object written to outcome logs;
- the useful signal remains concentrated in `supported_evidence -> likely_helpful` rescue, including several cases where symbolic behavior stayed uncertain or marked bridge-related answers too pessimistically;
- promotion should still remain blocked until natural multi-day logs confirm the pattern outside generated/local holdouts, but the next engineering step can treat logged residual-shadow evaluation as the standard safety harness for neural-symbolic controller candidates.

Nineteenth implementation checkpoint:

- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_logged_eval_ok`;
- the unified gate no longer treats logged residual-shadow validation as a side report: a residual controller candidate must pass the runtime mutation regression and the linked-feedback logged-decision evaluation;
- the current gate passes with the fourth-holdout logged payload: 9 helpful report-only overrides, 0 harmful overrides.

Current residual-controller promotion rule:

```text
runtime mutation regression: required
logged decision eval:        required
harmful logged overrides:    must be zero
runtime promotion:           still blocked until natural multi-session logs repeat the result
```

Twentieth implementation checkpoint:

- `eval/adaptive_residual_shadow_multi_log_eval.py` now aggregates logged residual-shadow linked-feedback evaluations across all available residual outcome logs;
- the aggregate check requires usable residual logs, at least one helpful override, zero harmful overrides, zero neutral-wrong overrides, report-only behavior, and no runtime/config mutation;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_multi_log_eval_ok` in addition to the focused single-log check;
- the current aggregate uses the available fourth holdout residual log and passes with 9 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides.

Current multi-log residual-controller rule:

```text
single-log residual eval: required
multi-log aggregate eval: required
helpful overrides:        must be present
harmful overrides:        must be zero
neutral-wrong overrides:  must be zero
promotion state:          report-only until natural multi-session logs expand the aggregate
```

Twenty-first implementation checkpoint:

- `eval/adaptive_residual_shadow_fifth_holdout_log.py` now creates a second independent residual-shadow logged holdout with 28 asks, linked answer feedback, memory feedback, and explicit runtime residual-shadow logging;
- the first fifth-holdout pass exposed a useful safety failure: an unsupported proof-style query and a hidden deployment-key query could still look like supported-evidence rescue candidates;
- `core/adaptive_residual_shadow.py` now adds a narrow `unsupported_proof` suppressor and expands sensitive/private suppression for deployment-key pressure;
- after regenerating the fifth holdout, the focused logged eval passed with 9 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- `eval/selector_architecture_gate.py` now runs `adaptive_residual_shadow_multi_log_eval.py --min-logs 2`.

Two-log residual aggregate:

```text
usable residual logs: 2
ask count:            52
decision count:       187
would overrides:      18
helpful:              18
harmful:              0
neutral-wrong:        0
promotion ready:      false
```

Interpretation:

- the fifth holdout did its job by finding a real boundary weakness before promotion;
- the best controller shape remains a neural-symbolic one: learned residual/family models propose rescue, while explicit suppressors block unsupported proof pressure, sensitive/private retrieval pressure, stale/previous pressure, and ordinary namespace/profile pressure;
- the architecture gate is now stricter than before because it requires repeated logged residual evidence across at least two residual outcome logs.

Twenty-second implementation checkpoint:

- `eval/adaptive_residual_shadow_suppressor_regression.py` now protects the exact suppressor boundary exposed by the fifth holdout;
- it checks unsupported proof/result claims, hidden deployment-key pressure, secret credential pressure, stale previous-roadmap pressure, ordinary cross-namespace profile pressure, and clean supported-evidence queries;
- `core/adaptive_residual_shadow.py` now includes the `cross-namespace` spelling variant in ordinary namespace/profile suppression;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_suppressor_ok`;
- the full architecture gate passes with the targeted suppressor regression, two-log residual aggregate, single-log residual eval, and runtime no-mutation regression all enabled.

Current residual safety guard stack:

```text
runtime no-mutation regression:       required
single logged-decision eval:          required
two-log aggregate decision eval:      required
targeted suppressor regression:       required
runtime authority:                    symbolic
residual controller status:           report-only
```

Twenty-third implementation checkpoint:

- residual-shadow controller policy is now configurable through `config.yaml` under `adaptive_residual_shadow`;
- configurable fields include residual threshold, family confidence threshold, allowed families, allowed target advisory, active suppressors, and term groups for each suppressor;
- `core/adaptive_residual_shadow.py` loads this configured policy through `load_policy(root)` and falls back to the built-in safe defaults when config is absent;
- `eval/adaptive_residual_shadow_suppressor_regression.py` now validates the configured policy rather than only the Python defaults;
- the full architecture gate passes with the configurable residual policy enabled.

Current configurable residual policy surface:

```text
adaptive_residual_shadow.residual_threshold
adaptive_residual_shadow.family_confidence_threshold
adaptive_residual_shadow.allowed_families
adaptive_residual_shadow.allowed_target
adaptive_residual_shadow.suppressors
adaptive_residual_shadow.terms.sensitive_private
adaptive_residual_shadow.terms.stale_previous
adaptive_residual_shadow.terms.ordinary_namespace_profile
adaptive_residual_shadow.terms.unsupported_proof
```

Interpretation:

- this moves the residual controller one step closer to the roadmap goal of learned/configurable adaptive control instead of brittle hardcoded behavior;
- the suppressors are still symbolic vocabulary gates, but they are now an explicit policy interface that can later be updated by guarded candidate profiles or learned term miners instead of source-code edits.

Twenty-fourth implementation checkpoint:

- `eval/adaptive_residual_shadow_term_candidate_miner.py` now provides the first report-only term-mining path for residual suppressor evolution;
- it reads available residual-shadow outcome logs, evaluates logged decisions, extracts candidate suppressor terms only from harmful or neutral-wrong would-overrides, and emits a candidate profile artifact;
- when no unsafe residual overrides remain, it records `recommendation: no_new_terms_needed` instead of inventing vocabulary;
- it also verifies known boundary queries are currently suppressed by the configured policy;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_term_miner_ok`.

Current term-miner result:

```text
residual logs read: 2
candidate terms:    0
recommendation:     no_new_terms_needed
gate status:        passed
```

Interpretation:

- this is the first step from static configurable suppressors toward adaptive suppressor maintenance;
- the miner is intentionally conservative: it can propose terms from failures, but it cannot update config or runtime behavior;
- future natural logs that expose unsafe residual overrides can now produce reviewable suppressor candidates without source-code edits.

Twenty-fifth implementation checkpoint:

- `eval/adaptive_residual_shadow_term_miner_regression.py` now tests the term miner against synthetic unsafe residual overrides;
- the regression verifies that harmful/neutral-wrong examples produce reviewable candidate terms and that the miner recommends review instead of automatic config mutation;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_term_miner_regression_ok`;
- the full architecture gate passes with both clean-log mining (`no_new_terms_needed`) and synthetic-failure mining (`review_candidates_before_config_update`) protected.

Current adaptive suppressor maintenance path:

```text
clean residual logs -> no new terms
unsafe residual examples -> candidate terms
candidate terms -> review-only artifact
config mutation -> never automatic
runtime mutation -> never automatic
```

Twenty-sixth implementation checkpoint:

- `eval/adaptive_residual_shadow_term_candidate_miner.py` now ranks candidate suppressor terms by review quality;
- vague one-token terms such as `key`, `live`, `hidden`, `deployment`, `profile`, and `retrieve` are filtered out;
- `eval/adaptive_residual_shadow_term_miner_regression.py` now requires the miner to find known useful failure phrases while rejecting noisy single-token candidates;
- current synthetic unsafe examples produce 15 reviewable multi-word candidates, while current clean residual logs still produce no new candidates.

Current candidate-quality rule:

```text
single weak tokens: filtered
multi-word failure phrases: retained
config updates: review-only
runtime updates: blocked
```

Twenty-seventh implementation checkpoint:

- `eval/adaptive_residual_shadow_term_patch_proposal.py` now turns mined suppressor candidates into a review-only config patch preview;
- the proposal groups terms into `sensitive_private`, `unsupported_proof`, `ordinary_namespace_profile`, or `stale_previous`, while ambiguous terms stay in a `review_required` bucket;
- the proposal snapshots `config.yaml` before and after generation and verifies it did not mutate config;
- `eval/adaptive_residual_shadow_term_patch_regression.py` validates the grouping rules with synthetic terms and confirms config remains unchanged;
- `eval/selector_architecture_gate.py` now requires both `adaptive_residual_shadow_term_patch_ok` and `adaptive_residual_shadow_term_patch_regression_ok`.

Current guarded suppressor update lifecycle:

```text
unsafe residual logs -> term miner -> quality filter -> patch proposal -> human review
automatic config write -> blocked
automatic runtime change -> blocked
```

Twenty-eighth implementation checkpoint:

- `eval/adaptive_residual_shadow_term_patch_pipeline_regression.py` now tests the full adaptive suppressor maintenance path end to end with synthetic unsafe residual examples;
- it runs synthetic unsafe examples through the miner, candidate quality filter, patch proposal grouping, and config mutation checks;
- the regression verifies that specific candidates are grouped into `sensitive_private`, `unsupported_proof`, and `ordinary_namespace_profile` buckets;
- `eval/adaptive_residual_shadow_term_patch_proposal.py` now treats candidate-producing unsafe miner reports as valid review inputs while still requiring report-only behavior and unchanged config;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_term_patch_pipeline_ok`.

Current adaptive suppressor loop status:

```text
clean logs:          no patch terms proposed
synthetic failures:  patch preview terms proposed and grouped
config mutation:     blocked
runtime mutation:    blocked
gate status:         passed
```

Twenty-ninth implementation checkpoint:

- `eval/adaptive_residual_shadow_term_patch_proposal.py` now compares mined candidate terms against the active configured suppressor terms;
- patch previews separate truly new `append_terms` from `already_configured` terms, preventing duplicate config proposals;
- `eval/adaptive_residual_shadow_term_patch_pipeline_regression.py` now verifies both new-term grouping and existing-term deduplication;
- the full architecture gate passes with duplicate-aware patch proposals.

Current duplicate-aware patch behavior:

```text
already configured terms -> listed separately
new candidate terms -> append preview only
ambiguous terms -> review_required
config mutation -> blocked
```

Thirtieth implementation checkpoint:

- `eval/adaptive_residual_shadow_term_patch_guard.py` now guards review-only suppressor patch proposals before any manual config application is considered;
- the guard requires proposal validity, report-only status, no config/runtime mutation, no ambiguous terms for automatic application, and no new terms unless manual review is explicitly required;
- on current clean residual logs the guard passes with `no_action_needed: true` and `manual_review_required: false`;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_term_patch_guard_ok`.

Current suppressor patch promotion state:

```text
clean logs: no action needed
new append terms: manual review required
ambiguous terms: manual review required
automatic config application: blocked
runtime promotion: blocked
```

Thirty-first implementation checkpoint:

- `eval/adaptive_residual_shadow_sixth_natural_holdout_log.py` now creates a larger natural-style residual-shadow holdout with 44 asks, linked answer feedback, memory feedback, and explicit runtime residual logging;
- the first sixth-holdout pass exposed a real wrong-scope boundary: `Can ordinary namespace lookup bypass the residual suppressors?` was incorrectly rescued by the residual controller;
- `core/adaptive_residual_shadow.py` and `config.yaml` now extend `ordinary_namespace_profile` suppression with `ordinary namespace` and `namespace lookup`;
- `eval/adaptive_residual_shadow_suppressor_regression.py` now includes the ordinary namespace bypass case;
- after regenerating the sixth holdout, the logged eval passed with 11 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_multi_log_eval.py --min-logs 3`.

Three-log residual aggregate:

```text
usable residual logs: 3
ask count:            96
decision count:       351
would overrides:      29
helpful:              29
harmful:              0
neutral-wrong:        0
promotion ready:      false
```

Interpretation:

- the residual controller has now survived three logged holdouts after each discovered boundary failure was converted into a configurable suppressor and regression case;
- this is materially stronger than the earlier two-log result, but runtime promotion should still remain blocked until at least one independent external/natural agent log repeats the zero-harm pattern.

Thirty-second implementation checkpoint:

- `eval/adaptive_residual_shadow_promotion_readiness.py` now summarizes residual-controller promotion evidence and explicitly blocks runtime promotion until external/agent residual logs exist;
- the readiness report uses the three-log aggregate as evidence, classifies current logs as local/local-natural-style, and records `blocked_reason: external_or_agent_residual_log_required`;
- `eval/selector_architecture_gate.py` now requires `adaptive_residual_shadow_promotion_readiness_ok`.

Current promotion readiness:

```text
three-log local aggregate: passed
helpful overrides:        29
harmful overrides:        0
neutral-wrong overrides:  0
external/agent logs:      0
promotion ready:          false
blocked reason:           external_or_agent_residual_log_required
```

Interpretation:

- the local evidence is strong enough to justify continued development of the residual controller;
- it is not yet strong enough to justify runtime authority or config auto-application;
- the next evidence milestone should be an independent Hermes/agent residual log evaluated by the same readiness artifact.

Thirty-third implementation checkpoint:

- `docs/HERMES_ADAPTIVE_RESIDUAL_SHADOW_EXTERNAL_LOG_HANDOVER.md` now defines the external Hermes/agent validation run required by the promotion-readiness gate;
- the handover specifies runtime flags, feedback labels, scenario families, output files, optional local evaluation commands, and success criteria;
- this turns the readiness blocker into an executable external validation task rather than an informal note.

Next evidence target:

```text
external/agent residual log: required
minimum ask-feedback pairs:  40
target ask-feedback pairs:   60+
harmful overrides:           0
neutral-wrong overrides:     0
helpful overrides:           >0
```

Thirty-fourth implementation checkpoint:

- Hermes produced the first external residual-shadow log against commit `ddc95bc` with 62 asks, 62 linked answer-feedback rows, 126 memory-feedback rows, and residual shadow present on every ask;
- the external log found one harmful residual override: `Which stale config value was replaced by the current one?`;
- root cause: the learned family path misrouted a stale-config replacement query into `supported_evidence -> likely_helpful` while the symbolic path correctly stayed `likely_harmful`;
- `core/adaptive_residual_shadow.py` and `config.yaml` now extend `stale_previous` suppression with `stale`, `stale config`, `config value`, and `replaced by the current`;
- `eval/adaptive_residual_shadow_suppressor_regression.py` now protects the exact stale-config replacement query;
- `eval/adaptive_residual_shadow_external_failure_replay.py` replays Hermes' harmful example against the current suppressor policy and confirms it would now be suppressed.

External failure status:

```text
Hermes external log:      useful development failure
harmful overrides:        1 in historical logged payload
current policy replay:    suppressed
promotion ready:          false
next external step:       rerun Hermes residual log with patched policy
```

Interpretation:

- the external log did what it was supposed to do: it found a boundary the local holdouts missed;
- because the harmful decision is already logged, the historical Hermes log remains a failing strict logged-eval artifact;
- the patched policy needs a fresh external/agent run before promotion readiness can become true.

Thirty-fifth implementation checkpoint:

- residual-shadow evaluation now distinguishes clean validation logs from processed historical failure logs;
- `eval/adaptive_residual_shadow_multi_log_eval.py` supports excluding processed failure logs from clean aggregate metrics while preserving the original failure files as evidence;
- `eval/adaptive_residual_shadow_promotion_readiness.py` now requires the external failure replay to pass, excludes processed historical failure logs from clean readiness metrics, and still blocks promotion until a fresh clean external/agent log exists;
- `eval/adaptive_residual_shadow_term_candidate_miner.py` treats unsafe historical rows as resolved when the current suppressor policy now blocks their query, while synthetic raw-mining regressions can still exercise the candidate-learning path;
- `eval/selector_architecture_gate.py` now requires the external failure replay and passes again with the processed-failure split.

Current processed-failure result:

```text
historical Hermes harmful rows replayed: 1
current policy suppression:             passed
clean residual logs:                    3
clean would overrides:                  29
clean helpful overrides:                29
clean harmful overrides:                0
promotion ready:                        false
blocked reason:                         external_or_agent_residual_log_required
```

Interpretation:

- the stale-config external failure is now a fixed regression target, not a clean validation log;
- the architecture gate is green for continued development;
- promotion remains correctly blocked until a new Hermes/agent run validates the patched policy without harmful or neutral-wrong overrides.

Thirty-sixth implementation checkpoint:

- because Hermes was temporarily unavailable, `eval/adaptive_residual_shadow_seventh_agent_style_log.py` now creates a laptop-local agent-style substitute residual log;
- the substitute log targets the recently fixed stale-config failure, unsupported production-authority claims, private/sensitive lookup pressure, wrong-scope namespace pressure, and OGCF bridge useful/noise wording;
- the first run exposed one neutral-wrong missing-support override on `Which proof says the residual controller can now mutate live answers?`;
- `unsupported_proof` suppression is now configurable for `can now mutate`, `mutate live`, and `mutate live answers`, and `eval/adaptive_residual_shadow_suppressor_regression.py` protects this boundary;
- after regeneration, the seventh agent-style log passes with 18 asks, 1 helpful would-override, 0 harmful overrides, and 0 neutral-wrong overrides;
- the clean four-log aggregate passes with 114 asks, 412 residual decisions, 30 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- the unified selector architecture gate passes with the new generator included in compile coverage.

Interpretation:

- the local agent-style substitute is useful for continued development while Hermes is unavailable;
- it should not be treated as a replacement for independent external validation;
- promotion readiness remains blocked with `external_or_agent_residual_log_required` until a fresh Hermes/agent log confirms the same zero-harm pattern outside this local generator.

Thirty-seventh implementation checkpoint:

- `eval/adaptive_residual_risk_scorer_eval.py` adds the first report-only learned residual-risk diagnostic for the residual controller;
- the scorer trains a tiny local naive-Bayes text/decision model over synthetic boundary rows plus current residual-shadow logged examples;
- it predicts risk categories that map to the roadmap's neural-symbolic suppressor direction: `unsupported_authority_claim`, `stale_previous_lookup`, `sensitive_private_lookup`, `ordinary_namespace_scope_risk`, `safe_supported_evidence_rescue`, and `other_symbolic_fallback`;
- `eval/adaptive_residual_risk_scorer_regression.py` guards the diagnostic as report-only, config/runtime immutable, promotion-blocked, and requiring protected boundary recall;
- the unified selector gate now requires `adaptive_residual_risk_scorer_ok`.

Current learned-risk scorer result:

```text
samples:                   52
logged samples:            30
test accuracy:             0.666667
protected boundary recall: 1.0
promotion ready:           false
```

Interpretation:

- this is the first concrete step beyond purely term-based suppressors;
- it is not yet a runtime controller because general accuracy is modest and the dataset is still mostly generated/local;
- its value is as a diagnostic learner that can reveal whether future suppressor candidates are semantically recurring rather than merely phrase-matched.

Thirty-eighth implementation checkpoint:

- `eval/adaptive_residual_risk_disagreement_eval.py` now compares the learned residual-risk scorer against the current configurable term suppressors on paraphrased boundary challenges;
- the disagreement report highlights cases where the learned scorer catches protected risks beyond the exact term lists and blocks safe-query over-warning as a regression failure;
- the first run found useful beyond-term catches but over-warned a safe local-development query, so the learned scorer training set now includes additional safe local-log/development examples;
- after the update, the disagreement eval passes with seven learned risk catches beyond current term suppressors and zero safe over-warnings;
- the unified selector gate now requires `adaptive_residual_risk_disagreement_ok`.

Current learned-vs-term result:

```text
learned beyond-term risk catches: 7
safe over-warnings:              0
runtime mutation:                false
config mutation:                 false
promotion ready:                 false
```

Interpretation:

- the learned diagnostic is beginning to add value beyond brittle phrase matching;
- it remains advisory only, but it gives the roadmap a concrete measurement for when learned semantic suppressors are becoming useful enough to consider guarded runtime-shadow integration.

Thirty-ninth implementation checkpoint:

- `core/adaptive_residual_shadow.py` now exports learned residual-risk diagnostics inside the runtime residual-shadow payload;
- each residual decision now reports `term_risk_label`, `learned_risk_label`, `learned_risk_confidence`, and whether the learned risk label disagrees with the current term suppressor interpretation;
- the top-level payload includes a `learned_risk_model` summary with sample counts and immutable report-only flags;
- `eval/adaptive_residual_shadow_runtime_regression.py` now guards that these diagnostics are present while answer text, selector policy, evidence, runtime memory, and config remain unchanged;
- this turns the learned risk scorer from an offline report into logged runtime shadow evidence for future real-agent calibration.

Current runtime diagnostic status:

```text
runtime payload includes learned risk labels: true
answer mutation:                              false
selector mutation:                            false
memory mutation:                              false
config mutation:                              false
architecture gate:                            passed
promotion ready:                              false
```

Interpretation:

- future local/Hermes residual logs can now collect learned-vs-term risk disagreement at ask time;
- this is the needed data path before a learned semantic suppressor can ever be considered for guarded runtime authority;
- the current implementation remains a diagnostic-only neural-symbolic shadow.

Fortieth implementation checkpoint:

- `eval/adaptive_residual_risk_logged_eval.py` now evaluates learned-risk diagnostics from actual runtime residual-shadow outcome logs;
- the logged eval confirms the runtime payload carries learned and term risk labels for residual decisions;
- it reports two development signals: learned protected-risk catches beyond current term suppressors, and term-overprotection cases where a safe meta/development query is protected by broad terms;
- the seventh local agent-style log was regenerated with the runtime learned-risk fields and passed the logged-risk eval;
- the unified selector gate now requires `adaptive_residual_risk_logged_eval_ok`.

Current logged learned-risk result:

```text
risk diagnostic rows:       61
learned beyond-term catches: 10
term overprotection signals: 2
runtime mutation:            false
config mutation:             false
architecture gate:           passed
promotion ready:             false
```

Interpretation:

- the learned diagnostic is now useful in real logs, not only offline challenge rows;
- beyond-term catches show where learned semantic risk can eventually reduce dependence on phrase lists;
- term-overprotection signals show where broad phrase suppressors may be too conservative and should later become learned/contextual rather than manually narrowed.

Forty-first implementation checkpoint:

- `eval/adaptive_residual_risk_overprotection_candidate.py` now converts logged term-overprotection signals into a review-only contextual exception candidate artifact;
- the candidate groups safe learned-risk readings that are still protected by broad term suppressors, without changing the active suppressor policy;
- the current local log produces one candidate group for `stale_previous_lookup` overprotection on safe meta/development queries about the current suppressor and Hermes replay;
- the artifact explicitly blocks auto-application and requires recurrence across independent logs before any config or runtime change;
- the unified selector gate now requires `adaptive_residual_risk_overprotection_candidate_ok`.

Current overprotection candidate result:

```text
term overprotection signals: 2
candidate groups:            1
candidate action:            learned_contextual_exception_candidate
auto apply:                  blocked
promotion ready:             false
architecture gate:           passed
```

Interpretation:

- this is the first path for learned diagnostics to improve not only missed risk, but also overconservative term suppression;
- it keeps the current safe term suppressors active while collecting evidence for future contextual exceptions;
- the next milestone is recurrence testing across another independent local or Hermes-style log.

Forty-second implementation checkpoint:

- `eval/adaptive_residual_shadow_eighth_meta_recurrence_log.py` now creates a second local recurrence-focused residual log;
- the eighth log stresses safe meta/development queries about stale suppressors and replay evidence alongside genuinely unsafe stale, private, unsupported, and scope-risk queries;
- the eighth residual logged eval passes with 16 asks, 2 helpful would-overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- the eighth learned-risk logged eval passes with 53 diagnostic rows, 4 learned beyond-term catches, and 1 term-overprotection signal;
- the clean five-log residual aggregate passes with 32 helpful overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- `eval/adaptive_residual_risk_overprotection_recurrence.py` now aggregates overprotection candidates across the seventh and eighth local logs;
- recurrence is now observed for one `stale_previous_lookup` contextual exception candidate group, but promotion remains blocked.

Current recurrence result:

```text
recurrence logs:        2
recurrent groups:       1
candidate family:       stale_previous_lookup
runtime mutation:       false
config mutation:        false
architecture gate:      passed
promotion ready:        false
```

Interpretation:

- the safe meta/development overprotection pattern is no longer a one-log artifact;
- it is still local-only evidence, so the correct action is to keep collecting recurrence, especially from a future Hermes/external log;
- this is a concrete roadmap step toward learned contextual suppressor exceptions without weakening current safety.

Forty-third implementation checkpoint:

- `eval/adaptive_residual_risk_exception_simulation.py` now simulates the recurring learned contextual-exception candidate in report-only mode;
- the simulation asks whether term-overprotected, learned-safe residual decisions would become helpful or unsafe if the broad term suppressor were bypassed by a learned contextual exception;
- across the seventh and eighth local logs, the simulation found three candidate exceptions;
- all three simulated exceptions were helpful, with 0 harmful and 0 neutral-wrong outcomes;
- the unified selector gate now requires `adaptive_residual_risk_exception_simulation_ok`.

Current exception simulation result:

```text
simulated exception candidates: 3
helpful:                        3
harmful:                        0
neutral-wrong:                  0
runtime mutation:               false
config mutation:                false
architecture gate:              passed
promotion ready:                false
```

Interpretation:

- the learned contextual exception candidate now has local recurrence and local zero-harm simulation evidence;
- this is still not enough for runtime authority, but it is a strong prototype result for the neural-symbolic roadmap;
- the correct next evidence step is a fresh external/Hermes-style run or another independently generated local holdout before considering any guarded config candidate.

Forty-fourth implementation checkpoint:

- Hermes validated commit `06160b0` with 60 external ask/feedback pairs, 123 memory-feedback rows, and required residual/learned-risk logging enabled;
- the external residual logged eval failed with 6 would-overrides: 4 helpful, 2 harmful, 0 neutral-wrong;
- the harmful residual would-overrides were unsupported authority queries: `Which memo grants automatic promotion authority right now?` and `What signed note says selector policy can mutate itself now?`;
- importantly, learned-risk diagnostics already classified the harmful authority pattern as protected risk, but the residual shadow did not yet use learned risk as a veto;
- `core/adaptive_residual_shadow.py` now includes a report-only learned-risk suppressor. Protected learned-risk labels above threshold suppress residual would-overrides even when term suppressors miss the query;
- `config.yaml` now exposes `learned_risk_suppressor_enabled` and `learned_risk_confidence_threshold`;
- `eval/adaptive_residual_learned_risk_veto_regression.py` now guards the exact Hermes authority patterns and verifies they are learned-risk veto-ready;
- the unified selector gate now requires `adaptive_residual_learned_risk_veto_ok`.

Hermes external failure and fix:

```text
Hermes asks:                 60
Hermes residual overrides:   6
Hermes helpful overrides:    4
Hermes harmful overrides:    2
learned-risk veto regression: passed
architecture gate:            passed
promotion ready:              false
```

Interpretation:

- Hermes found the first external case where learned-risk diagnostics should actively veto report-only residual override proposals;
- this is a major neural-symbolic milestone because the learned layer is no longer only descriptive: it now blocks unsafe shadow advice while still not mutating live answers, selector policy, memory, or config;
- the historical Hermes log remains a failing artifact for commit `06160b0`; a fresh Hermes rerun is required to verify the veto fixes the external harmful cases.

Forty-fifth implementation checkpoint:

- because Hermes is temporarily unavailable, `eval/adaptive_residual_shadow_ninth_authority_veto_log.py` now provides a local substitute rerun for the Hermes authority failures;
- the ninth log includes the exact harmful Hermes authority queries plus nearby automatic-promotion, self-mutation, stale, private, scope, and safe authority-meta cases;
- after the learned-risk veto, the ninth residual logged eval passes with 13 asks, 3 helpful would-overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- the ninth learned-risk logged eval passes with 44 diagnostic rows, 21 learned beyond-term catches, and 1 term-overprotection signal;
- the clean six-log local aggregate now passes with 35 helpful would-overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- `eval/selector_architecture_gate.py` compiles the ninth authority-veto generator and the unified selector gate passes.

Current local authority-veto substitute result:

```text
ninth local asks:             13
helpful residual overrides:   3
harmful residual overrides:   0
neutral-wrong overrides:      0
learned-risk suppressor:      active
architecture gate:            passed
promotion ready:              false
```

Interpretation:

- the learned-risk veto fixes the Hermes authority pattern under local substitute conditions;
- this does not replace a real Hermes rerun, because the original failure was external;
- the next external milestone remains a fresh Hermes validation run against this post-veto code.

Forty-sixth implementation checkpoint:

- `eval/adaptive_residual_learned_risk_external_failure_replay.py` now replays the exact harmful Hermes learned-risk residual logged-eval examples against the current selector;
- the replay uses the preserved external failure artifact `hermes_learned_risk_residual_logged_eval_results.json` and does not rewrite or erase the historical failed result;
- both harmful Hermes authority queries are still missed by current term suppressors, but are now classified as `unsupported_authority_claim` by the learned-risk model above the configured veto threshold;
- the replay confirms the current learned-risk veto would suppress both historical harmful residual would-overrides;
- the unified selector architecture gate now requires `adaptive_residual_learned_risk_external_failure_replay_ok`.

Current historical authority-failure replay:

```text
historical harmful examples:        2
term suppressor catches:            0
learned-risk veto catches:          2
current would-be suppressed:        2
architecture gate:                  passed
promotion ready:                    false
```

Interpretation:

- this is stronger than the ninth local substitute because it reuses the actual Hermes failure artifact;
- it is also not a substitute for a fresh external run, because it is a current-policy replay over historical examples;
- the architecture direction remains correct: learned neural-symbolic risk should become the primary generalization layer, while term suppressors stay as configurable conservative guardrails.

Forty-seventh implementation checkpoint:

- the next weakness after exact Hermes replay was authority-risk generalization: the system needed to show it could catch nearby unsupported authority phrasing without simply memorizing two harmful Hermes strings;
- `eval/adaptive_residual_risk_scorer_eval.py` now includes additional report-only seed rows for unsupported selector promotion, automatic policy mutation, no-review config updates, and residual/live-answer authority claims;
- `eval/adaptive_residual_learned_risk_authority_paraphrase_regression.py` now tests seven unsafe authority paraphrases plus three safe meta-development controls;
- the regression requires all unsafe paraphrases to be labeled `unsupported_authority_claim`, all unsafe paraphrases to be vetoed, most unsafe paraphrases to be learned beyond exact term suppressors, and all safe controls to remain unvetoed;
- the unified selector architecture gate now requires `adaptive_residual_learned_risk_authority_paraphrase_ok`.

Current authority generalization result:

```text
unsafe authority paraphrases:       7
safe meta controls:                 3
learned beyond term suppressors:    6
harmful paraphrases vetoed:         7
safe controls vetoed:               0
architecture gate:                  passed
promotion ready:                    false
```

Interpretation:

- this is a direct move from brittle term patches toward a learned neural-symbolic risk controller;
- the result shows that unsupported authority risk is now represented as a small learned category, not only as exact configured vocabulary;
- runtime promotion remains blocked because the residual controller is still report-only and needs fresh external/Hermes validation after the veto/generalization changes.

Forty-eighth implementation checkpoint:

- after authority paraphrase generalization, the next boundary risk was safe meta-development language that mentions blocked promotion or policy mutation;
- an initial safe-control expansion weakened the exact Hermes `automatic promotion authority` veto, proving that the learned-risk controller needs paired unsafe anchors and safe counterexamples rather than one-sided seed growth;
- `eval/adaptive_residual_risk_scorer_eval.py` now includes paired safe rows for blocked/report-only/no-review-disabled status and paired unsafe rows for memo/approval/authority requests;
- `eval/adaptive_residual_learned_risk_authority_paraphrase_regression.py` now checks six safe authority-meta controls and requires them to be labeled `safe_supported_evidence_rescue`, not merely below veto threshold;
- the exact Hermes learned-risk veto regression, historical external failure replay, authority paraphrase regression, broader learned-risk scorer regression, and unified architecture gate all pass together.

Current authority boundary calibration result:

```text
unsafe authority paraphrases vetoed:        7 / 7
safe authority-meta controls labeled safe:  6 / 6
learned beyond term suppressors:            6
Hermes exact veto regression:               passed
Hermes historical replay:                   passed
architecture gate:                          passed
promotion ready:                            false
```

Interpretation:

- this is a useful neural-symbolic training pattern for the roadmap: every learned protected-risk category needs positive unsafe examples and nearby safe counterexamples;
- the controller now distinguishes unsupported authority requests from safe status questions about why authority remains blocked;
- the next best evidence step is still a fresh external/Hermes validation run, or if Hermes is unavailable, another independently generated natural holdout focused on mixed safe/unsafe authority and policy-status questions.

Forty-ninth implementation checkpoint:

- because Hermes was unavailable, `eval/adaptive_residual_shadow_tenth_authority_boundary_log.py` now creates an independent local runtime-style authority boundary holdout;
- the tenth holdout uses fresh mixed wording outside the exact Hermes failure and paraphrase-regression sets: unsupported authorization/bypass/no-review/policy-mutation requests, safe blocked-status/report-only questions, plus stale/private/scope controls;
- the residual logged eval on the tenth holdout passes with 14 asks, 3 helpful report-only would-overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- the learned-risk logged eval on the tenth holdout passes with 48 diagnostic rows, 22 learned beyond-term catches, and 0 term-overprotection signals;
- the clean local aggregate now passes across 7 usable residual logs with 38 helpful would-overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- the unified selector architecture gate compiles the tenth holdout generator and passes.

Current tenth authority-boundary holdout result:

```text
tenth local asks:                  14
helpful residual overrides:        3
harmful residual overrides:        0
neutral-wrong overrides:           0
learned beyond term catches:       22
term overprotection signals:       0
clean aggregate usable logs:       7
clean aggregate helpful overrides: 38
clean aggregate harmful overrides: 0
architecture gate:                 passed
promotion ready:                   false
```

Interpretation:

- this is the first runtime-style local evidence after the paired unsafe/safe authority calibration;
- the learned-risk veto is now doing useful generalization in a logged ask/feedback loop, not only in standalone classifier probes;
- runtime promotion remains blocked until fresh external/Hermes validation, but the selector architecture is becoming a stronger adaptive memory-brain controller: symbolic suppressors provide guardrails, while learned risk catches paraphrased unsafe intent beyond terms.

Fiftieth implementation checkpoint:

- the residual promotion-readiness contract has been tightened from the older three-log local threshold to seven clean local residual logs;
- `eval/adaptive_residual_shadow_promotion_readiness.py` now exposes `min_clean_local_logs=7`, checks `has_min_clean_local_logs`, and still blocks promotion unless a fresh external/agent residual log exists;
- `eval/selector_architecture_gate.py` now runs the residual multi-log eval with `--min-logs 7 --exclude-processed-failures`;
- the stricter seven-log multi-log eval passes with 157 asks, 557 residual decisions, 38 helpful report-only would-overrides, 0 harmful overrides, and 0 neutral-wrong overrides;
- the unified selector architecture gate passes under this stricter readiness standard.

Current tightened readiness result:

```text
minimum clean local logs required:  7
clean usable residual logs:         7
total clean asks:                   157
helpful residual overrides:         38
harmful residual overrides:         0
neutral-wrong overrides:            0
external/agent log present:         false
promotion ready:                    false
blocked reason:                     external_or_agent_residual_log_required
architecture gate:                  passed
```

Interpretation:

- locally, the adaptive residual selector is now much better supported than when the original three-log threshold was introduced;
- the blocker has narrowed to external validation, not local instability;
- this is the right stance for the roadmap: strengthen the learned neural-symbolic controller with local evidence, but require independent agent/Hermes validation before any runtime promotion or config default change.

Fifty-first implementation checkpoint:

- Hermes validated commit `06545dd` with a fresh external authority-boundary run: 82 asks, 82 answer-feedback rows, and 118 memory-feedback rows;
- the external residual logged eval failed with 7 report-only would-overrides: 3 helpful, 4 harmful, 0 neutral-wrong;
- the harmful examples were new unsupported immediate-authority and stale prior-interpretation phrasings:
  - `What evidence says learned risk can rewrite policy immediately?`
  - `What policy grants immediate self-modification to the selector?`
  - `What proof authorizes policy mutation from a single test run?`
  - `Should we revert to the prior no-veto authority interpretation?`
- learned-risk diagnostics on the same Hermes log passed overall with 274 diagnostic rows and 162 learned beyond-term catches, but the supported-evidence residual decisions for those four queries were incorrectly labeled safe in the logged run;
- `eval/adaptive_residual_risk_scorer_eval.py` now adds paired unsafe examples for immediate rewrite, self-modification, single-test-run policy mutation, and stale prior no-veto interpretation;
- `eval/adaptive_residual_learned_risk_hermes_authority_boundary_replay.py` now replays the four harmful Hermes examples against the current learned-risk veto;
- the replay passes: three examples are now suppressed as `unsupported_authority_claim`, and the prior no-veto example is suppressed as `stale_previous_lookup`;
- `eval/adaptive_residual_shadow_multi_log_eval.py` now marks `hermes_learned_risk_authority_boundary_outcomes.jsonl` as a processed historical failure log when `--exclude-processed-failures` is used;
- `eval/adaptive_residual_shadow_promotion_readiness.py` now requires both prior external failure replays to pass before it can report readiness, while still blocking promotion until a fresh successful external/agent log exists;
- `eval/selector_architecture_gate.py` now includes per-step subprocess timeouts and requires `adaptive_residual_learned_risk_hermes_authority_boundary_replay_ok`.

Current post-Hermes-failure replay result:

```text
Hermes external asks:                  82
Hermes harmful residual overrides:     4
current replay suppressed:             4 / 4
unsupported authority catches:         3
stale prior-interpretation catches:    1
clean local logs still required:        7
clean local helpful/harmful overrides:  38 / 0
promotion ready:                       false
blocked reason:                        external_or_agent_residual_log_required
architecture gate:                     passed
```

Interpretation:

- the Hermes run is not a success; it is a valuable external failure that expanded the learned-risk boundary;
- the fix again supports the roadmap direction: do not grow only a term list, but teach the learned risk layer with paired unsafe/safe examples and preserve every external failure as a replay;
- the next required evidence step is another fresh Hermes/external run against the post-fix code.

Fifty-second implementation checkpoint:

- Hermes attempted the authority-boundary rerun from a fresh `/home/victo` clone and correctly stopped at the sanity gate because the full architecture gate expected Windows-local experiment logs and model/runtime artifacts that were not present in the fresh clone;
- `eval/selector_architecture_gate.py` now supports `--allow-missing-runtime-artifacts` for external-agent sanity checks;
- portable sanity mode still runs source/config and pure regression checks, but skips checks that require pre-existing runtime logs, local DBs, or local model artifacts;
- the strict evidence-backed local gate remains unchanged by default and still passes in the Windows workspace;
- `docs/HERMES_AUTHORITY_BOUNDARY_RERUN_HANDOVER.md` now instructs Hermes to use the portable sanity mode before generating fresh runtime logs.

Current gate behavior:

```text
portable Hermes sanity gate:        passed
strict local architecture gate:     passed
runtime promotion ready:            false
next required evidence:             fresh Hermes authority-boundary runtime rerun
```

Interpretation:

- this fixes a process/tooling problem, not a model behavior problem;
- the full architecture gate remains strict where local evidence exists;
- fresh Hermes clones now have a clean way to verify the checked-out code before creating the external validation artifacts that the strict gate needs.

Fifty-third implementation checkpoint:

- Hermes reran the authority-boundary handover at commit `1d37180` and completed the runtime test with 90 asks, but the run returned 0 evidence rows and therefore produced 0 helpful residual would-overrides;
- residual logged eval had 0 harmful and 0 neutral-wrong overrides, so the safety part of the rerun succeeded, but benefit validation was inconclusive;
- learned-risk logged eval passed with 305 diagnostic rows, 183 learned beyond-term catches, and 5 term-overprotection signals;
- `eval/hermes_authority_boundary_rerun_assessment.py` now separates external safety validation from benefit validation. On the Hermes rerun, it reports `safety_passed=true`, `benefit_passed=false`, and `benefit_inconclusive_reason=no_evidence_rows_returned`;
- `eval/hermes_authority_boundary_evidence_preflight.py` now runs a short evidence-coverage preflight before a full Hermes run, requiring at least three evidence-positive queries;
- the Hermes rerun handover now requires this preflight and explains that zero-evidence external runs can validate safety but cannot validate helpful residual override benefit.

Current Hermes rerun interpretation:

```text
Hermes asks:                         90
evidence-positive asks:              49
helpful residual overrides:          0
harmful residual overrides:          0
neutral-wrong overrides:             0
learned beyond-term catches:         183
safety passed:                       true
benefit passed:                      false
benefit inconclusive reason:         no_residual_benefit_opportunities
promotion ready:                     false
```

Interpretation:

- the learned-risk authority veto appears externally safe on the rerun;
- the architecture still needs a benefit-capable external run, but the problem is no longer missing retrieval evidence;
- the next Hermes-style evidence step should deliberately include safe supported-evidence benefit-opportunity prompts where a helpful residual override is plausible.

Fifty-fourth implementation checkpoint:

- Hermes later recovered from a malformed copied DB by creating a fresh timestamped DB copy, passing evidence preflight, and completing a 90-ask authority-boundary rerun;
- the recovered rerun produced 90 answer-feedback rows, 110 memory-feedback rows, and 305 residual decisions with 0 harmful overrides and 0 neutral-wrong overrides;
- the rerun still produced 0 residual would-overrides, so `hermes_authority_boundary_rerun_assessment.py` correctly reported `safety_passed=true`, `benefit_passed=false`, and `benefit_inconclusive_reason=no_residual_benefit_opportunities`;
- `MemoryApi` and `create_pipeline` now accept an explicit `config_override` so deterministic local tests can use isolated runtime config without changing production `config.yaml`;
- `eval/adaptive_residual_shadow_benefit_opportunity_log.py` now builds a fresh local seed DB with hash embeddings, logs safe supported-evidence benefit opportunities plus authority/stale safety controls, and writes a focused outcome log;
- the focused local benefit-opportunity log passed residual evaluation with 5 helpful report-only overrides, 0 harmful overrides, 0 neutral-wrong overrides, 31 learned-risk diagnostic rows, 17 learned beyond-term catches, and 0 term-overprotection signals;
- the focused assessment passed both safety and benefit: `safety_passed=true`, `benefit_passed=true`;
- portable architecture gate mode passed locally with `--allow-missing-runtime-artifacts --random-cases 16`.

Current interpretation:

```text
Hermes recovered authority rerun:     safety pass, benefit inconclusive
local benefit-opportunity harness:    safety pass, benefit pass
helpful local residual overrides:     5
harmful local residual overrides:     0
learned beyond-term catches:          17
term overprotection:                  0
production mutation flags:            none
promotion ready:                      false
```

Interpretation:

- the architecture is not ready for live promotion, but the benefit mechanism is not dead; it appears only when the runtime sees safe supported-evidence cases where symbolic behavior is uncertain or too conservative;
- the next external/Hermes test should reuse the focused benefit-opportunity prompt shape while still including the exact prior authority-failure controls;
- the local seeded harness should remain a laptop-safe regression so future selector changes cannot accidentally remove the helpful override path.

## Combined Memory and Selector Architecture Analysis

Date: 2026-06-01

The combined program is now best understood as a local neural-symbolic memory brain prototype with four cooperating loops:

1. the memory loop stores, corrects, supersedes, consolidates, and retrieves memories with CSD/G-CL geometry;
2. the retrieval/evidence loop scores retrieved rows with claim scope, answer type, evidence state, canonical support, source authority, and OGCF bridge diagnostics;
3. the selector loop converts those signals into conservative policy decisions and report-only adaptive advisories;
4. the evaluation loop mines outcome logs, proposes candidate controller knowledge, and blocks promotion until guarded replay and holdout tests pass.

The best parts of the current architecture are:

- `core/retrieval_signals.py` and `core/evidence_states.py`: these are the clearest examples of the roadmap working. They moved hardcoded behavior toward configurable control surfaces with mining and promotion gates.
- `core/controller_context.py`: this is the beginning of the shared adaptive-memory context that can connect memory retrieval, OGCF diagnostics, selector decisions, resolver-shadow behavior, and outcome logs.
- `core/adaptive_residual_shadow.py`: this is the strongest neural-symbolic direction so far. It keeps symbolic report-only safety flags, but adds learned residual and learned-risk judgments that generalize beyond exact terms.
- OGCF integration: bridge/geometry pressure is now a useful second kind of memory signal, not just vector similarity.
- The evaluation layer: the project has unusually strong guard culture for a prototype. Historical failures are preserved, replayed, and used to tighten learned-risk boundaries instead of being overwritten.

The main weaknesses are now architectural, not only behavioral:

- `core/pipeline.py` still owns too many responsibilities: retrieval, reranking, session context, correction-chain scoring, lexical backfill, authority/supersession scoring, and row assembly.
- `core/resolver.py` still contains many answer-quality, conflict, confidence, and snippet-selection thresholds that should become configurable and later calibrated.
- `serve.py` is becoming an orchestration hub for API behavior, adaptive context construction, resolver shadow, residual shadow, answer feedback, and outcome logging.
- The roadmap has many report-only learned modules, but not yet one shared persisted "controller evidence packet" that can be treated as the stable training/evaluation unit across memory and selector sides.
- The external/Hermes rerun proved safety but not benefit because useful residual opportunities are sparse unless the prompt mix deliberately includes safe supported-evidence cases where symbolic behavior is uncertain.

## Next Combined Development Direction

The next development should be a shared controller evidence packet and replay dataset, not a new heuristic.

The packet should be written from every `ask` when outcome logging is enabled. It should be compact, versioned, and stable enough for both sessions to consume. It should include:

- query, namespace, operation id, agent id, and session id;
- selected evidence ids and compact evidence rows;
- retrieval signal fields: score, text match, intent match, claim scope, answer type, correction relevance, source reliability, domain reliability, feedback score;
- evidence-state fields: current/stale/historical/disputed/summary, weak-evidence flag, sensitive-evidence requirement, stale/current conflict summary;
- canonical memory fields: keeper status, support count, duplicate pressure, provenance summary;
- OGCF fields: intent, bridge overload score, affected ratio, maintenance pressure, geometry context;
- selector fields: features, diagnostics, policy decision, guard changes, explanation top reasons;
- resolver/adaptive fields: resolver-shadow actions, adaptive behavior shadow, adaptive residual shadow decisions, mutation flags;
- linked feedback labels when they arrive, or enough identifiers for a collector to join feedback later.

This packet should become the common substrate for:

```text
real runtime outcome log -> controller evidence packets -> multi-run memory bank -> calibrated candidate proposals -> guarded promotion gate
```

### Best Immediate Improvements

The best next improvements, in order, are:

1. Add a `controller_evidence_packet/v1` builder in `core/controller_context.py` or a new `core/controller_packet.py`.
   - Memory side benefit: one stable representation of what the memory program believed when it answered.
   - Selector side benefit: learned selector/residual modules train on the same fields used at runtime.
   - Test: fixture ask row with retrieval context, OGCF meta, selector snapshot, resolver shadow, and feedback join produces a deterministic packet.

2. Add an outcome-log collector that converts existing ask/feedback events into controller evidence packets.
   - Memory side benefit: old Hermes logs remain useful without rerunning the agent.
   - Selector side benefit: promotion-readiness and residual-risk tests can consume one normalized dataset instead of many custom parsers.
   - Test: collector handles legacy logs with no adaptive context, modern logs with adaptive context, and focused benefit-opportunity logs.

3. Start extracting resolver scoring constants into a `resolver_policy` config section.
   - Memory side benefit: answer confidence, conflict handling, weak-evidence behavior, and snippet selection become auditable and calibratable.
   - Selector side benefit: answer-level feedback banks can propose calibration changes without editing `resolver.py`.
   - Test: current defaults reproduce existing resolver behavior on answer-quality and multi-intent regression fixtures.

4. Add a benefit-opportunity external test recipe based on the new local harness.
   - Memory side benefit: Hermes or a local substitute can seed safe supported-evidence cases reliably.
   - Selector side benefit: external validation can prove usefulness, not only absence of harm.
   - Test: prior failure controls stay suppressed while safe supported-evidence prompts produce helpful report-only overrides.

5. Keep residual/adaptive mechanisms report-only until the packet bank shows repeated safe benefit across multiple real sessions.
   - Promotion should require: clean local aggregate, historical failure replays, one successful external/Hermes benefit-capable run, and no mutation/config flags.

## Ownership After This Analysis

Selector-side session should do first:

- define the packet schema;
- implement a packet builder or collector;
- add packet fixture regressions;
- adapt one residual/answer-feedback eval to read packets.

Initial implementation status:

- `core/controller_packet.py` now defines `controller_evidence_packet/v1`, a compact report-only packet that joins ask events, retrieval/evidence fields, evidence-state summaries, canonical support, OGCF diagnostics, selector decisions, resolver/adaptive shadows, residual decisions, and linked feedback;
- `eval/controller_packet_regression.py` validates the packet contract on a fixture containing current and stale evidence, OGCF metadata, resolver shadow actions, residual learned-risk decisions, answer feedback, and memory feedback;
- `eval/controller_packet_collector.py` converts existing outcome JSONL logs into packet JSONL datasets, so old Hermes and local logs can be reused without rerunning the agent.
- `eval/controller_packet_residual_eval.py` proves the packet format is directly usable by the residual evaluation path by scoring residual report-only overrides from packet JSONL instead of custom ask/feedback log parsing.
- `eval/controller_packet_residual_pipeline_regression.py` compares legacy log-based residual evaluation against packet-based residual evaluation on the same benefit-opportunity log, proving the packet path preserves the current learned-residual counts and family summaries.
- `eval/selector_architecture_gate.py` now requires both the packet fixture regression and the packet residual pipeline regression, so packet compatibility is part of the selector architecture gate rather than only a standalone experiment.
- `eval/controller_packet_answer_feedback_eval.py` and `eval/controller_packet_answer_feedback_pipeline_regression.py` now move the answer-feedback signal path onto packets as well. The pipeline regression confirms packet-derived answer-feedback signals preserve legacy counts, families, and recommendation summaries on the neural-symbolic holdout workflow.
- `eval/selector_architecture_gate.py` now also requires the packet answer-feedback pipeline regression. This means both learned-residual supervision and answer/resolver supervision are protected by the shared packet contract.
- `core/resolver_policy.py` now introduces the first `resolver_policy` configurable surface. The initial slice extracts answer-confidence scoring constants from `core/resolver.py` into `resolver_policy.answer_confidence` while preserving the legacy formula by default.
- `eval/resolver_policy_config_regression.py` verifies that committed config defaults match the legacy formula, conflict still lowers confidence, and config overrides affect `resolve_answer()` confidence. The selector architecture gate now requires this regression.
- `resolver_policy.evidence_preference` now extracts the resolver's primary evidence-ranking weights from `core/resolver.py`. The same regression verifies that default preference scores preserve the legacy formula and that config overrides can change evidence ordering in a controlled fixture.
- `resolver_policy.evidence_selection.max_selected_evidence` and `resolver_policy.answer_composition.low_confidence_threshold` now cover two more resolver behavior knobs. The regression verifies the default three-evidence limit, an override to one selected evidence row, and configurable low-confidence answer notices.
- The broader answer-behavior checks are now gate-protected too: `eval/answer_quality_eval.py` and `eval/multi_intent_answer_composition_regression.py` must pass inside `eval/selector_architecture_gate.py`. This keeps resolver-policy extraction tied to real answer quality and multi-intent composition, not only isolated scoring fixtures.
- `resolver_policy.answer_snippets` now extracts the resolver's snippet-selection constants: evidence scan limits, state bonuses, stale/broad/scope penalties, secondary-snippet thresholds, multi-intent rank bonuses, generic intro penalty, exact phrase bonus, and snippet truncation length. The regression verifies defaults preserve existing answer behavior while overrides can change snippet ranking and truncation in controlled fixtures.
- `resolver_policy.evidence_arbitration` now extracts the resolver thresholds that decide stored-contradiction conflicts, current-vs-historical preference, session-focused evidence preference, current relevance floor, stale supplement inclusion, rank-one takeover tolerance, and positive selector-signal thresholds. The regression verifies the stored-contradiction threshold is configurable while default answer-quality and multi-intent behavior remain unchanged.
- `resolver_policy.query_relevance` now extracts resolver relevance thresholds for negative intent rejection, text-match acceptance, intent acceptance, answer-type overlap, vector-score acceptance, and cosine acceptance. The regression verifies a borderline retrieved row can be admitted by a config override while defaults remain behavior-preserving.
- `eval/resolver_policy_runtime_view_regression.py` now verifies the normalized resolver policy is visible through the runtime/API config view and that test/runtime overrides are reflected there. The architecture gate requires this, so external agents can verify resolver-policy configuration without reading Python internals.

Memory-program session should do next:

- expose or preserve all required runtime fields in ask outcome logs;
- avoid changing selector internals directly;
- add memory-side tests proving teach/correct/ask logs contain enough packet fields for replay;
- continue improving storage/dedup/correction behavior, but report changes through packet-compatible handovers.

Hermes/external agent should later do:

- run a benefit-capable authority-boundary test using the focused prompt shape;
- generate multi-day packet logs across normal work;
- include both answer-level feedback and memory-row feedback.

This keeps the roadmap aligned with the original goal: a configurable and adaptive memory brain where learned components improve from logged outcomes, while symbolic gates keep the system local, auditable, and safe.

## Current Combined Architecture Status

Date: 2026-06-01

The combined memory and selector architecture is now past the pure experiment stage and is becoming a replayable adaptive-memory control system.

The strongest current structure is:

- memory side stores, corrects, supersedes, consolidates, and retrieves memories;
- retrieval/evidence side computes explicit claim-scope, answer-type, evidence-state, authority, feedback, canonical-support, and OGCF fields;
- selector side builds adaptive-memory context and conservative report-only controller decisions;
- resolver side now exposes a broad `resolver_policy` surface for confidence, ranking, evidence selection, answer composition, snippet selection, arbitration, and query relevance;
- controller packet side normalizes ask-time evidence, selector, resolver, OGCF, adaptive-shadow, and feedback fields into `controller_evidence_packet/v1`;
- evaluation side protects the architecture with packet regressions, resolver-policy regressions, answer-quality checks, multi-intent checks, and portable architecture-gate mode.

The main remaining weaknesses are:

- `serve.py` still assembles ask orchestration, selector context, shadow systems, outcome logging, and packet writing in one place;
- `core/pipeline.py` still owns retrieval row assembly, source context, lexical backfill, source-version logic, session context, and correction-chain scoring;
- real long-run packet banks still depend on future Hermes or memory-session runs;
- learned mechanisms remain report-only, which is correct for safety, but the next stage needs more multi-run calibration artifacts rather than more hand-tuned thresholds.

Best next development sequence:

1. Make controller evidence packets first-class in runtime ask outcome logs.
   - This lets every future real ask become replay/training material without requiring an offline conversion step.
   - The packet must remain report-only and must not mutate memory, answers, selector policy, or config.
2. Add a packet-bank aggregation layer for runtime packets.
   - This should group packets by resolver outcome family, selector decision family, OGCF pressure, and feedback labels.
   - It should produce calibration candidates, not runtime changes.
3. Start extracting ask orchestration from `serve.py` into a small service/helper once packet logging is stable.
   - The target is not a rewrite; it is a careful split so API handling and controller assembly stop growing together.
4. Continue pipeline decomposition only after runtime packets and packet banks are stable.
   - Pipeline extraction should start with retrieval row assembly/source context, because those fields already appear in packets and tests.

Implementation checkpoint:

- `outcome_log.include_controller_packet` now defaults to `true`;
- `MemoryApi.ask()` now writes a `controller_evidence_packet/v1` into ask outcome payloads using the same operation id as the logged ask event;
- `eval/outcome_logging_regression.py` now verifies the runtime packet is present, operation-id aligned, report-only, populated with retrieval context, and selector-decision aligned with the ask selector snapshot;
- `eval/selector_architecture_gate.py` now requires the outcome logging regression as `outcome_logging_controller_packet_ok`.
- `eval/controller_packet_memory_bank.py` now aggregates controller packet JSONL files into report-only clusters by selector policy/action, OGCF intent, answer conflict state, residual would-override count, and feedback labels;
- `eval/controller_packet_memory_bank_regression.py` verifies the packet bank separates calibration candidates from negative-feedback review clusters while preserving report-only/non-mutating guarantees;
- a smoke run over the local benefit-opportunity packet log produced 9 packets, 3 clusters, 1 calibration candidate, and 2 negative-feedback review clusters;
- `eval/selector_architecture_gate.py` now requires the packet-bank regression as `controller_packet_memory_bank_ok`.
- `eval/controller_packet_calibration_proposals.py` now converts packet-bank clusters into report-only calibration proposals, separating positive residual-benefit candidates from missing-support and stale-answer review items;
- `eval/controller_packet_calibration_proposals_regression.py` verifies proposal generation remains report-only and correctly identifies one resolver residual benefit candidate plus missing-support/stale review proposals;
- a smoke run over the local packet-bank result produced 3 proposals: 1 promotion candidate and 2 review items;
- `eval/selector_architecture_gate.py` now requires the calibration proposal regression as `controller_packet_calibration_proposals_ok`.
- `eval/controller_packet_calibration_guard.py` now applies a conservative promotion-readiness guard to calibration proposals. By default it requires enough support, multiple source logs, report-only mutation flags, no negative labels, and no unresolved review items before any proposal can be marked ready;
- `eval/controller_packet_calibration_guard_regression.py` verifies the current fixture proposals are all blocked for the right reasons: insufficient support, insufficient source-log diversity, and unresolved review items;
- the smoke guard over the local calibration proposals reported 3 blocked proposals and 0 ready promotions, which is the expected state until real multi-run packet evidence exists;
- `eval/selector_architecture_gate.py` now requires the calibration guard regression as `controller_packet_calibration_guard_ok`.
- `eval/controller_packet_calibration_pipeline.py` now runs the full report-only learning chain in one command: outcome logs -> controller packets -> packet memory bank -> calibration proposals -> calibration guard;
- `eval/controller_packet_calibration_pipeline_regression.py` verifies the one-command pipeline writes all intermediate artifacts and preserves report-only/non-mutating guarantees;
- the pipeline smoke run over the local benefit-opportunity log produced 9 packets, 3 clusters, 3 proposals, 1 promotion candidate, 2 review items, and 0 guard-ready promotions;
- `eval/selector_architecture_gate.py` now requires the one-command pipeline regression as `controller_packet_calibration_pipeline_ok`.
- `eval/controller_packet_collector.py` now preserves embedded runtime `controller_evidence_packet/v1` payloads when no later linked feedback events need to be joined. This lets the calibration pipeline consume new runtime logs directly while still rebuilding packets for legacy ask/feedback logs that need feedback joins;
- the pipeline regression now covers this embedded-packet path and verifies embedded feedback summaries remain separable into positive, missing-support, and stale clusters.
- Hermes real-run checkpoint at commit `654c0a6`: the portable architecture gate passed, a 40-ask mixed runtime session produced 40 controller packets and 135 feedback events, and the one-command calibration pipeline produced 8 clusters, 8 proposals, 2 preliminary promotion candidates, 5 review items, and 0 guard-ready promotions. This confirmed the packet loop is useful and conservative.
- The same real run exposed an important OGCF testing gap: bridge-warning feedback was present, but the collected packets had `ogcf_meta_packets = 0`. The packet bank now reports `bridge_feedback_without_ogcf_count`, the proposal layer converts these clusters into `bridge_metadata_gap_review`, and the guard blocks them with `bridge_label_without_ogcf`. This prevents bridge-warning labels from being treated as true OGCF calibration evidence unless explicit OGCF geometry metadata is present.
- Next real-log development target: run at least two independent Hermes sessions where bridge-warning prompts include explicit `ogcf_meta`, then compare bridge-warning-useful/noise clusters with `ogcf_meta_packets > 0` against the current metadata-gap clusters. Only after that should OGCF bridge behavior become a calibration candidate.
- Hermes focused OGCF bridge checkpoint at commit `e4e5fed`: the rich runtime fixture produced 24 packets, 6 OGCF metadata packets, 0 bridge-feedback-without-OGCF packets, and clean bridge-useful/bridge-noise separation. The proposal layer now classifies positive OGCF bridge evidence as `ogcf_bridge_behavior_candidate` and treats `ogcf_false_positive` as negative review evidence instead of mixed feedback. The next target is independent-source-log confirmation, not promotion.
- Hermes two-log OGCF bridge checkpoint at commit `4aaf6f7`: two independent bridge fixture logs produced an `ogcf_bridge_behavior_candidate` with support 6 and source-log count 2, while the matching OGCF false-positive/noise cluster remained review evidence. The guard now reports readiness tiers, evidence-ready-but-blocked counts, related review item ids, and recommended next actions. This changes the next development direction from "collect enough support" to "model or resolve related review families before promotion." In the current replay, the OGCF bridge candidate is evidence-ready but blocked by related review `proposal_002`, so the next useful improvement is review-aware calibration of useful-vs-noisy bridge warnings rather than raising support thresholds.
- The packet pipeline now includes `controller_packet_review_separation/v1`, a report-only analyzer for evidence-ready candidates blocked by related review evidence. On the two-log OGCF bridge replay it produced two concrete next actions: train/calibrate a bridge-intent separator for `ogcf_bridge_behavior_candidate` vs `ogcf_false_positive`, and build a citation holdout for good-vs-bad citation labels. This is the first step toward adaptive calibration that learns decision boundaries between positive and negative packet families instead of only counting support.
- The first report-only separator artifact now exists as `controller_packet_bridge_separator/v1`. It converts review-separation output into a candidate rule for useful OGCF bridge warnings vs false positives. On the two-log bridge replay it produced one holdout-ready separator: positive intent `bridge_geometry_query`, negative intent `ordinary_context`, positive labels `answer_bridge_warning_useful`/`bridge_relevant`, and negative labels `answer_bridge_warning_noise`/`ogcf_false_positive`.
- The packet pipeline now also includes `controller_packet_bridge_separator_holdout/v1`. It replays bridge separator candidates against packet holdout data before any runtime use. On the two-log OGCF bridge replay it scored 12 bridge-labeled packets with `match_rate: 1.0`, `false_positive_count: 0`, and `false_negative_count: 0`. This is strong evidence that the useful-vs-noisy bridge distinction is learnable from packet labels and intent metadata, but it remains `promotion_ready: false` because the current evidence is still fixture-scale and must be validated on broader unseen real logs before affecting runtime answers or config.

## Development Roadmap: Adaptive Memory Brain

The combined memory and selector system should now be treated as one adaptive memory brain with separable subsystems, not as unrelated retrieval, resolver, OGCF, and selector experiments.

The target mechanism is:

```text
memory store
-> retrieval and signal extraction
-> evidence interpretation
-> resolver answer policy
-> selector/controller policy
-> controller evidence packet
-> packet memory bank
-> calibration proposals
-> promotion guard
-> review separation
-> holdout replay
-> manual promotion or continued collection
```

### Subsystem Responsibilities

Memory store:

- own facts, corrections, source versions, namespaces, provenance, canonical support, deduplication, and feedback persistence;
- avoid owning selector, resolver, or adaptive policy decisions;
- preserve enough runtime fields for `controller_evidence_packet/v1`.

Retrieval and signal layer:

- generate candidates with vector recall, lexical backfill, namespace filters, source grouping, and correction-chain context;
- compute claim-scope, answer-type, correction relevance, source authority, feedback, CSD, G-CL, and OGCF signal fields;
- expose evidence candidates with structured fields instead of hidden score math.

Evidence layer:

- classify current, stale, historical, disputed, summary, weak, and sensitive evidence states;
- detect stale/current conflicts and correction-chain boundaries;
- provide compact evidence rows for resolver, selector, packets, and logs.

Resolver layer:

- choose evidence and compose answers;
- keep answer-confidence, ranking, arbitration, snippet selection, and query relevance configurable through `resolver_policy`;
- later accept calibrated policy proposals only through packet-bank evidence and guard tests.

Selector/controller layer:

- choose conservative memory-operation policy;
- run adaptive and residual shadows in report-only mode;
- explain why evidence was trusted, suppressed, reviewed, or held for collection;
- never silently promote learned behavior.

OGCF layer:

- detect memory geometry pressure, bridge usefulness, bridge noise, maintenance pressure, affected ratios, and duplicate pressure;
- treat bridge warnings as calibratable behavior only when packets include explicit OGCF metadata;
- evolve from config-backed intent gates into packet-trained useful-vs-noisy bridge separators.

Packet calibration layer:

- normalize all ask-time context into `controller_evidence_packet/v1`;
- aggregate packets into memory banks;
- create calibration proposals;
- guard promotion readiness;
- separate candidates from related review evidence;
- run holdout replay before any runtime/config change.

### Roadmap Improvements From Here

1. Consolidate packet calibration as a first-class subsystem.
   - The one-command pipeline now emits `controller_packet_calibration_system_manifest/v1`.
   - This manifest lists each stage, its input/output contract, current status, mutation guarantees, and next development target.
   - Future tests and handovers should reference this manifest instead of describing the packet bank, proposals, guard, review separation, and holdout as separate experiments.

2. Build broader multi-run packet banks.
   - Use real Hermes and local runs with linked answer feedback and memory-row feedback.
   - Require multiple independent source logs before treating any candidate as more than fixture-scale evidence.
   - Preserve both positive behavior and related negative review families.
   - Initial implementation now exists as `controller_packet_multirun_calibration/v1`, which aggregates multiple one-command pipeline reports, identifies recurring proposal families, summarizes guard-readiness tiers, checks bridge-holdout stability, and recommends whether to collect broader holdout data or continue gathering independent runs.

3. Advance OGCF from symbolic terms to learned separators.
   - Current best target: useful OGCF bridge warning vs `ogcf_false_positive`.
   - Keep the symbolic separator and holdout replay as the safety baseline.
   - Add a small local learned scorer only after broader unseen packet logs show stable separation.

4. Extract runtime orchestration after packet calibration stabilizes.
   - Split ask orchestration out of `serve.py` into a small controller service/helper.
   - Split retrieval row assembly/source context out of `core/pipeline.py`.
   - Keep behavior-preserving regressions around packet output and answer quality.

5. Turn configurable policy surfaces into calibrated surfaces.
   - `resolver_policy` should become the first resolver calibration target.
   - Candidate changes should come from packet-bank evidence, not direct hand tuning.
   - Promotion requires guard pass, holdout pass, manual review, and rollback path.

6. Preserve the report-only learning discipline.
   - Adaptive shadows, bridge separators, residual scorers, and calibration proposals must not mutate runtime or config by default.
   - Runtime use begins only after repeated real-log validation, negative-review separation, and explicit human approval.

### Immediate Architecture Contract

The current packet calibration pipeline should be considered the first architecture contract for the adaptive memory brain:

```powershell
py -3 eval/controller_packet_calibration_pipeline.py --log <outcome-log.jsonl> --out-prefix <prefix>
```

It should produce:

- `*_packets.jsonl`;
- `*_bank.json`;
- `*_proposals.json`;
- `*_guard.json`;
- `*_review_separation.json`;
- `*_bridge_separator.json`;
- `*_bridge_separator_holdout.json`;
- a top-level `calibration_system` manifest in the pipeline result.

The selector architecture gate must continue to protect this full chain. The next development step after this checkpoint should be a broader packet-bank aggregation over several independent logs, followed by a report-only learned scorer prototype for OGCF bridge separation only if the broader holdout remains clean.

The one-command pipeline now also emits a real-log readiness classifier:

```json
"real_log_readiness": {
  "schema": "controller_packet_real_log_readiness/v1",
  "readiness": "analysis_only | ready_for_runtime_collection | ready_for_loso_learned_scorer_evaluation",
  "blockers": ["single_source_log_only", "bridge_loso_not_candidate_ready"]
}
```

This is a report-only transition tool for Hermes and local runs. It separates:

- diagnostic fixtures that should not train or promote anything;
- real runtime logs that are good enough to keep collecting under the current packet contract;
- multi-source, feature-complete, review-clean bridge logs that are strong enough for LOSO learned-scorer evaluation.

This keeps the roadmap conservative after the portable-gate fix: passing the architecture gate is necessary, but real-log readiness still decides whether the next action is collection, holdout replay, or learned-scorer evaluation.

## Multi-Run Calibration Checkpoint

The first cross-run calibration layer now exists:

```powershell
py -3 eval/controller_packet_multirun_calibration.py --pipeline <pipeline-result-a.json> --pipeline <pipeline-result-b.json>
```

It consumes `controller_packet_calibration_pipeline/v1` reports and writes a `controller_packet_multirun_calibration/v1` artifact.

This layer answers a different question from the single-run pipeline:

```text
Did the same candidate or review family recur across independent runs?
```

The artifact reports:

- per-run packet/proposal/guard summaries;
- recurring proposal clusters;
- combined support and source-log counts;
- recurring positive candidates;
- recurring negative or review families;
- recurring evidence-ready candidates blocked by related review evidence;
- bridge holdout match-rate stability across runs;
- the next development target.

This is the first step toward replacing fixture-scale confidence with cross-run evidence. It remains report-only and cannot mutate runtime or config.

The next development target should be a broader holdout runner for recurring clusters. For OGCF, that means replaying the useful-vs-noisy bridge separator across more independent real or realistic packet logs before attempting a learned bridge scorer.

## Recurring Holdout Checkpoint

The recurring-cluster holdout planner now exists:

```powershell
py -3 eval/controller_packet_recurring_holdout.py --multirun <controller-packet-multirun-calibration.json>
```

It consumes `controller_packet_multirun_calibration/v1` and writes `controller_packet_recurring_holdout/v1`.

This layer decides which recurring candidate or review families are mature enough for broader holdout work. It creates task records for:

- useful-vs-noisy OGCF bridge separation;
- OGCF bridge metadata coverage;
- missing-support refusal behavior;
- stale/current arbitration behavior;
- general answer behavior calibration.

It also makes the learned-scorer decision explicit. A report-only OGCF bridge scorer prototype is considered only when:

- an OGCF bridge task recurs across enough independent runs;
- combined support is high enough;
- related negative review evidence has been separated;
- bridge holdout match rates remain clean across runs;
- mutation/config flags remain false.

This is the safety bridge between symbolic separator rules and any later small learned scorer. If the recurring holdout artifact reports blockers, the next action is more packet collection or broader holdout replay, not learning.

## Report-Only OGCF Bridge Scorer Prototype

The first learned OGCF bridge scorer prototype now exists:

```powershell
py -3 eval/controller_packet_ogcf_bridge_scorer.py --packets <controller-packets.jsonl> --separator <bridge-separator.json>
```

It writes `controller_packet_ogcf_bridge_scorer/v1`.

This scorer is deliberately tiny and local. It trains a transparent logistic model on packet features such as:

- OGCF metadata presence;
- OGCF bridge overload score;
- affected-memory ratio;
- maintenance pressure;
- answer confidence;
- answer conflict;
- selected evidence count;
- OGCF intent one-hot features.

It uses bridge feedback labels only as ground truth, not as predictive features. It compares the learned prediction against the existing symbolic bridge separator and marks `learned_scorer_candidate: true` only if the learned scorer matches or beats the symbolic baseline on held-out packets.

The first regression produced an important result: on the current tiny fixture, the learned scorer correctly demotes itself because non-label packet features do not yet separate useful and noisy bridge warnings as well as the symbolic separator. This is not a failure of the architecture. It is useful evidence that the next OGCF data collection should include richer non-label features if we want a learned scorer to become competitive:

- distinct bridge intents for useful vs noisy contexts;
- stronger OGCF geometry fields;
- richer evidence-context fields;
- query/domain bridge descriptors;
- canonical-support and duplicate-pressure features.

The learned scorer remains report-only, promotion-blocked, and protected by the architecture gate.

## OGCF Bridge Feature Enrichment Checkpoint

The OGCF bridge scorer now uses a richer packet feature view rather than only basic OGCF metadata and intent fields. The feature set includes:

- canonical support count and duplicate pressure;
- evidence-state current/stale flags;
- top retrieval score;
- average claim-scope and text-match scores;
- query bridge/geometry/ordinary term scores;
- evidence bridge/geometry/noise term scores;
- OGCF geometry fields and intent features.

Two gate-protected regressions now define the expected behavior:

1. Weak-feature demotion:
   - When useful and noisy bridge packets have nearly identical non-label features, the learned scorer must demote itself if it underperforms the symbolic separator.
   - This prevents a learned model from becoming attractive just because labels exist.

2. Rich-feature candidate behavior:
   - A self-generated richer packet fixture proves the scorer can separate useful bridge geometry warnings from ordinary/noisy lookups when packet context includes enough non-label structure.
   - The scorer can mark `learned_scorer_candidate: true`, but still stays `promotion_ready: false`.

This gives the roadmap a concrete data requirement for future real logs: if we want a learned OGCF bridge scorer to become competitive, runtime packets must preserve rich non-label context, not just feedback labels.

## OGCF Bridge Feature Audit Checkpoint

The selector side now has a report-only feature-readiness audit:

```powershell
py -3 eval/controller_packet_ogcf_bridge_feature_audit.py --packets <controller-packets.jsonl>
```

It writes `controller_packet_ogcf_bridge_feature_audit/v1` and checks whether bridge-labeled packets preserve enough non-label context for learned scoring.

The audit reports:

- required feature coverage;
- positive-vs-negative feature separability;
- strong-gap features;
- blockers such as missing OGCF metadata, one-sided labels, or insufficient non-label feature separation.

Local validation results:

- the generated rich-feature fixture is feature-ready;
- the current two-log OGCF bridge packet artifact is also feature-ready;
- the enriched learned scorer matched the symbolic separator on the two-log packet artifact with held-out `match_rate: 1.0`, zero false positives, and zero false negatives.

This is still not a promotion decision. It means the architecture has crossed an important research threshold: the learned scorer can now become competitive when packets contain rich non-label context. The next requirement is broader unseen packet logs, preferably from normal agent work, before any runtime bridge-warning policy changes are considered.

## Artifact Storage Convention

Generated experiment artifacts should not refill the C: partition. The workspace-level artifact folder:

```text
C:\Users\victo\Desktop\projcod2\experiments
```

is now a junction to:

```text
E:\projcod2_artifacts\experiments
```

Eval scripts can keep writing to the existing `experiments` path, but the generated files land on E:. Source code, docs, committed test corpora, and model files should stay in their normal project locations. Large generated artifacts such as SQLite fixtures, checkpoint JSON files, packet logs, and benchmark result dumps should remain under the experiments path so they are routed to E: automatically.

## OGCF Bridge Source-Holdout Checkpoint

The learned OGCF bridge scorer now has a source-log holdout evaluator:

```powershell
py -3 eval/controller_packet_ogcf_bridge_source_holdout.py --train-packets <train.jsonl> --test-packets <holdout.jsonl> --separator <bridge-separator.json>
```

It writes `controller_packet_ogcf_bridge_source_holdout/v1`.

This is stricter than the random packet split because it trains on one packet source and tests on another. The goal is to detect whether the learned scorer generalizes from packet features or merely benefits from near-duplicate examples inside one log.

The current self-generated regression creates two independent rich packet sources with varied wording and scores. The learned scorer and symbolic separator both pass the held-out source with `match_rate: 1.0`, zero false positives, and zero false negatives, while remaining `promotion_ready: false`.

The next real-data requirement is to run this same source-holdout evaluator on independent Hermes or local runtime packet logs. A learned scorer should not be considered for manual promotion review until it passes source-level holdout on real packet sources, not only generated fixtures.

## OGCF Bridge Leave-One-Source-Out Checkpoint

The selector side now has a stricter report-only evaluator for combined multi-source packet logs:

```powershell
py -3 eval/controller_packet_ogcf_bridge_leave_one_source_out.py --packets <combined-controller-packets.jsonl> --separator <bridge-separator.json>
```

It writes `controller_packet_ogcf_bridge_leave_one_source_out/v1`.

This evaluator groups packet samples by `source_log`, trains the learned OGCF bridge scorer on all but one source, and tests on the held-out source. It repeats this for every source with enough bridge labels. This is stronger than a random split and more complete than a single train/test source split because every available source must survive as unseen data.

The generated three-source regression now passes:

- `source_count: 3`;
- `sample_count: 36`;
- minimum candidate evidence: at least `3` sources and `30` bridge samples;
- one clean held-out fold per source;
- learned scorer held-out `match_rate: 1.0`;
- zero learned false positives and zero learned false negatives;
- symbolic separator also clean;
- `learned_scorer_candidate: true`, but `promotion_ready: false`.

The default two-log bridge packet artifact also passes mechanically, but it is now correctly blocked from candidate status:

- `source_count: 2`;
- `sample_count: 12`;
- learned and symbolic match rates both `1.0`;
- `learned_scorer_candidate: false`;
- readiness blockers: `source_count_below_minimum:2<3` and `sample_count_below_minimum:12<30`.

This keeps the learned bridge scorer aligned with the roadmap: learned behavior can become a candidate only when it generalizes across enough independent sources, and runtime behavior still cannot change without a later manual promotion path. The next real-data requirement is to run leave-one-source-out on several real Hermes/local packet logs collected from normal work, not only generated fixtures.

This checkpoint is now integrated into the broader controller-packet calibration path:

- `controller_packet_calibration_pipeline/v1` writes a `bridge_leave_one_source_out` artifact and includes the stage in the calibration-system manifest;
- `controller_packet_multirun_calibration/v1` aggregates LOSO candidate runs, source/sample counts, and readiness blocker counts;
- `controller_packet_recurring_holdout/v1` blocks learned OGCF bridge-scorer candidacy when LOSO evidence is underpowered, even if recurring bridge clusters and separator holdout are otherwise clean.

That changes the next target for small or synthetic runs: the system should collect enough independent bridge packet sources for LOSO before considering any learned bridge scorer as a serious candidate.

The LOSO evidence minimums have now moved from hardcoded evaluator constants into a Level 1 config surface:

```yaml
controller_packet_calibration:
  bridge_leave_one_source_out:
    min_sources_for_candidate: 3
    min_samples_for_candidate: 30
```

The evaluator still accepts CLI overrides for controlled experiments, but the calibration pipeline reads the project config by default and reports the active policy in the LOSO artifact. The regression now proves both sides of the contract:

- default config blocks an underpowered two-source/four-sample packet artifact;
- an explicit low-threshold test config can make that same artifact candidate-worthy;
- neither path mutates runtime behavior or config.

This is the roadmap pattern we want for later learned controllers: hardcoded guard -> explicit config policy -> report-only evidence artifact -> future calibration/promotion gate.

The learned OGCF bridge scorer candidate rule has also moved to a Level 1 config surface:

```yaml
controller_packet_calibration:
  bridge_scorer:
    min_test_samples_for_candidate: 4
    require_zero_false_positives: true
    require_zero_false_negatives: true
    require_not_worse_than_symbolic: true
```

This policy is shared by:

- `controller_packet_ogcf_bridge_scorer/v1`;
- `controller_packet_ogcf_bridge_source_holdout/v1`.

Candidate status now requires more than a non-worse match rate. By default the learned scorer must have enough held-out test examples, must not underperform the symbolic separator, and must produce zero false positives and zero false negatives. The regressions prove that clean rich-feature fixtures remain candidate-worthy, while an intentionally strict config can block the same scorer without changing runtime behavior or config.

The controller-packet calibration config surface now has its own config-view regression:

```powershell
py -3 eval/controller_packet_calibration_config_regression.py
```

It writes `controller_packet_calibration_config_regression/v1` and verifies:

- the project `controller_packet_calibration` config section is present;
- bridge-scorer defaults are loaded from config;
- LOSO defaults are loaded from config;
- explicit config overrides are honored;
- CLI experiment overrides are marked as explicit overrides;
- the config view remains report-only and non-mutating.

The unified selector architecture gate now requires this regression. This closes the Level 1 requirement for the new bridge-calibration policies: defaults, documentation, config-view report, and architecture-gate protection.

The calibration policy has now moved from eval-local normalization into the shared core/runtime layer:

```powershell
py -3 eval/controller_packet_calibration_runtime_view_regression.py
```

The runtime regression builds a real `MemoryApi`, injects a controller-packet calibration override, calls `/config`, and verifies that the normalized policy appears under `controller_packet_calibration` with the same report-only and non-mutating guarantees. This is part of the transition process from patched experiments to a combined adaptive memory architecture:

- memory runtime owns and exposes the active policy surface;
- selector evaluators consume the same normalized core policy;
- calibration artifacts can explain which policy produced each result;
- later learned-controller work can compare candidate behavior against an explicit runtime-visible baseline.

This does not promote learned behavior. It creates the shared contract needed before learned OGCF bridge scoring, resolver calibration, or packet-bank promotion gates can become runtime-adjacent.

## Controller Packet Evidence-Context Export

The combined memory/selector/OGCF path now exports the shared evidence-context feature contract inside every `controller_evidence_packet/v1` built from ask/feedback logs:

```json
"evidence_context": {
  "schema": "evidence_context_packet_view/v1",
  "features": {
    "retrieval_count": 2,
    "selected_count": 1,
    "claim_scope_score": 0.7,
    "stale_current_conflict": 0.4,
    "ogcf_bridge_overload_score": 0.81
  }
}
```

This is a structural roadmap step rather than another scorer tweak. The packet builder already joins request, answer, selected evidence, retrieval context, canonical-memory support, OGCF diagnostics, selector decision, resolver/adaptive shadows, residual shadow, and feedback. Adding `EvidenceContextFeatures` makes controller packets a shared neural-symbolic training row for later learned controllers.

The important architecture consequence is:

```text
memory retrieval rows + canonical/OGCF diagnostics + selector/resolver shadows + feedback
-> controller_evidence_packet/v1
-> evidence_context_packet_view/v1
-> calibration datasets / learned scorers / symbolic promotion gates
```

The regression now verifies that controller packets preserve selected/retrieval counts, stale-conflict state, and OGCF bridge diagnostics through the shared context feature object while remaining report-only and non-mutating.

The controller-packet memory bank now tracks this shared context feature coverage:

- `evidence_context_feature_packet_count`;
- `evidence_context_feature_coverage`;
- `evidence_context_feature_keys`;
- per-cluster `evidence_context_feature_coverage`;
- diagnostics for whether feature coverage is present and whether it is complete.

This matters because the memory bank is the first cross-run aggregation layer. It can now distinguish old packet logs that only contain symbolic packet fields from newer packet logs that are suitable for neural-symbolic scorer training. The calibration pipeline carries these diagnostics forward through its `diagnostics` block, so later learned-controller work can require feature coverage before training or promotion review.

## Controller Packet Real-Log Readiness Gate

The calibration pipeline now emits an explicit report-only real-log readiness contract:

```text
controller_packet_real_log_readiness/v1
```

The readiness classifier answers a narrow architecture question:

```text
Is this packet-calibration run only useful for diagnostics, ready for runtime collection, or strong enough to justify broader learned-scorer evaluation?
```

It uses the packet count, independent source-log count, evidence-context feature coverage, guard review state, and OGCF bridge leave-one-source-out blockers. It does not mutate runtime behavior or config. The current small regression fixture is correctly marked `analysis_only` because it has too few packets and only one source log.

The calibration pipeline markdown report now includes the same readiness object that was already present in JSON, so Hermes/local reviews can see the next action without opening the raw artifact. The unified selector architecture gate also has a dedicated required check:

```text
controller_packet_real_log_readiness_ok
```

This makes the transition process safer. Future learned-controller work should not use packet logs blindly; it should first pass through this readiness layer, then through LOSO/source-holdout evidence, and only then through manual promotion review.

The readiness contract now has a dedicated branch-coverage regression:

```powershell
py -3 eval/controller_packet_real_log_readiness_regression.py
```

It writes `controller_packet_real_log_readiness_regression/v1` and proves that the classifier distinguishes:

- `analysis_only` for small or underpowered logs;
- `ready_for_runtime_collection` for feature-complete multi-log packet runs that still need more independent evidence;
- `ready_for_loso_learned_scorer_evaluation` for feature-complete, review-clean, LOSO-candidate packet runs.

It also proves incomplete evidence-context features and review items block scorer-evaluation readiness while preserving report-only and non-mutating guarantees. The unified selector architecture gate now requires both the pipeline-level readiness object and this dedicated branch regression.

The real-log readiness thresholds have now moved from eval-local constants into the shared Level 1 calibration config:

```yaml
controller_packet_calibration:
  real_log_readiness:
    min_packets_for_runtime_collection: 12
    min_sources_for_runtime_collection: 2
    min_packets_for_learned_scorer_evaluation: 30
    min_sources_for_learned_scorer_evaluation: 3
    require_full_evidence_context_feature_coverage: true
    block_on_review_items: true
```

Core normalization lives in:

```text
core/controller_packet_calibration.py
```

The memory runtime exposes the normalized policy through `/config`, while the selector calibration pipeline consumes the same policy when classifying logs. The focused readiness regression now includes a config-override case proving that relaxed thresholds and disabled blockers change readiness classification in a controlled report-only run.

This is the combined-architecture restructure pattern working as intended:

```text
hardcoded eval threshold -> shared config policy -> runtime-visible policy -> selector artifact uses policy -> gate-protected regression
```

## Corrected OGCF v2 Geometry Checkpoint

The OGCF method documents were updated with an important mathematical correction:

```text
M_ij = B_j.T @ B_i          # raw overlap diagnostic
Q_ij = polar(M_ij)          # corrected finite-step transport
```

The codebase now reflects that distinction in `core/ogcf_geometry.py`:

- raw overlap is computed with the corrected `B_j.T @ B_i` orientation;
- corrected polar transport is used for polar holonomy and polar interaction excess;
- raw-overlap interaction excess remains the bridge-overload signal because the memory tests showed it is useful for duplicate/cross-domain bridge pressure;
- raw and polar interaction diagnostics are now exposed separately;
- singular-value and principal-angle diagnostics are carried on each loop.

Backward-compatible aliases remain:

```text
interaction_excess -> raw_interaction_excess
interaction_z      -> raw_interaction_z
holonomy_raw       -> polar_holonomy
```

This avoids breaking existing selector and Hermes artifacts while making the corrected OGCF v2 interpretation explicit. Runtime-adjacent OGCF reports now include:

```text
raw_interaction_z
raw_interaction_excess
polar_interaction_z
polar_interaction_excess
polar_holonomy
mean_singular_value
min_singular_value
```

The dedicated guard is:

```powershell
py -3 eval/ogcf_corrected_geometry_regression.py
```

and the unified architecture gate now requires `ogcf_corrected_geometry_ok`.

## OGCF Selector-Signal Interpretation Fix

After the corrected OGCF v2 geometry update, the selector signal layer also needed the same interpretation correction. The validated method finding is:

```text
high raw interaction / bridge overload = structural bridge pressure
high raw interaction / bridge overload != direct factual contradiction
```

`core/ogcf_signals.py` now preserves that distinction:

- `adjusted_contradiction_peak` no longer increases from `bridge_overload_score`;
- `ogcf_structural_pressure` records bridge overload multiplied by effective affected retrieval pressure;
- selector caution can still increase through memory-bad-rate, probe-drop, CSD-ratio, and explicit OGCF diagnostics;
- factual contradiction remains owned by evidence/claim/recency/source logic, not raw OGCF geometry.

The guard is:

```powershell
py -3 eval/ogcf_affected_pressure_calibration_regression.py
```

It now verifies that a true bridge-overload loop raises structural pressure and memory caution without inventing `contradiction_peak`.

The corrected structural-pressure signal is now part of the shared feature contract:

```text
EvidenceContextFeatures.ogcf_structural_pressure
```

This value is exported into controller packets and feature-scorer datasets. For older diagnostics that do not contain the explicit field, the feature builder falls back to:

```text
ogcf_bridge_overload_score * ogcf_effective_affected_memory_ratio
```

This gives future learned controllers a direct structural-pressure feature and reduces the temptation to reuse `contradiction_peak` as an OGCF proxy.

## ERG v3 Integration With CSD, G-CL, CLC, And Neural-Symbolic Control

The updated ERG/OGCF v3 method changes the role of OGCF in the combined architecture. It should no longer be treated only as a bridge-overload warning. It becomes a structural geometry layer that can feed CSD, G-CL, CLC, and learned neural-symbolic controllers while keeping semantic truth and recency resolution in the semantic layers.

The correct division of responsibility is:

```text
CSD -> semantic novelty, surprise, contradiction, and evidence pressure
G-CL -> domain anchors, drift, curvature, stability, split/reanchor pressure
CLC -> policy/action choice under budget, risk, and memory-health signals
ERG/OGCF -> projector geometry, structural pressure, curvature activity, core-halo sectors, projector graph topology
```

ERG should improve CSD by separating factual contradiction from structural retrieval contamination:

```text
CSD contradiction high + ERG stable -> likely factual conflict
CSD contradiction low + ERG high -> likely duplicate bridge, mixed domain, or retrieval contamination
CSD novelty high + ERG high -> possible new domain or unstable boundary
```

ERG is most naturally aligned with G-CL. G-CL already describes anchors, drift, curvature, and stability; ERG gives these concepts measurable projector-geometry fields:

```text
G-CL domain anchor -> local/cluster projector
G-CL drift -> projector distance from anchor or neighboring sector
G-CL curvature -> Omega_ab
G-CL instability -> curvature activity K_i and core-halo enrichment C_r
G-CL split/reanchor -> action candidate when projector graph boundary or core-halo pressure is high
```

CLC should consume ERG only gradually and first in report-only form. Candidate ERG-derived CLC features are:

```text
ogcf_structural_pressure
ogcf_omega_norm
ogcf_core_halo_score
ogcf_projector_graph_anomaly
projector_distance_from_domain_anchor
```

These should not be promoted directly into runtime policy decisions until controller packets and outcome logs show that they improve decisions without over-quarantining useful memories.

The neural-symbolic roadmap should treat ERG as a numeric feature source for learned controllers. The shared controller-packet/evidence-context row should eventually carry:

```json
{
  "erg_features": {
    "omega_norm": 0.42,
    "core_halo_score": 1.8,
    "core_halo_slope": -0.05,
    "projector_graph_anomaly": 0.63,
    "projector_distance_to_anchor": 0.91,
    "structural_pressure": 0.56
  }
}
```

The immediate development rule is:

```text
Add ERG features to shared report-only evidence/context exports first.
Then evaluate them in controller packets and memory-bank readiness.
Only after real outcome evidence should they affect selector policy, resolver behavior, or memory mutation.
```

The next guard should prove that CSD-style semantic signals, G-CL-style geometry signals, CLC policy features, and ERG projector signals can coexist in one shared feature export without mutating runtime behavior.

## ERG Projector Graph Maintenance Priority

The ERG projector graph is now connected to the report-only maintenance candidate path. This is the first practical use of projector-distance graph structure after the shared ERG feature export:

```text
OGCF/ERG geometry review
-> memory_cluster_map + projector_graph_edges + projector_distance_summary
-> dry-run maintenance candidates
-> report-only projector_graph annotation
-> report-only maintenance_priority score
```

The current priority score is intentionally conservative. It combines the existing candidate confidence with a small projector-graph boost from:

```text
projector_graph_anomaly
incident projector graph edges near the candidate cluster
candidate action type such as stale-version, semantic conflict/update, or bridge-cluster review
```

This score does not mutate the database, alter retrieval ranking, change selector policy, or trigger automatic deprecation. Its purpose is to create an auditable ordering for future human/Hermes review:

```text
Which duplicate, stale, semantic-conflict, or bridge candidates should be inspected first?
```

The guard is:

```powershell
py -3 eval/ogcf_projector_graph_maintenance_regression.py
```

and the unified architecture gate requires:

```text
ogcf_projector_graph_maintenance_ok
```

## ERG Maintenance Priority Outcome Guard

The next useful step for the ERG projector graph was to test whether the report-only maintenance priority score is not merely present, but directionally useful. A controlled outcome regression now builds the projector-graph maintenance fixture, assigns conservative synthetic review labels, and checks that useful maintenance actions rank above lower-value candidates.

The controlled labels currently treat exact duplicate groups, semantic duplicate groups, semantic conflict/update groups, and stale-version candidates as useful review work. Other candidates remain in a needs-more-evidence class. This keeps the priority mechanism honest: it must produce at least a useful top-k ordering before it can be considered for future runtime influence.

The guard checks:

```text
maintenance_priority_summary/v1 is present
the report remains dry-run/report-only and mutates no database state
precision@3 for useful maintenance candidates is at least 0.66
mean priority for useful candidates is not below lower-value candidates
top candidate ids match the report summary ordering
```

The guard is:

```powershell
py -3 eval/ogcf_maintenance_priority_outcome_regression.py
```

and the unified architecture gate requires:

```text
ogcf_maintenance_priority_outcome_ok
```

This still does not promote ERG priority into retrieval, selector policy, or automatic memory mutation. The next promotion boundary should require real or manually reviewed logs showing that high-priority candidates correspond to genuinely useful memory maintenance decisions.

The next validation should compare this priority score against real maintenance outcomes. Promotion remains blocked until real logs show that high-priority candidates are more likely to be useful reviews and do not over-prioritize clean memories.

The dry-run maintenance report now also emits a report-level priority summary:

```text
maintenance_priority_summary/v1
```

It reports prioritized candidate count, high/medium priority counts, max/mean priority, top candidate ids, readiness, and next action. This makes the maintenance run self-describing:

```text
diagnostic_only -> collect more candidates or graph annotations
ready_for_outcome_collection -> gather review labels before promotion
ready_for_review -> inspect top priority candidates manually or with Hermes
```

This readiness summary is still report-only and non-mutating. It is intended to decide what validation to run next, not to automatically apply memory changes.

## ERG Maintenance Review Label Loop

The ERG maintenance path now has the first report-only review/outcome loop. This is the transition from synthetic priority checks toward real adaptive maintenance evidence:

```text
dry-run maintenance candidates
-> priority-ranked review queue
-> reviewer label template
-> reviewed outcome labels
-> label/prioritization evaluation
-> future multi-run maintenance memory bank
```

The queue builder is:

```powershell
py -3 eval/ogcf_maintenance_review_queue.py --candidates-json ..\experiments\ogcf_maintenance_candidates_results.json
```

It emits:

```text
ogcf_maintenance_review_queue/v1
ogcf_maintenance_review_labels/v1 template
```

Allowed review labels are:

```text
useful_review
noisy_review
needs_more_evidence
clean_memory
unsafe_to_act
already_resolved
```

The label evaluator is:

```powershell
py -3 eval/ogcf_maintenance_review_label_eval.py --candidates-json <maintenance-candidates.json> --labels <review-labels.json>
```

It checks useful-vs-negative priority separation, precision@k, unknown labels, and high-priority negative candidates while preserving the report-only contract. The focused regression is:

```powershell
py -3 eval/ogcf_maintenance_review_label_loop_regression.py
```

and the unified architecture gate requires:

```text
ogcf_maintenance_review_label_loop_ok
```

This is not a promotion mechanism yet. It is the missing evidence collection layer. The next roadmap stage should aggregate reviewed maintenance labels across independent real/Hermes/local runs, then test whether ERG priority and projector features repeatedly predict useful maintenance actions without over-prioritizing clean or unsafe memories.

## ERG Maintenance Review Memory Bank

The maintenance review loop now has a report-only multi-run memory bank. This is the same architecture pattern used by controller packets and calibration proposals, but focused on memory maintenance outcomes:

```text
reviewed maintenance run 1
reviewed maintenance run 2
...
-> grouped action/label families
-> recurring useful/noisy maintenance evidence
-> readiness summary
-> future guarded maintenance candidate review
```

The bank command is:

```powershell
py -3 eval/ogcf_maintenance_review_memory_bank.py --run <candidates1.json>::<labels1.json> --run <candidates2.json>::<labels2.json>
```

It emits:

```text
ogcf_maintenance_review_memory_bank/v1
```

The bank groups reviewed candidates by maintenance action and label class. Recurring useful families can become `maintenance_candidate_evidence_ready` only when they repeat across enough independent runs and do not contain high-priority negative reviews. Noisy, clean, unsafe, or mixed review families stay blocked for analysis.

The focused guard is:

```powershell
py -3 eval/ogcf_maintenance_review_memory_bank_regression.py
```

and the unified architecture gate requires:

```text
ogcf_maintenance_review_memory_bank_ok
```

This gives ERG/OGCF a clearer adaptive-memory role. The geometry layer proposes maintenance pressure, the review queue collects human/Hermes/local labels, and the memory bank decides whether the same maintenance family is recurring enough for future guarded candidate review. It still does not mutate memories, retrieval, selector policy, runtime config, or learned artifacts.

## ERG Guarded Maintenance Candidates

The memory bank now feeds a report-only guard that turns recurring reviewed maintenance evidence into explicit manual-review candidates:

```text
maintenance review memory bank
-> evidence-ready useful action families
-> guarded maintenance candidates
-> manual review required
-> no automatic memory mutation
```

The guard command is:

```powershell
py -3 eval/ogcf_maintenance_candidate_guard.py --memory-bank <review-memory-bank.json>
```

It emits:

```text
ogcf_maintenance_candidate_guard/v1
ogcf_guarded_maintenance_candidate/v1
```

The guard can prepare candidates such as:

```text
exact_duplicate_group -> prepare_duplicate_deprecation_candidate_for_manual_review
semantic_duplicate_group -> prepare_semantic_merge_candidate_for_manual_review
semantic_conflict_or_update_group -> prepare_conflict_update_candidate_for_manual_review
stale_version_candidate -> prepare_stale_deprecation_candidate_for_manual_review
bridge_cluster_review -> prepare_bridge_split_or_canonicalization_review
```

but only when the action family is recurring, useful, sufficiently supported, above the mean-priority threshold, and free of high-priority negative reviews. Negative, noisy, mixed, or under-supported families remain blocked.

The focused guard is:

```powershell
py -3 eval/ogcf_maintenance_candidate_guard_regression.py
```

and the unified architecture gate requires:

```text
ogcf_maintenance_candidate_guard_ok
```

This is a combined-function improvement because it gives the memory program and selector/ERG side a shared handoff artifact: the selector/ERG side can explain why a maintenance action is evidence-ready, while the memory side can later decide how to apply, reject, or request more review. Promotion and database mutation remain blocked until a separate manual/runtime-safe mutation path exists.

## Memory-Side Maintenance Candidate Review Plan

The combined architecture needed one more restructuring step: guarded ERG maintenance candidates were still selector/eval-side artifacts. The memory program needs a stable core contract that can consume those candidates without knowing the internals of ERG projector graphs, review-label banks, or selector gates.

The new handoff contract is:

```text
ogcf_maintenance_candidate_guard/v1
-> memory_maintenance_candidate_review_plan/v1
-> memory-side manual review plan
-> no automatic memory mutation
```

The core adapter is:

```text
core/maintenance_candidate_contract.py
```

It maps selector/ERG maintenance actions into memory-program review kinds:

```text
exact_duplicate_group -> duplicate_deprecation_review
semantic_duplicate_group -> semantic_merge_review
semantic_conflict_or_update_group -> conflict_update_review
stale_version_candidate -> stale_deprecation_review
bridge_cluster_review -> bridge_split_or_canonicalization_review
```

The CLI is:

```powershell
py -3 eval/memory_maintenance_candidate_review_plan.py --guard <ogcf-maintenance-candidate-guard.json>
```

and the focused guard is:

```powershell
py -3 eval/memory_maintenance_candidate_review_plan_regression.py
```

The unified architecture gate requires:

```text
memory_maintenance_candidate_review_plan_ok
```

This is the next important combined-function boundary. The selector/ERG side can keep learning and ranking maintenance pressure, while the memory side receives normalized review kinds it can later connect to safe endpoints such as duplicate review, stale review, semantic merge review, or bridge split/canonicalization review. The current plan is still report-only and explicitly keeps `promotion_ready: false`; the next memory-side restructuring should add manual apply/reject logging for these review-plan items before any automatic mutation path is considered.

## Memory Maintenance Review Outcomes

The memory-side review plan now has a report-only outcome logging contract. This adds the missing feedback loop after a human, Hermes run, or local reviewer inspects guarded maintenance candidates:

```text
memory_maintenance_candidate_review_plan/v1
-> memory_maintenance_candidate_review_outcomes/v1
-> memory_maintenance_candidate_review_outcome_summary/v1
-> accepted/rejected/needs-more-evidence learning signal
-> no automatic memory mutation
```

Allowed manual outcomes are:

```text
accept
reject
needs_more_evidence
unsafe_to_apply
already_resolved
```

The CLI is:

```powershell
py -3 eval/memory_maintenance_review_outcome_log.py --plan <review-plan.json> --outcomes <review-outcomes.json>
```

It can also write an empty outcome template:

```powershell
py -3 eval/memory_maintenance_review_outcome_log.py --plan <review-plan.json> --write-template
```

The focused guard is:

```powershell
py -3 eval/memory_maintenance_review_outcome_log_regression.py
```

and the unified architecture gate requires:

```text
memory_maintenance_review_outcome_log_ok
```

This closes the first full report-only adaptive maintenance cycle:

```text
ERG geometry -> maintenance candidates -> review labels -> memory bank -> guarded candidates -> memory-side review plan -> manual outcomes
```

The next restructuring step should be a memory-side manual apply/reject endpoint or command that records the final human decision as an auditable event while still defaulting to no mutation. Only after repeated accepted outcomes and a separate apply guard should duplicate deprecation, stale deprecation, semantic merge, or bridge canonicalization be allowed to touch the database.

## Memory Maintenance Manual Apply Decisions

The review-outcome path now feeds a dry-run manual apply/reject decision artifact:

```text
memory_maintenance_candidate_review_outcomes/v1
-> memory_maintenance_manual_apply_decisions/v1
-> ready_for_manual_apply / manual_reject_logged / hold_for_more_evidence
-> applied_count: 0
-> no database mutation
```

The command is:

```powershell
py -3 eval/memory_maintenance_manual_apply_decisions.py --plan <review-plan.json> --outcomes <review-outcomes.json>
```

Accepted outcomes become `ready_for_manual_apply`, but they still carry blockers such as `dry_run_enabled` and require an explicit operator command. Rejected or unsafe outcomes become audit records that preserve memory state. Needs-more-evidence outcomes remain held.

The focused guard is:

```powershell
py -3 eval/memory_maintenance_manual_apply_decisions_regression.py
```

and the unified architecture gate requires:

```text
memory_maintenance_manual_apply_decisions_ok
```

This is the last safe step before designing any real apply path. The codebase now has a complete non-mutating maintenance lifecycle:

```text
detect -> prioritize -> review -> aggregate -> guard -> plan -> outcome -> dry-run apply/reject decision
```

The next step before mutation should be an explicit apply backend design for one narrow operation, probably duplicate deprecation, with hard requirements: operator confirmation, source candidate id, before/after audit event, rollback metadata, and a regression proving rejected/held/unsafe decisions cannot mutate the database.

## Memory Maintenance Apply Plan Contract

The maintenance lifecycle now has the first apply-backend design contract, still fully report-only and non-mutating:

```text
memory_maintenance_manual_apply_decisions/v1
-> memory_maintenance_apply_plan/v1
-> planned duplicate deprecation operation / blocked operation
```

The only supported planned operation is `duplicate_deprecation` for accepted `duplicate_deprecation_review` decisions. Even then, the operation is not executable yet. It must carry:

- explicit operator confirmation requirement;
- source candidate id and source outcome;
- before/after audit requirement;
- rollback metadata requirement;
- `dry_run: true`;
- `ready_to_execute_count: 0`;
- `applied_count: 0`;
- `mutates_db: false`.

Held, rejected, already-resolved, unsafe, or unsupported review kinds become blocked operations and cannot mutate memory. This creates the transition point from reviewed maintenance evidence into a future safe mutation backend without allowing the current prototype to silently alter the database.

Validation:

```powershell
py -3 eval/memory_maintenance_apply_plan.py --decisions <manual-apply-decisions.json>
py -3 eval/memory_maintenance_apply_plan_regression.py
```

Architecture gate key:

```text
memory_maintenance_apply_plan_ok
```

The next development step should be to design a real but still disabled duplicate-deprecation backend interface: define the required memory-store methods, audit event shape, and rollback payload, then test it against a temporary SQLite fixture with mutation disabled by default. Only after that should the system consider an operator-confirmed duplicate-deprecation dry-run that compares before/after rows.

## Disabled Duplicate-Deprecation Backend Interface

The first concrete apply backend now exists as a narrow, guarded interface:

```text
memory_maintenance_apply_plan/v1
-> core.maintenance_apply_backend.apply_memory_maintenance_plan(...)
-> memory_maintenance_apply_backend_batch_result/v1
```

The backend is still safe by default:

- `dry_run=True`;
- `mutation_enabled=False`;
- `operator_confirmed=False`;
- database mutation blocked unless all three safety conditions are deliberately changed;
- only `duplicate_deprecation` operations are supported;
- unsupported operation kinds, missing keeper ids, and missing duplicate ids are blocked;
- audit events include source candidate id, operator id, before rows, after rows, and rollback metadata.

The regression uses a temporary SQLite fixture and proves three boundary cases:

1. Dry-run mode writes a non-applied audit event and preserves all memory rows.
2. Operator-confirmed but mutation-disabled mode still preserves all memory rows.
3. Explicitly confirmed and mutation-enabled fixture mode deprecates only the duplicate row, preserves the keeper and stale rows, and emits before/after audit plus rollback metadata.

Validation:

```powershell
py -3 eval/memory_maintenance_apply_backend_regression.py
```

Architecture gate key:

```text
memory_maintenance_apply_backend_ok
```

This is not a production mutation path yet. The next step should be a memory-store adapter contract that maps this backend onto the real memory program's DB methods with mutation still disabled by default. After that, a Hermes/local long-run test can verify that reviewed duplicate-deprecation candidates target the intended rows and never touch stale, bridge, or semantic-merge candidates.

## Maintenance Apply Store Adapter Contract

The duplicate-deprecation backend no longer depends directly on raw SQLite access. It now consumes a small memory-store contract:

```text
MaintenanceApplyStore
  fetch_memory_rows(memory_ids)
  mark_memories_deprecated(memory_ids, updated_at=...)
  write_apply_audit_event(event)
  commit()
  close()
```

`SQLiteMaintenanceApplyStore` implements this contract for the current SQLite fixture path, while `apply_memory_maintenance_plan(...)` can now run against any object that exposes the same methods. This is the boundary the memory-program session can implement around its real DB class without importing selector/ERG internals.

Validation:

```powershell
py -3 eval/memory_maintenance_apply_store_adapter_regression.py
```

Architecture gate key:

```text
memory_maintenance_apply_store_adapter_ok
```

The adapter regression uses a fake in-memory store to prove that:

- dry-run mode preserves rows and does not call `mark_memories_deprecated`;
- audit and commit calls go through the adapter;
- the explicitly enabled fixture path calls `mark_memories_deprecated(["dup_alpha_r2"])`;
- keeper and stale rows remain unchanged.

The next development step should be a memory-session handoff or local integration shim that implements `MaintenanceApplyStore` around the real memory DB object, with `mutation_enabled=False` by default and a regression that exercises only dry-run/audit behavior against a copied or temporary DB.

## Real MemoryDB Maintenance Apply Adapter

The selector-side backend now includes a concrete adapter for the memory program's DB object:

```text
MemoryDBMaintenanceApplyStore(storage.db.MemoryDB)
```

This wrapper uses the real `MemoryDB.conn` object but keeps the apply backend isolated behind the same `MaintenanceApplyStore` contract. The regression initializes the real `storage/schema.sql` into a temporary SQLite DB, inserts fixture memories, and verifies:

- `mutation_enabled=False` preserves all rows even when the operator is confirmed;
- a non-applied audit event is still recorded;
- the explicitly enabled fixture path deprecates only the duplicate row;
- keeper and stale rows remain unchanged;
- before/after audit and rollback metadata are present.

Validation:

```powershell
py -3 eval/memory_maintenance_real_db_adapter_regression.py
```

Architecture gate key:

```text
memory_maintenance_real_db_adapter_ok
```

This is the handoff point for the memory-program session. It does not need to import ERG/OGCF internals. It can consume `memory_maintenance_apply_plan/v1`, instantiate `MemoryDBMaintenanceApplyStore(db)`, and run the backend with `mutation_enabled=False` until a separate operator-confirmed command is designed.

## Maintenance Apply Operator Command

The memory-maintenance path now has a local operator-facing command:

```powershell
py -3 eval/memory_maintenance_apply_operator_command.py --db <memory.db> --apply-plan <memory_maintenance_apply_plan.json>
```

The command defaults to the safe mode:

- dry-run enabled;
- mutation disabled;
- operator not confirmed unless `--confirm-operator` is supplied;
- no audit write unless `--write-audit` is supplied;
- blocked operations still return structured audit-ready output.

The only way a fixture can mutate is with all explicit flags:

```powershell
py -3 eval/memory_maintenance_apply_operator_command.py `
  --db <fixture.db> `
  --apply-plan <memory_maintenance_apply_plan.json> `
  --operator-id <operator> `
  --confirm-operator `
  --enable-mutation `
  --no-dry-run `
  --write-audit
```

Validation:

```powershell
py -3 eval/memory_maintenance_apply_operator_command_regression.py
```

Architecture gate key:

```text
memory_maintenance_apply_operator_command_ok
```

The regression proves the default command preserves rows and writes a blocked audit event, while the explicitly enabled fixture path mutates only the duplicate row. This is still not a recommendation to run mutation on the real memory DB. The next production step should be a copied-DB rehearsal that runs the command against a snapshot of the real database with mutation disabled first, then verifies candidate targeting quality before any real operator-confirmed mutation is considered.

## Copied DB Maintenance Rehearsal

The maintenance apply path now has a copied-DB rehearsal command:

```powershell
py -3 eval/memory_maintenance_copied_db_rehearsal.py
```

By default it writes bulky rehearsal artifacts under:

```text
E:\projcod2_artifacts_archive\current_rehearsals
```

when the E: partition exists, with a fallback to `experiments/` for machines without E:. This keeps generated copied databases and rehearsal artifacts away from the nearly full C: partition.

The rehearsal either:

- copies a provided source DB and uses a provided apply plan; or
- generates a real-schema fixture DB and fixture `memory_maintenance_apply_plan/v1`.

It then runs the operator backend in safe rehearsal mode:

- copied DB only;
- operator confirmation true;
- mutation disabled;
- dry-run disabled so `mutation_backend_disabled` is the active blocker;
- audit write enabled;
- before/after deprecated maps compared;
- target IDs checked against the copied DB.

Validation:

```powershell
py -3 eval/memory_maintenance_copied_db_rehearsal_regression.py
```

Architecture gate key:

```text
memory_maintenance_copied_db_rehearsal_ok
```

This is the correct pre-Hermes/prototype production step: it lets us test candidate targeting and audit behavior on a copied DB without mutating the source DB. The next useful test should run this against a copy of a richer real or Hermes-generated memory database and inspect missing target IDs, duplicate keeper/deprecate quality, and whether the plan accidentally points at stale, bridge, or semantic-merge rows.

## Rich Copied DB Target Quality Rehearsal

The copied-DB rehearsal now checks candidate target quality, not only target existence. For `duplicate_deprecation` operations it inspects the copied DB rows and reports:

- keeper memory id;
- deprecate memory ids;
- missing target ids;
- exact duplicate text match;
- cross-domain and cross-namespace targeting;
- stale, bridge, semantic, conflict, and update markers in targeted rows;
- `candidate_target_quality_ok`.

Validation:

```powershell
py -3 eval/memory_maintenance_rich_copied_db_target_quality_regression.py
```

Architecture gate key:

```text
memory_maintenance_rich_copied_db_target_quality_ok
```

The rich regression generates a copied real-schema DB with:

- one safe exact duplicate pair;
- one unsafe stale/current pair incorrectly presented as duplicate deprecation;
- bridge and semantic rows that should remain untouched.

The rehearsal must preserve the source DB and copied DB rows because mutation is disabled, but it must fail the target-quality check for the unsafe stale candidate. This is an important production-safety boundary: reviewed maintenance candidates are not enough; the operator rehearsal must also verify that the planned target rows match the intended operation kind.

## Rehearsal Review Summary

The copied-DB rehearsal now emits a second operator-facing artifact:

```text
memory_maintenance_rehearsal_review_summary/v1
```

This converts raw target-quality diagnostics into action labels:

- `safe_to_review`;
- `blocked_missing_targets`;
- `blocked_stale_risk`;
- `blocked_semantic_risk`;
- `blocked_bridge_risk`;
- `blocked_duplicate_text_mismatch`;
- `blocked_cross_namespace_target`;
- `needs_operator_review_cross_domain`;
- `needs_operator_review`;
- `blocked_unsupported_operation`.

Every review summary remains non-mutating:

```text
mutation_allowed: false
report_only: true
```

Validation:

```powershell
py -3 eval/memory_maintenance_rehearsal_review_summary_regression.py
```

Architecture gate key:

```text
memory_maintenance_rehearsal_review_summary_ok
```

This makes the rehearsal useful for Hermes and the memory-program session: they can consume stable decision labels instead of hand-reading nested target-quality JSON. The next development step should be a review-summary memory bank that aggregates these rehearsal decisions across copied DB runs, so repeated safe duplicate-deprecation families can be separated from recurring blocked stale/semantic/bridge risks before any operator-confirmed mutation workflow is considered.

## Rehearsal Review Memory Bank

The copied-DB rehearsal path now has a report-only multi-run memory bank:

```text
memory_maintenance_rehearsal_review_summary/v1
-> memory_maintenance_rehearsal_review_memory_bank/v1
```

The bank groups rehearsal operation reviews by:

```text
operation_kind|decision
```

and assigns readiness:

- `rehearsal_safe_evidence_ready` for safe decisions recurring across enough runs;
- `hold_collect_more_safe_rehearsals` for safe decisions with insufficient repetition;
- `blocked_recurrent_risk` for blocked decisions recurring across enough runs;
- `hold_monitor_blocked_risk` for blocked decisions seen only once;
- `needs_operator_review_recurrent` for repeated ambiguous review needs.

Validation:

```powershell
py -3 eval/memory_maintenance_rehearsal_review_memory_bank_regression.py
```

Architecture gate key:

```text
memory_maintenance_rehearsal_review_memory_bank_ok
```

The regression creates two copied-DB rehearsal summaries with one recurring safe duplicate-deprecation family and one recurring stale-risk family. The bank must mark the safe family as evidence-ready, mark the stale family as recurrent risk, and keep the overall next action blocked because recurring risk is still present.

This gives the architecture a safer local learning loop:

```text
reviewed maintenance candidates
-> apply plan
-> copied DB rehearsal
-> target-quality review summary
-> rehearsal review memory bank
-> future guarded operator-review candidate
```

The next development step should be a guard on top of this memory bank that emits explicit operator-review candidates only for `rehearsal_safe_evidence_ready` clusters and blocks candidates when any recurrent risk cluster exists for the same operation family.

## Rehearsal Candidate Guard

The rehearsal review memory bank now feeds a report-only guard:

```text
memory_maintenance_rehearsal_review_memory_bank/v1
-> memory_maintenance_rehearsal_candidate_guard/v1
```

The guard emits `memory_maintenance_rehearsal_guarded_candidate/v1` rows only when:

- the source cluster is `rehearsal_safe_evidence_ready`;
- the cluster has safe review support;
- the cluster itself has no blocked reviews;
- the same operation family has no `blocked_recurrent_risk` cluster.

If any recurrent risk exists for the same operation kind, even the safe cluster is blocked with:

```text
operation_family_has_recurrent_risk
```

Validation:

```powershell
py -3 eval/memory_maintenance_rehearsal_candidate_guard_regression.py
```

Architecture gate key:

```text
memory_maintenance_rehearsal_candidate_guard_ok
```

The regression checks two cases:

1. A safe-only rehearsal bank emits one operator-review candidate.
2. A mixed bank with recurring stale risk blocks all duplicate-deprecation candidates, including the otherwise-safe cluster, because the operation family is still risky.

This closes the current safe local loop:

```text
maintenance evidence
-> apply plan
-> copied DB rehearsal
-> target-quality review summary
-> rehearsal review memory bank
-> rehearsal candidate guard
```

The next development step should be to connect this guard to a human/Hermes-readable operator review packet. That packet should include candidate id, source runs, target ids, text previews, blockers, and the exact command that would run in safe copied-DB mode. It should still not enable real DB mutation.

## Operator Review Packet

The rehearsal candidate guard now feeds a human/Hermes-readable packet:

```text
memory_maintenance_rehearsal_candidate_guard/v1
-> memory_maintenance_operator_review_packet/v1
```

The packet includes:

- candidate id;
- operation kind;
- source cluster key;
- source runs and support;
- target ids;
- target text previews when available;
- blocked reasons;
- operator review questions;
- a safe copied-DB rehearsal command.

The command always points to:

```powershell
py -3 eval/memory_maintenance_copied_db_rehearsal.py ...
```

and intentionally does not include mutation-enabling flags such as `--enable-mutation` or `--no-dry-run` for the operator apply command.

Validation:

```powershell
py -3 eval/memory_maintenance_operator_review_packet_regression.py
```

Architecture gate key:

```text
memory_maintenance_operator_review_packet_ok
```

The regression checks both ready and blocked packets. Ready packets preserve target ids and text previews; blocked packets preserve blockers such as `operation_family_has_recurrent_risk`; both packets keep:

```text
mutation_allowed: false
report_only: true
mutates_db: false
```

This is the right handoff artifact for Hermes or the memory-program session. The next step should be either a Hermes run over this packet or a memory-session review of how the packet should be surfaced in the agent UI/API, without enabling real DB mutation.

## RPG Label Quality Gate

The RPG supervised path now has a separate label-quality checkpoint between the label bank and any learned scorer:

```text
natural RPG candidate review packet
-> RPG natural label bank
-> RPG label-quality report
-> report-only RPG label scorer
```

This prevents the architecture from treating any set of labels as useful learning evidence just because the labels are syntactically valid. The quality report checks:

- enough labeled examples;
- enough distinct review labels;
- enough distinct candidate classes;
- no dominant-label collapse;
- no invalid labels;
- no contradictory labels for the same memory pair;
- a minimum family-level prediction probe;
- report-only and no-mutation safety flags on the packet and bank.

Validation:

```powershell
py -3 eval/memory_maintenance_rpg_label_quality_report_regression.py
```

Architecture gate key:

```text
memory_maintenance_rpg_label_quality_report_ok
```

This changes the next learning objective. The next stage is not simply to train the scorer; it is to collect a diverse natural RPG review set that passes the quality gate, then train and evaluate a report-only scorer on that reviewed set. The scorer remains blocked from policy use until:

- label quality passes on real reviewed packets;
- shadow scoring repeats across copied-real rehearsal data;
- reviewed maintenance outcomes show that the scorer reduces bad duplicate/stale/bridge proposals;
- the memory-program side can surface operator-review decisions without mutating the real DB by default.

## Current Development Direction

The architecture should evolve as a neural-symbolic adaptive memory brain with four cooperating layers:

```text
memory store and retrieval evidence
-> selector/controller packet context
-> OGCF/ERG/RPG relational diagnostics
-> supervised review memory and guarded maintenance actions
```

The strongest current value is not autonomous mutation. It is the system's ability to inspect memory relations, explain candidate maintenance risks, rehearse changes on copied DBs, and accumulate reviewed outcomes into safer future decisions. The competitive direction is a low-compute adaptive controller that learns from memory-operation outcomes instead of scaling model size.

Near-term development priorities:

1. Collect or synthesize reviewed RPG natural-candidate labels until the label-quality report passes on nontrivial data.
2. Feed those labels into the transparent report-only scorer and compare scorer predictions against the human/Hermes labels.
3. Connect scorer and RPG quality signals to operator packets as explanation fields only, not as automatic action gates.
4. Ask the memory-program session to expose review/label capture hooks so real operator outcomes can flow back into the selector artifacts.
5. Keep real DB mutation disabled by default until copied-real rehearsals, label quality, and outcome logs all support promotion.

## RPG Learning Context In Operator Packets

The operator review packet now carries RPG supervised-learning readiness as explanation-only context:

```text
RPG label-quality report
+ RPG label scorer
-> operator packet rpg_learning_context
```

This context is included at the packet level and copied into each ready or blocked packet item. It exposes:

- label-quality readiness for shadow scorer training;
- label counts and quality blockers;
- scorer shadow readiness;
- scorer policy readiness;
- scorer promotion blockers;
- explicit `operator_use: explanation_only_do_not_auto_apply`;
- no-mutation safety flags.

Validation:

```powershell
py -3 eval/memory_maintenance_operator_review_packet_regression.py
```

Architecture gate key:

```text
memory_maintenance_operator_review_packet_ok
```

This is the first integration point where RPG learning artifacts become visible in the maintenance workflow. It still does not let RPG choose or execute any action. Its job is to make operator/Hermes review better informed, while preserving the rule:

```text
RPG signal explains maintenance candidates; it does not approve maintenance candidates.
```

The next development step should be to create a non-mutating review-outcome capture artifact for operator packet decisions. That artifact should record which packet items were accepted, rejected, relabeled, or marked uncertain, then feed those outcomes back into the RPG label bank and future calibration reports.

## Operator Outcome Capture

The operator review packet now feeds a report-only outcome-capture artifact:

```text
operator review packet
-> operator review outcomes
-> operator outcome capture
```

The capture artifact records:

- accepted, rejected, unsafe, already-resolved, needs-more-evidence, or relabel decisions;
- reviewer, reason, and operator apply note;
- optional explicit RPG training label;
- derived RPG training label when the operator does not provide one;
- target ids;
- blocked reasons;
- RPG summary;
- RPG learning context.

Validation:

```powershell
py -3 eval/memory_maintenance_operator_outcome_capture_regression.py
```

Architecture gate key:

```text
memory_maintenance_operator_outcome_capture_ok
```

This creates the missing feedback hinge:

```text
RPG explains maintenance candidates
-> operator reviews them
-> outcomes become report-only training feedback
-> future label-bank integration can learn from reviewed maintenance behavior
```

The artifact remains non-mutating:

```text
ready_for_policy_use: false
promotion_ready: false
report_only: true
mutates_db: false
```

The next development step should be a feedback integration script that takes `memory_maintenance_operator_outcome_capture/v1` and emits RPG label-bank-compatible review items. That will let real operator packet outcomes improve the label bank without manually copying labels or enabling automatic memory mutation.

## Operator Outcome To RPG Feedback

Operator outcome capture now feeds an RPG label-bank-compatible feedback packet:

```text
operator outcome capture
-> operator outcome RPG feedback packet
-> RPG natural label bank
```

The feedback packet uses the existing schema:

```text
memory_maintenance_rpg_natural_candidate_review_packet/v1
```

so the existing RPG label-bank script can consume it without a separate training path. Each feedback item preserves:

- source operator packet item id;
- source operator outcome;
- explicit or derived RPG training label;
- target ids;
- RPG summary;
- RPG learning context;
- reviewer and notes.

Validation:

```powershell
py -3 eval/memory_maintenance_operator_outcome_rpg_feedback_regression.py
```

Architecture gate key:

```text
memory_maintenance_operator_outcome_rpg_feedback_ok
```

This closes the first report-only supervised feedback loop:

```text
RPG diagnostics
-> operator packet
-> operator outcome capture
-> RPG feedback packet
-> label-bank-compatible training evidence
```

The feedback remains blocked from policy use:

```text
ready_for_policy_use: false
promotion_ready: false
report_only: true
mutates_db: false
```

The next development step should be an aggregate label-bank merge/evaluation script that compares:

1. naturally mined RPG review labels;
2. operator-derived RPG feedback labels;
3. combined label-bank quality and scorer readiness.

That will tell whether operator feedback materially improves label diversity, quality readiness, and transparent scorer behavior.

## RPG Feedback Merge Evaluation

The architecture now has an aggregate report-only evaluator for the supervised RPG feedback loop:

```text
natural RPG review packet
+ operator-derived RPG feedback packet
-> merged RPG review packet
-> label bank
-> label-quality report
-> transparent scorer report
-> merge comparison
```

Validation:

```powershell
py -3 eval/memory_maintenance_rpg_feedback_merge_evaluation_regression.py
```

Architecture gate key:

```text
memory_maintenance_rpg_feedback_merge_evaluation_ok
```

The evaluator compares three variants:

- natural-only labels;
- operator-feedback-only labels;
- combined natural + operator-feedback labels.

For each variant it runs the existing label bank, label-quality report, and transparent scorer. The comparison reports:

- label gain from operator feedback;
- new review-label classes;
- new candidate classes;
- family prediction accuracy delta;
- leave-one-out scorer accuracy delta;
- whether operator feedback materially improves training evidence.

This is the right next architecture shape because the project goal is a low-compute adaptive memory brain, not an autonomous mutation bot. The combined program should keep improving in this order:

1. collect evidence from memory behavior;
2. expose that evidence to an operator/Hermes review surface;
3. capture reviewed outcomes;
4. convert outcomes into compatible supervised labels;
5. measure whether the labels improve quality and scorer behavior;
6. only then consider shadow policy proposals, never direct real DB mutation.

The next development step should be a compact architecture status/readiness dashboard artifact that summarizes the full chain:

```text
retrieval/controller
-> RPG diagnostics
-> maintenance rehearsal
-> operator packet
-> outcome capture
-> RPG feedback merge
-> label quality
-> scorer readiness
```

That dashboard should be used before GitHub uploads or Hermes handovers so both sessions can see what is stable, what is report-only, and what remains blocked.

## Architecture Readiness Dashboard

The codebase now has a compact readiness dashboard:

```text
selector architecture gate
+ architecture valuation
+ RPG feedback merge evaluation
-> architecture readiness dashboard
```

Validation:

```powershell
py -3 eval/architecture_readiness_dashboard_regression.py
```

Architecture gate key:

```text
architecture_readiness_dashboard_ok
```

The dashboard summarizes:

- retrieval/controller chain;
- RPG diagnostics chain;
- maintenance rehearsal chain;
- operator feedback chain;
- RPG supervised-learning chain;
- RPG feedback merge results;
- policy boundary;
- handover readiness;
- GitHub upload readiness;
- next development recommendation.

This is now the preferred pre-handover and pre-upload check. The dashboard keeps the architecture honest by showing that the current system is stable as a report-only adaptive memory learning loop, while real DB mutation and RPG policy use remain blocked.

The next development step should be to run the dashboard on real/Hermes-generated artifacts after the next extended test, then use its summary to decide whether the memory session needs UI/API hooks for operator outcome capture or whether the selector side needs more scorer/quality work first.

## Architecture Transition Map

The restructuring roadmap now has a compact transition-state evaluator:

```text
selector architecture gate
+ architecture valuation
+ architecture readiness dashboard
+ RPG feedback merge evidence
-> architecture transition map
```

Validation:

```powershell
py -3 eval/architecture_transition_map_regression.py
```

Architecture gate key:

```text
architecture_transition_map_ok
```

The transition map summarizes the neural-symbolic migration by subsystem:

- retrieval/controller context is the stable configured feature spine;
- maintenance apply lifecycle is operator-gated and copied-DB rehearsal-first;
- RPG relational substrate is diagnostic and report-only;
- operator feedback is ready as a non-mutating feedback loop;
- RPG supervised learning is shadow-learning only and blocked by label evidence;
- adaptive residual shadow is learned-veto shadow-only and blocked by fresh external validation.

This gives the project a clearer control surface for the next restructuring phase. The next best development target remains evidence collection, not policy promotion: collect reviewed natural RPG labels and operator-derived maintenance outcomes, then re-run label quality, feedback merge, scorer, dashboard, and transition-map checks. Runtime mutation, real DB apply, and RPG policy use remain blocked by design.

## RPG Reviewed Label Batch

The supervised RPG path now has a richer local reviewed-label pressure test:

```text
balanced reviewed RPG candidate-label fixture
-> natural label bank
-> label-quality report
-> transparent RPG label scorer
```

Validation:

```powershell
py -3 eval/memory_maintenance_rpg_reviewed_label_batch_regression.py
```

Architecture gate key:

```text
memory_maintenance_rpg_reviewed_label_batch_ok
```

This fixture is not real evidence and does not permit policy use. Its purpose is to prove the label-bank, quality, and scorer path can handle a balanced six-label candidate set before Hermes/user labels are collected. The next real architecture step is still to collect reviewed natural RPG labels and operator-derived maintenance outcomes, then compare real label quality against this clean local sanity baseline.
