# Hermes Adaptive Behavior Shadow Real-Log Handover

Date: 2026-05-25

## Purpose

Run real working-condition tests for the new runtime adaptive behavior shadow surface.

The selector-side architecture now exposes `adaptive_behavior_shadow/v1` on `POST /ask` when explicitly requested. It is report-only. It must not change answer text, selected evidence, selector policy, memory rows, runtime config, or learned artifacts.

Your job is to pull the latest GitHub version, run the required gates, then use the memory program in a continued work session while logging adaptive behavior shadow advisories and linked feedback. The resulting logs and report will be used by Codex to build the next calibration/replay artifact.

## Repository

```bash
git clone https://github.com/victorhamfler/clc-gcl-memory-core.git
cd clc-gcl-memory-core
```

If you already have the repo:

```bash
git pull origin main
```

## Local Model Requirement

The Windows/Codex config expects the local Gemma embedding model. On WSL, confirm the model exists:

```bash
test -f /home/victo/models/embeddinggemma-300M-Q8_0.gguf && echo "Gemma model present"
```

If the model is not available in your environment, report that clearly and use the hash fallback only for non-Gemma smoke tests. Do not claim Gemma validation if the `wsl_llama_cpp` backend was not used.

## Required Baseline Tests

Run these before the real-log work:

```bash
python eval/adaptive_behavior_shadow_runtime_regression.py
python eval/adaptive_context_gemma_shadow_regression.py
python eval/canonical_ogcf_shadow_coverage_regression.py
python eval/selector_architecture_gate.py
```

Expected current gate summary:

```json
{
  "retrieval_signal_gate_ok": true,
  "evidence_state_gate_ok": true,
  "shadow_coverage_guard_ok": true,
  "gemma_shadow_regression_ok": true,
  "adaptive_behavior_shadow_runtime_ok": true
}
```

If any baseline fails, stop and report the failing command, stdout/stderr, and the generated report path.

## Runtime Shadow Request Contract

For each real `POST /ask` request that should collect adaptive behavior shadow data, include:

```json
{
  "include_adaptive_behavior_shadow": true,
  "log_adaptive_behavior_shadow": true
}
```

Use `include_resolver_shadow: true` too when possible, because resolver-shadow actions help interpret adaptive behavior advisories:

```json
{
  "query": "example question",
  "namespace": "agent:hermes-adaptive-shadow-real-log",
  "include_global": false,
  "top_k": 8,
  "include_selector_snapshot": true,
  "include_resolver_shadow": true,
  "include_adaptive_behavior_shadow": true,
  "log_adaptive_behavior_shadow": true
}
```

The response should include:

```text
adaptive_behavior_shadow.schema == adaptive_behavior_shadow/v1
adaptive_behavior_shadow.report_only == true
adaptive_behavior_shadow.mutates_answer == false
adaptive_behavior_shadow.mutates_selector_policy == false
adaptive_behavior_shadow.mutates_memory == false
adaptive_behavior_shadow.mutates_config == false
```

## Real-Log Test Design

Use one continuous namespace for the main run:

```text
agent:hermes-adaptive-shadow-real-log
```

Also optionally use daily sub-namespaces if running more than one day:

```text
agent:hermes-adaptive-shadow-real-log:day1
agent:hermes-adaptive-shadow-real-log:day2
```

Run at least 40 ask/feedback cycles if possible. Minimum useful run: 20 ask/feedback cycles.

Include these scenario families:

1. Supported evidence
   - Teach clear facts or rules.
   - Ask direct questions where selected evidence should support the answer.
   - Feedback labels: `answer_correct`, `answer_good_citation`, `useful`, `good`.

2. Missing support
   - Ask questions not supported by memory.
   - Good behavior is refusal or uncertainty.
   - Feedback labels: `answer_missing_support` for bad unsupported answers, `answer_correct` if it correctly refuses.

3. Stale/current conflict
   - Teach an old fact, then a correction/current fact.
   - Ask current and historical versions.
   - Feedback labels: `answer_stale`, `answer_conflict_not_disclosed`, `stale`, `useful`.

4. Wrong scope
   - Teach nearby but different facts, then ask a boundary question.
   - Example: calendar approval versus GitHub upload approval.
   - Feedback labels: `answer_wrong_scope`, `wrong_domain`.

5. OGCF bridge warning useful
   - Ask cross-domain synthesis questions where bridge-risk diagnostics should matter.
   - If your harness can pass non-empty `ogcf_meta`, do so.
   - Feedback labels: `answer_bridge_warning_useful`, `bridge_relevant`, `ogcf_geometry`.

6. OGCF bridge warning noise
   - Ask ordinary fact questions that contain bridge-like words but should not trigger bridge-warning behavior.
   - Feedback labels: `answer_bridge_warning_noise`, `ogcf_false_positive`, `ordinary_lookup`.

## Feedback Linking Requirement

Every feedback event must link to the ask operation id.

For answer-level feedback:

```json
{
  "feedback_scope": "answer",
  "operation_id": "<ask_operation_id>",
  "label": "answer_correct",
  "selected_memory_ids": ["<selected ids from ask evidence>"],
  "notes": "why this answer was correct or wrong"
}
```

For memory-level feedback:

```json
{
  "operation_id": "<ask_operation_id>",
  "memory_id": "<selected memory id>",
  "label": "useful",
  "rank": 1,
  "retrieval_score": 0.0,
  "notes": "why this memory was useful, stale, wrong-domain, bridge-relevant, etc."
}
```

Do not write unlinked feedback. Unlinked feedback cannot calibrate the shadow controller.

## What To Collect

Save the following artifacts in your experiments folder:

- the full outcome log JSONL;
- a compact report markdown;
- any copied DB used for the test, if safe and not too large;
- command outputs for baseline tests;
- a summary JSON with counts.

The final report should include:

- commit hash tested;
- Python/WSL environment used;
- whether Gemma backend was used;
- namespace(s);
- number of teach/correct/ask/feedback operations;
- number of ask events with `adaptive_behavior_shadow/v1`;
- advisory count distribution;
- behavior-family count distribution;
- label count distribution;
- linked feedback count;
- skipped/unlinked feedback count;
- examples where the shadow advisory looked useful;
- examples where the shadow advisory looked wrong or uncertain;
- whether any answer text, evidence, selector policy, memory rows, or config changed because of the shadow surface.

## Safety Rules

- Do not promote adaptive behavior shadow to runtime action.
- Do not edit `config.yaml` to enable shadow globally unless explicitly instructed.
- Do not mutate memory rows based on adaptive shadow advisories.
- Do not delete duplicate memories during this test.
- Keep the run report-only and feedback-linked.

## Expected Next Use By Codex

Codex will use your real logs to build a calibration/replay artifact that compares:

```text
adaptive_behavior_shadow advisories
vs
linked answer-level feedback
vs
linked memory-level feedback
vs
adaptive_memory_context diagnostics
```

The goal is to decide whether the runtime adaptive shadow is only useful for logging, or whether any behavior family is strong enough to become a guarded future controller candidate.
