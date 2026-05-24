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
- Many thresholds and coefficients are hardcoded in code rather than described by configuration, calibration artifacts, or learned outcome models.

The system is still valuable, but new behavior is increasingly being added as local patches instead of clean mechanisms.

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
