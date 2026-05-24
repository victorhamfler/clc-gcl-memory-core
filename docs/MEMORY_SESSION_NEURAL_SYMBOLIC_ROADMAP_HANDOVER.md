# Memory Session Neural-Symbolic Roadmap Handover

Date: 2026-05-24

## Purpose

This handover is for the memory-program session. It explains how the memory side can advance alongside the selector session toward the shared roadmap goal:

```text
hardcoded heuristics -> configurable control surfaces -> mined candidate artifacts -> readiness gates -> semantic/learned controller features
```

The selector session should continue owning selector policy, retrieval-signal candidates, OGCF intent candidates, semantic candidate memory, and promotion gates. The memory-program session should continue owning storage behavior, learning endpoints, resolver/answer behavior, canonical provenance, feedback capture, and Hermes workflow integration.

The two sessions should stay separate for now, but coordinate through handover documents before shared contract changes or GitHub uploads.

## Current Selector-Side Direction

The selector roadmap is now centered on a neural-symbolic adaptive memory controller:

- symbolic contracts keep the system auditable and safe;
- configurable surfaces replace hardcoded rules;
- outcome logs propose new candidates;
- readiness gates decide whether candidates are mature;
- semantic clustering or a small local learned scorer later generalizes beyond exact terms;
- runtime behavior changes only after guard tests pass.

Recent selector-side pieces:

```text
core/retrieval_signals.py
core/evidence_states.py
core/ogcf_intent.py
eval/mine_ogcf_intent_candidates.py
eval/candidate_semantic_memory.py
eval/selector_candidate_pipeline_from_log.py
```

The latest OGCF candidate miner now filters generic workflow terms. It should receive real memory-session/Hermes outcome logs before any production config promotion.

## What The Memory Session Can Improve Next

### 1. Make Outcome Logs More Useful For Learning

The most important memory-side improvement is richer, consistent outcome logging. The selector can only become less hardcoded if the memory program logs enough evidence to train and validate controller behavior.

For every `ask`, `retrieve`, `selector_explain`, `answer`, `teach`, `correct`, and `feedback` event, preserve or add:

- `operation_id`;
- `linked_operation_id` for feedback;
- query text;
- namespace;
- selected answer text or answer summary;
- selected memory IDs;
- raw retrieved rows before answer selection;
- reranked retrieved rows after scoring;
- evidence state fields: current, stale, historical, disputed, summary;
- canonical fields: keeper ID, support count, duplicate count, source/namespace spread;
- OGCF fields when available: cluster count, affected ratio, effective affected ratio, loop count, interaction z-score, bridge-overload score;
- selector diagnostics when available: policy, action, confidence, memory_bad_rate, probe_drop, csd_ratio;
- feedback label and numeric rating;
- free-text reason when an agent or user can provide one.

This turns the memory program into the data engine for the neural-symbolic controller.

### 2. Add Real Feedback Labels During Normal Hermes Work

The controlled workflow proved the label loop works. The next step is to use these labels in real Hermes runs, not only synthetic fixtures.

Positive bridge labels:

```text
bridge_relevant
cross_domain_bridge
ogcf_bridge
```

Positive geometry labels:

```text
ogcf_geometry
bridge_geometry
loop_overload
```

Positive maintenance labels:

```text
memory_maintenance
dedup
duplicate
bridge_maintenance
```

Suppression labels:

```text
ogcf_false_positive
bridge_irrelevant
ordinary_lookup
ordinary_fact
unrelated_bridge
no_ogcf_pressure
```

Memory session should make these labels easy for Hermes to emit from real work. The goal is not to force every interaction into these labels; the goal is to produce enough clean examples for mining and holdout tests.

### 3. Convert Memory-Side Hardcoded Behavior To Config First

Before adding learned behavior, memory-side hardcoded logic should be moved to explicit config with defaults and regressions.

Best targets:

- resolver evidence ranking weights;
- answer confidence thresholds;
- stale/current conflict thresholds;
- correction-chain priority weights;
- source-version grouping rules;
- teach/correct ingestion thresholds;
- duplicate/canonicalization thresholds;
- semantic dedup review thresholds;
- answer snippet length and evidence-count limits;
- broad/generic note suppression rules if still present in resolver or pipeline code.

Each configurable surface should include:

- default config section;
- one regression proving config changes behavior;
- one report or config-view output showing active values.

This is Level 1 in the roadmap and should happen before Level 3 adaptive updates.

### 4. Extract Resolver And Evidence Modules

The selector side already started extracting signal/evidence surfaces. The memory session should now plan a conservative split of resolver responsibilities.

Suggested memory-side target modules:

```text
core/evidence_ranking.py
core/evidence_conflicts.py
core/answer_composer.py
core/answer_confidence.py
core/learning_precheck.py
```

The first extraction should preserve behavior exactly. Do not change answer logic and refactor at the same time.

Recommended first module:

```text
core/evidence_ranking.py
```

Reason: ranking weights are a natural place to move from hardcoded heuristics to configurable and later calibrated behavior.

### 5. Treat Dedup As Canonicalization, Not Deletion

The OGCF duplicate analysis showed that duplicate rows often do not add new text, but they can add evidence value:

- support count;
- provenance;
- namespace spread;
- first-seen and last-seen time;
- repeated confirmation from different workflows.

Memory session should avoid blind deletion as the default path. Exact duplicates should become canonical support metadata. Semantic duplicates should stay review-first because they may hide corrections or conflicts.

Memory-side improvements to consider:

- persistent canonical claim table or view;
- provenance table linking canonical claims to supporting memory rows;
- explicit `semantic_paraphrase`, `semantic_conflict`, and `semantic_update` relation types;
- dry-run maintenance candidate endpoint before mutation;
- review/report workflow for proposed merges.

### 6. Build A Real Holdout Set From Hermes Failures

The selector side has many generated regressions. The memory side can add the real development value by collecting holdout cases from normal Hermes use.

Holdout categories:

- personal preference corrections;
- project-memory updates;
- stale/current conflicts;
- source-version updates;
- multi-domain bridge questions;
- ordinary factual questions that should not trigger OGCF pressure;
- duplicate-heavy retrieval cases;
- near-topic distractors;
- tool-rule changes;
- multi-session continuity questions.

For each holdout item, store:

- query;
- expected answer behavior;
- expected memory IDs or forbidden stale IDs when known;
- expected selector behavior if relevant;
- reason why this became a holdout case.

These holdouts should be used by both sessions before promoting learned/adaptive behavior.

### 7. Add Answer-Level Feedback For Learned Resolver Development

The selector roadmap is not only about memory-operation policy. The memory program eventually needs adaptive answer behavior too.

Suggested labels:

```text
answer_correct
answer_stale
answer_wrong_scope
answer_missing_support
answer_overconfident
answer_good_citation
answer_bad_citation
answer_conflict_not_disclosed
answer_bridge_warning_useful
answer_bridge_warning_noise
```

These labels would allow a later resolver scorer to learn from real outcomes while keeping symbolic safety gates.

### 8. Make Hermes Agent-Loop Tests Emit Non-Empty OGCF Metadata

The last Hermes validation showed selector policy distribution was fixed, but OGCF did not move policy because the agent-loop test passed empty `ogcf_meta = {}`.

Memory session/Hermes should update the agent-loop benchmark so bridge-risk cases include real or simulated non-empty OGCF metadata:

- `bridge_overload_score`;
- `max_interaction_z`;
- `loop_count`;
- `risk_region_count`;
- `cluster_count`;
- `affected_memory_ratio`;
- `weighted_affected_memory_ratio`;
- `effective_affected_memory_ratio`.

This will test the combined architecture more honestly:

```text
canonical support/provenance + OGCF geometry pressure + selector policy
```

### 9. Prepare A Memory-Side Candidate Pipeline

The selector already has dry-run candidate artifacts. The memory session should mirror this pattern for memory/resolver behavior.

Possible artifact schemas:

```text
resolver_weight_candidates/v1
canonicalization_candidates/v1
answer_confidence_candidates/v1
learning_precheck_candidates/v1
```

Each should be report-only at first:

- no DB mutation;
- no config mutation;
- input logs listed;
- examples included;
- support counts included;
- known guard risks stated.

## Recommended Immediate Memory-Session Step

The best next memory-side development step is:

```text
Add a real-outcome logging and holdout-capture pass for Hermes runs, with answer-level labels and non-empty OGCF metadata.
```

This is more valuable than immediately changing resolver logic because it gives both sessions the data needed to replace hardcoded components safely.

Concrete implementation target:

1. Extend the memory-session/Hermes test harness to log enriched `ask`, `answer`, `selector_explain`, and `feedback` rows.
2. Add the answer-level labels listed above.
3. Add OGCF metadata for bridge-risk cases instead of `{}`.
4. Write a small report that summarizes:
   - number of linked feedback events;
   - number of answer-level feedback events;
   - number of OGCF-labeled events;
   - number of ordinary-fact suppression events;
   - number of holdout candidates captured.
5. Do not mutate runtime config or promote learned behavior yet.

## Suggested Validation Commands

Run the current shared safety checks after changes:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\outcome_logging_regression.py
..\.venv-torch\Scripts\python.exe .\eval\ogcf_intent_outcome_workflow.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_policy_distribution_regression.py
..\.venv-torch\Scripts\python.exe .\eval\selector_architecture_gate.py
```

If the memory session adds new memory-side tests, include them in the returned handover.

## Handover Back To Selector Session

Please return a handover with:

- files changed;
- exact validation commands and pass/fail results;
- sample enriched outcome rows or artifact paths;
- any new labels added;
- whether OGCF metadata is now non-empty in agent-loop bridge cases;
- whether any runtime DB mutation was introduced;
- any proposed candidate artifact schemas.

The selector session will then run the OGCF miner, readiness pipeline, and semantic candidate memory on the real logs.

