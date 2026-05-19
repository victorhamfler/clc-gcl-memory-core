# Hermes Handover: Multi-Day Architecture Test

## Mission

Run the current CLC/CSD/G-CL memory architecture under continued working conditions for several days, then return a report that helps Codex decide the next development stage.

This is not a single smoke test. The goal is to find how the architecture behaves when an agent repeatedly teaches, corrects, retrieves, asks, explains selector decisions, and works across topic changes over time.

## Current Architecture To Test

The current version includes:

- learned CLC selector with guardrails,
- retrieval-derived selector features,
- retrieval-aware policy guards,
- irrelevant stale-cluster detection,
- corrected source-version grouping by source file,
- pressure and randomized eval suites for stale/current/clutter behavior.

The most important claim to test is:

> The architecture can protect clean memory, detect real stale/current conflict, and avoid escalating query-irrelevant stale clutter during continued agent work.

## Setup

Pull the latest GitHub version:

```bash
git clone https://github.com/victorhamfler/clc-gcl-memory-core.git
cd clc-gcl-memory-core
```

If the repo already exists:

```bash
cd clc-gcl-memory-core
git pull origin main
```

Use the available Python environment. If needed, create one and install the project dependencies already used by this repository. Do not commit generated databases, logs, caches, or reports unless Victor explicitly asks.

## Day 0 Baseline Tests

Run these first and save all outputs:

```bash
python eval/selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8
python eval/selector_retrieval_guard_pressure_eval.py --embedding-backend hash --top-k 10
python eval/selector_retrieval_guard_randomized_eval.py --embedding-backend hash --cases 32 --seed 20260519 --top-k 10
python eval/selector_retrieval_feature_eval.py
python eval/selector_live_retrieval_pipeline_eval.py
python eval/selector_explain_endpoint_eval.py
python eval/guarded_continual_live_endpoint_eval.py
```

If the configured Gemma embedding backend is available:

```bash
python eval/selector_retrieval_calibration_eval.py --embedding-backend config --top-k 8
python eval/selector_retrieval_guard_pressure_eval.py --embedding-backend config --top-k 10
python eval/selector_retrieval_guard_randomized_eval.py --embedding-backend config --cases 32 --seed 20260519 --top-k 10
```

Expected current results:

```text
selector_retrieval_calibration_eval hash: 6/6
selector_retrieval_guard_pressure_eval hash: 6/6
selector_retrieval_guard_randomized_eval hash: 32/32
selector_retrieval_calibration_eval config: 6/6
selector_retrieval_guard_pressure_eval config: 6/6
selector_retrieval_guard_randomized_eval config: 32/32
```

If any baseline fails, stop and report the failing JSON/Markdown plus the console output.

## Start A Long-Run Test Server

Use a dedicated database so the test does not contaminate Victor's normal local DB.

Example:

```bash
python serve.py --host 127.0.0.1 --port 8765 --db-path ../experiments/hermes_long_run_memory.db
```

Use the HTTP API for repeated work:

- `POST /teach`
- `POST /correct`
- `POST /ask`
- `POST /retrieve`
- `POST /selector_decide`
- `POST /selector_explain`
- `GET /stats`
- `GET /memory_usage`
- `GET /health`

## Multi-Day Working Protocol

Run this for at least 3 days. Five days is better if practical.

Each day should contain at least three work sessions:

- morning session,
- middle session,
- end-of-day session.

Each session should perform real agent-like operations. Use Hermes' own LLM/orchestrator harness to decide phrasing, but keep the task categories below balanced.

### Session Task Mix

For every session, run:

1. Clean teaches:
   - Add 3 to 5 new memories with no contradictions.
   - Include project facts, user preferences, tool rules, and CSD/G-CL architecture notes.

2. Mild compatible updates:
   - Add 2 memories that extend previous memories without correcting them.
   - Example: "Victor values source clarity" then later "Victor also values concise summaries with citations."

3. Direct corrections:
   - Correct at least 2 memories using `/correct` with explicit `target_memory_ids`.
   - Query the corrected topic afterward.

4. Correction chains:
   - Create one multi-step correction chain across the day.
   - Example: v1 preference -> v2 correction -> v3 correction.

5. Topic switches:
   - Ask across unrelated topics after corrections.
   - Make sure stale memories from one topic do not affect answers in another topic.

6. Selector explanation probes:
   - For at least 5 questions per session, call `/selector_explain` using the same query/namespace.
   - Save decision, base decision, retrieval guard, diagnostics, nearest samples, and retrieval rows.

7. Retrieval inspections:
   - Call `/retrieve` for each important query.
   - Save top rows, scores, authority states, supersession scores, text-match scores, and source paths.

## Required Namespaces

Use separate namespaces so results can be compared:

```text
hermes_longrun_day1
hermes_longrun_day2
hermes_longrun_day3
hermes_longrun_day4
hermes_longrun_day5
```

Also run one cross-day namespace:

```text
hermes_longrun_continuous
```

The daily namespaces test isolation. The continuous namespace tests true continued learning.

## What To Measure

Track these metrics in JSONL or JSON:

- total teaches,
- total corrections,
- total asks,
- total retrieves,
- total selector explanations,
- answer correctness by Hermes judgment,
- stale evidence appearing in clean queries,
- stale evidence dominating clean queries,
- correct current evidence missing after correction,
- retrieval guard applied count by reason,
- false protect cases,
- false aggressive cases,
- cases where `hard=true` but the query was clean,
- cases where `hard=false` but a true correction conflict existed,
- average top retrieval score,
- average stale score gap,
- number of source-version anomalies,
- latency per endpoint if available.

For each failure, save the full request and response.

## Failure Categories

Use these labels:

```text
answer_wrong_current_missing
answer_wrong_stale_dominates
selector_false_aggressive
selector_false_protect
hard_false_negative
hard_false_positive
retrieval_query_irrelevant_stale
retrieval_source_version_error
retrieval_topical_miss
session_topic_leak
namespace_leak
llm_judgment_uncertain
```

## Daily Report Format

Write one daily Markdown report:

```text
../experiments/hermes_long_run_day1_report.md
../experiments/hermes_long_run_day2_report.md
../experiments/hermes_long_run_day3_report.md
```

Also write machine-readable details:

```text
../experiments/hermes_long_run_day1_events.jsonl
../experiments/hermes_long_run_day2_events.jsonl
../experiments/hermes_long_run_day3_events.jsonl
```

Each event should include:

```json
{
  "timestamp": "...",
  "day": 1,
  "session": "morning",
  "namespace": "hermes_longrun_day1",
  "operation": "ask|teach|correct|retrieve|selector_explain",
  "query": "...",
  "request": {},
  "response": {},
  "expected_behavior": "protect|aggressive|neutral",
  "hermes_judgment": "pass|fail|uncertain",
  "failure_category": "",
  "notes": ""
}
```

## Final Report Format

At the end, write:

```text
../experiments/hermes_long_run_final_report.md
../experiments/hermes_long_run_final_summary.json
```

The final report must answer:

1. Did the architecture remain stable over multiple days?
2. Did the retrieval-aware guard reduce false aggressive refreshes?
3. Did it ever protect when it should have refreshed?
4. Did source-version grouping remain correct by file?
5. Did clean topic switches stay clean?
6. Did the continuous namespace accumulate useful memory or become noisy?
7. Which exact failures are most important for Codex to fix next?
8. Which test should become a permanent eval script?

## Final Recommendation Section

End the report with a ranked list:

```text
1. Highest-priority architecture fix
2. Highest-priority retrieval/ranking fix
3. Highest-priority selector/training fix
4. Highest-priority evaluation improvement
5. Whether the architecture is ready for a larger real-agent application test
```

## Important Notes

- Do not judge success only by selector policy. Judge final answer behavior too.
- Keep all generated databases and logs outside Git tracking.
- If using the configured Gemma backend, record whether the model loaded through WSL/native config.
- If any endpoint fails, save server stdout/stderr and the failing request.
- If a failure seems caused by Hermes' LLM judgment rather than the memory architecture, mark it `llm_judgment_uncertain`.
