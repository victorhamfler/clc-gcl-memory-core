# CLC-GCL Memory Core

Experimental AI agent memory core based on CLC, CSD, and G-CL ideas.

The program stores text memories as embedding-backed nodes, assigns them to symbolic domains, tracks source files, applies novelty and contradiction diagnostics, and retrieves memories with domain/source-aware ranking. The active baseline database is `memory_experiment_180_best.db`.

## Current Baseline

- Embedding backend: WSL `llama_cpp`
- Model: `embeddinggemma-300M-Q8_0.gguf`
- Vector dimension: `768`
- Active database: `memory_experiment_180_best.db`
- HTTP API default: `http://127.0.0.1:8765`

For the full agent-facing operating guide, see [docs/AGENT_USER_MANUAL.md](docs/AGENT_USER_MANUAL.md).

## Quick Commands

```powershell
py main.py stats
py retrieve.py --top-k 3 "geometry controller effective dimension curvature regime"
py eval/query_eval.py
py eval/feedback_ranking_smoke.py
py eval/reliability_ranking_smoke.py
py eval/supersession_ranking_smoke.py
py eval/mechanism_diagnostics.py
py eval/mechanism_ablation_eval.py
py eval/feedback_impact_experiment.py
py eval/consolidation_safety_smoke.py
py eval/summary_retrieval_eval.py
py eval/summary_answer_quality_eval.py
py eval/subtle_contradiction_eval.py
py eval/clc_threshold_calibration.py
py eval/mechanism_component_eval.py
py eval/memory_maintenance_eval.py
py eval/maintenance_impact_eval.py
py eval/maintenance_multi_case_eval.py
py eval/memory_training_run.py --fast-hash
py eval/memory_training_run_smoke.py
py eval/retrieval_weight_optimization.py
py eval/retrieval_weight_optimization_smoke.py
py eval/resolver_conflict_classification.py
py eval/stale_companion_context_smoke.py
py eval/long_run_drift_eval.py
py eval/contradiction_precision_eval.py
py eval/domain_contamination_eval.py
py eval/answer_specificity_eval.py
py eval/ask_smoke.py
py eval/answer_quality_eval.py
py eval/session_smoke.py
py eval/session_context_smoke.py
py eval/session_topic_filter_smoke.py
py eval/teach_correct_smoke.py
py eval/chat_smoke.py
py eval/agent_corpus_experiment.py
py chat.py --agent-id agent_alpha
py serve.py --host 127.0.0.1 --port 8765
```

## API Endpoints

- `GET /health`
- `GET /stats`
- `POST /ingest`
- `POST /ingest_batch`
- `POST /teach`
- `POST /correct`
- `POST /retrieve`
- `POST /ask`
- `POST /session`
- `POST /sessions`
- `POST /session_history`
- `POST /feedback`
- `POST /consolidation_plan`
- `POST /consolidate`
- `POST /consolidation_sources`
- `POST /memory_review`
- `POST /memory_weak` (`include_resolved`, `resolved_only`)
- `POST /memory_improve`

Example:

```powershell
$body = @{ query = "what can the geometry controller contribute to the AI memory program"; top_k = 3 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/retrieve" -Method Post -ContentType "application/json" -Body $body
```

Ask for an extractive answer with cited memory evidence:

```powershell
$body = @{ query = "can the assistant push to GitHub automatically"; top_k = 4 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ask" -Method Post -ContentType "application/json" -Body $body
```

Continue a session:

```powershell
$body = @{ query = "what should I remember next"; agent_id = "agent_alpha"; session_id = "sess_example" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ask" -Method Post -ContentType "application/json" -Body $body
```

When `session_id` is supplied, `/ask` uses topic-filtered recent session turns as retrieval context. This lets follow-up questions such as "what about that?" inherit the previous topic and evidence without dragging every recent topic into the retrieval query.

Teach or correct memory:

```powershell
$teach = @{ text = "Remember: the agent should keep API evidence ids visible."; agent_id = "agent_alpha" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/teach" -Method Post -ContentType "application/json" -Body $teach

$correct = @{ correction = "The assistant must not push to GitHub automatically."; target_query = "GitHub push policy"; agent_id = "agent_alpha" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/correct" -Method Post -ContentType "application/json" -Body $correct
```

Store retrieval feedback:

```powershell
py feedback.py mem_example useful --query "example query" --rank 1
```

## Memory Chat

`chat.py` is a local agent-facing memory assistant loop over the same ask, teach, and correct workflows used by the API.

```powershell
py chat.py --agent-id agent_alpha
```

Useful commands inside the loop:

```text
/teach <text>       store durable knowledge
/ask <question>     ask memory and show evidence
/correct <text>     store a correction linked to the last evidence
/feedback <label>   train last evidence; optional target: number, memory id, all
/sources            show evidence, source context, and superseded context
/why                show retrieval scoring details for the last answer
/consolidate plan   preview safe summary groups
/consolidate create create summary memories; options: min=4 max=8 groups=1
/memory review      inspect weak memories, domain flags, and recommendations
/memory weak        list weak memory candidates
/memory resolved    list repaired weak memories
/memory improve     plan or store a clarifying update for a memory
/history            show recent session turns
/new                start a new session
/quit               exit
```

Manual feedback session:

```powershell
py eval/interactive_retrieval_test.py --top-k 3
```

Stored feedback is used as a bounded reranking signal. Useful and excellent results receive a small boost, while wrong, stale, wrong-domain, or missing-source results are downranked. Feedback also contributes small source/domain reliability signals that can help fresh memories from trusted sources rank better. Retrieval also includes a supersession signal: when versioned sources such as `agent_memory_v1` and `agent_memory_v2` are both present, current/correction queries prefer the newer corrected source while preserving older memories as historical context. `/ask` responses keep primary evidence focused, then expose extra `source_context` for additional relevant files and `stale_context` for superseded relation-linked memories.

Retrieval ranking weights live in `config.yaml` under `retrieval_weights`. The current profile was selected with `py eval/retrieval_weight_optimization.py` and emphasizes source, feedback, supersession, manifest relation, and consolidation-summary signals over raw vector similarity. CLC controller thresholds live under `thresholds`; `py eval/clc_threshold_calibration.py` compares the configured profile against nearby alternatives.

Consolidation is non-destructive. `/consolidate create` and `POST /consolidate` create a new embedded summary memory and connect it to originals with `summarizes` relations. Original memories remain available as evidence, and `POST /consolidation_sources` or `/consolidate sources <summary-id>` can show the source memories behind a summary.

The synthetic agent corpus uses `test_corpora/agent_memory_manifest.json` to make this explicit. The manifest declares source-level `supersedes`, `corrects`, and `updates` relations; the experiment expands those into memory-to-memory relation rows that retrieval can use directly.

## Experiment Workflow

Build or rebuild an experiment DB:

```powershell
py eval/corpus_experiment.py --max-words 180 --overlap-words 30 --db-path memory_experiment_180_best.db --reset
```

Promote a validated DB into `config.yaml`:

```powershell
py promote_db.py memory_experiment_180_best.db
```

## Notes

This repo keeps only the current best baseline database in Git. Older scratch databases, logs, caches, and local runtime files are ignored.
