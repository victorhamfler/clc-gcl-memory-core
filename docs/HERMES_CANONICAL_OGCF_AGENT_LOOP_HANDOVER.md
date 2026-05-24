# Hermes Canonical + OGCF Agent-Loop Handover

Date: 2026-05-24

## Purpose

This handover is for the Hermes agent/orchestrator.

The selector architecture now has a combined canonical memory + OGCF checkpoint. The next task is to test it under a longer, more realistic agent-loop condition using Hermes working logs and memory behavior.

The goal is to find whether the current architecture improves real answer quality and controller safety:

- canonical memory should improve exact-claim recall and preserve support/provenance;
- stale/current corrections should answer from current evidence while preserving stale context;
- duplicate pressure should become visible as metadata, not silently deleted;
- OGCF should add bridge/composition risk warnings over retrieval contexts;
- the selector should receive useful diagnostics without overreacting to clean supported claims.

Do not mutate production memory databases during this test. Use copied databases or temporary databases. Produce reports only.

## Repository

Repository:

```text
https://github.com/victorhamfler/clc-gcl-memory-core.git
```

Branch:

```text
main
```

Project folder after clone/pull:

```text
clc_gcl_memory_core
```

If this exact version has not been uploaded to GitHub yet, ask Victor to upload/push first, or use the local project copy he provides.

## New Files To Verify

The version you test should include:

```text
core/canonical_memory.py
core/ogcf_geometry.py
core/ogcf_signals.py
core/ogcf_selector.py
core/ogcf_api.py
eval/canonical_ogcf_combined_eval.py
eval/canonical_ogcf_answer_quality_eval.py
```

It should also include canonical memory configuration in `config.yaml`:

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

## Required Baseline Commands

From the `clc_gcl_memory_core` folder, run the existing regression checkpoints first.

On Windows PowerShell:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_combined_eval.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_ogcf_answer_quality_eval.py
..\.venv-torch\Scripts\python.exe .\eval\clc_policy_feature_signal_regression.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_selector_features_regression.py
..\.venv-torch\Scripts\python.exe .\eval\canonical_lexical_backfill_regression.py
```

On WSL/Linux, use the available Python interpreter:

```bash
python eval/canonical_ogcf_combined_eval.py
python eval/canonical_ogcf_answer_quality_eval.py
python eval/clc_policy_feature_signal_regression.py
python eval/canonical_selector_features_regression.py
python eval/canonical_lexical_backfill_regression.py
```

Expected result: all scripts should report `"ok": true` or `Passed: **True**`.

## Existing Output Files

These evals write reports to the parent `experiments` folder:

```text
../experiments/canonical_ogcf_combined_eval_results.json
../experiments/canonical_ogcf_combined_eval_report.md
../experiments/canonical_ogcf_answer_quality_eval_results.json
../experiments/canonical_ogcf_answer_quality_eval_report.md
```

Copy or reference these in your final report.

## Main Hermes Test

After the baseline commands pass, run a longer agent-loop benchmark using Hermes' own working harness.

Use a copied test DB or a fresh test DB. Do not run destructive dedup or maintenance on a production DB.

The benchmark should compare four modes:

```text
1. canonical off, OGCF off
2. canonical on, OGCF off
3. canonical off, OGCF on
4. canonical on, OGCF on
```

If Hermes cannot switch all four modes inside one run, run separate passes and keep the test prompts, seed memories, and DB copy identical.

## Required Test Cases

Use at least these case families.

### 1. Exact-Miss Claim Recall

Create or find a case where vector retrieval can miss an exact textual claim because many vector-near distractors are present.

Expected behavior:

- canonical off may answer from a distractor;
- canonical on should recover the exact canonical keeper;
- answer evidence should expose `canonical_support_count`;
- duplicate non-keeper rows should not dominate top evidence.

Metrics:

```text
exact_claim_answer_correct
target_memory_rank
canonical_support_count
canonical_is_keeper
duplicate_pressure
answer_text
evidence_memory_ids
```

### 2. Current vs Stale Correction

Use a correction chain like:

```text
old: Victor currently prefers espresso.
current: Victor currently prefers sparkling water, not espresso.
```

Expected behavior:

- answer should use the current/authoritative memory;
- stale evidence should be preserved in stale context or diagnostics;
- canonical support must not create false confidence for stale/current conflict.

Metrics:

```text
answer_uses_current_claim
stale_claim_avoided_in_answer
stale_context_present
canonical_confidence_credit
stale_current_conflict
selector_policy
```

### 3. Duplicate-Heavy Support

Use repeated copies of the same valid claim across multiple sources/namespaces.

Expected behavior:

- canonical should preserve support/provenance;
- exact duplicates should be represented as support, not blindly deleted;
- duplicate clutter should be visible through canonical diagnostics.

Metrics:

```text
support_count
duplicate_count
namespace_count
source_count
canonical_keeper_memory_id
canonical_duplicate_pressure
top_evidence_unique_text_count
```

### 4. Semantic Conflict / Update

Use near-duplicate claims that are not safe exact duplicates, for example:

```text
Victor avoids all caffeine.
Victor likes espresso in the morning.
Victor likes green tea in the afternoon.
```

Expected behavior:

- semantic conflict/update should not be merged as clean duplicate support;
- answer should surface conflict or choose the current authoritative claim if one exists;
- report should show whether canonical/OGCF helps detect ambiguity.

Metrics:

```text
conflict_detected
answer_confidence
disputed_count
live_conflict_count
semantic_conflict_or_update_count
current_claim_selected
```

### 5. OGCF Bridge Risk

Use retrieval contexts where many memories bridge unrelated domains or where prior OGCF tests showed bridge-heavy regions.

Expected behavior:

- OGCF on should increase bridge/composition risk diagnostics;
- OGCF should not replace answer evidence;
- combined canonical + OGCF should keep canonical support while still warning about bridge risk.

Metrics:

```text
ogcf_bridge_overload_score
ogcf_max_interaction_z
ogcf_affected_memory_ratio
ogcf_memory_bad_rate_delta
ogcf_csd_ratio_delta
selector_policy_before_ogcf
selector_policy_after_ogcf
```

## Suggested Run Duration

Run at least one short controlled pass first:

```text
20-50 asks
5-10 corrections
5-10 duplicate/support insertions
at least 2 bridge-risk retrieval contexts
```

If stable, continue with a longer pass:

```text
1-3 days of normal Hermes work, shadow-logging canonical/OGCF diagnostics
```

For the longer pass, keep the architecture in report/shadow mode. Do not automatically promote new learned rules or delete memory rows.

## Required JSON Report

Write a JSON report to:

```text
../experiments/hermes_canonical_ogcf_agent_loop_results.json
```

If using WSL, write to:

```text
/home/victo/experiments_hermes/hermes_canonical_ogcf_agent_loop_results.json
```

Use this top-level shape:

```json
{
  "ok": true,
  "repository_commit": "commit sha or unknown",
  "runtime": {
    "os": "windows/wsl/linux",
    "python": "version",
    "embedding_backend": "hash/gemma/llama_cpp/etc",
    "db_path": "copied or temporary db path"
  },
  "baseline_evals": {
    "canonical_ogcf_combined_eval": true,
    "canonical_ogcf_answer_quality_eval": true,
    "clc_policy_feature_signal_regression": true,
    "canonical_selector_features_regression": true,
    "canonical_lexical_backfill_regression": true
  },
  "mode_summary": {
    "base": {},
    "canonical": {},
    "ogcf": {},
    "combined": {}
  },
  "cases": [
    {
      "case_id": "exact_miss_001",
      "case_family": "exact_miss",
      "mode": "combined",
      "query": "question text",
      "answer": "answer text",
      "expected_answer_terms": ["term"],
      "answer_correct": true,
      "evidence_memory_ids": ["mem_id"],
      "top_memory_id": "mem_id",
      "canonical": {
        "support_count": 3,
        "duplicate_count": 2,
        "is_keeper": true,
        "duplicate_pressure": 0.0,
        "confidence_credit": 0.0
      },
      "ogcf": {
        "bridge_overload_score": 0.0,
        "max_interaction_z": 0.0,
        "affected_memory_ratio": 0.0
      },
      "selector": {
        "policy_before_ogcf": "policy",
        "policy_after_ogcf": "policy",
        "memory_bad_rate": 0.0,
        "csd_ratio": 0.0,
        "probe_drop": 0.0
      },
      "notes": "short explanation"
    }
  ],
  "failures": [],
  "recommendations": []
}
```

## Required Markdown Report

Write a human-readable report to:

```text
../experiments/hermes_canonical_ogcf_agent_loop_report.md
```

If using WSL:

```text
/home/victo/experiments_hermes/hermes_canonical_ogcf_agent_loop_report.md
```

The Markdown report should include:

- commands run;
- commit/version tested;
- DB copy or temp DB used;
- baseline eval pass/fail table;
- four-mode comparison summary;
- per-case findings;
- examples where canonical helped;
- examples where OGCF helped;
- examples where either method hurt or added noise;
- whether any production code change is recommended;
- next recommended development steps.

## Important Safety Rules

- Do not delete, merge, or deprecate production memories during this test.
- Do not auto-promote candidate terms, semantic clusters, or learned controller features.
- Do not overwrite the main production DB.
- If testing dedup, use a copied DB and report what would be changed.
- Preserve exact duplicate support/provenance in reports.
- Treat semantic near-duplicates as review-first unless clearly proven safe.

## What To Tell Codex Back

When finished, give Victor/Codex:

```text
1. Path to JSON report.
2. Path to Markdown report.
3. Whether all baseline evals passed.
4. Whether combined mode beat base mode.
5. Any cases where canonical or OGCF made behavior worse.
6. Any recommended code changes.
```

The most useful result is not just "passed" or "failed". We need to know where the architecture is improving real agent memory behavior and where the controller still needs better learned/adaptive mechanisms.
