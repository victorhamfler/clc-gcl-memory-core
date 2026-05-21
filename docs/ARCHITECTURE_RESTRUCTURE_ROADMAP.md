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

## Immediate Next Step

Prepare a handover for the memory-program session after reviewing the remaining shared contracts.

The handover should focus on integration boundaries rather than asking the memory session to change selector internals:

- how to call the unified selector architecture gate;
- how outcome logs should supply linked `ask` and `feedback` events;
- which candidate artifact formats the selector side now accepts;
- what not to promote without a passing gate;
- which shared contracts should stay stable during the broader memory-program restructure.
