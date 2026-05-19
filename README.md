# CLC-GCL Memory Core

Experimental AI agent memory core based on CLC, CSD, and G-CL ideas.

The program stores text memories as embedding-backed nodes, assigns them to symbolic domains, tracks source files, applies novelty and contradiction diagnostics, and retrieves memories with domain/source-aware ranking. The active baseline database is `memory_experiment_180_best.db`.

## Current Baseline

- Embedding backend from Windows: `wsl_llama_cpp`
- Embedding backend from WSL/Hermes: `llama_cpp`
- Model: `embeddinggemma-300M-Q8_0.gguf`
- Vector dimension: `768`
- Active database: `memory_experiment_180_best.db`
- HTTP API default: `http://127.0.0.1:8765`

The committed config is Windows-first and uses `wsl_llama_cpp` to bridge into WSL. When the same code runs inside WSL/Hermes, it automatically switches that config to native `llama_cpp` with `wsl_model_path`. Existing databases created with the Windows bridge remain compatible as long as the GGUF model name and embedding dimension match.

For the full agent-facing operating guide, see [docs/AGENT_USER_MANUAL.md](docs/AGENT_USER_MANUAL.md).

For the current CSD/G-CL selector architecture, evidence, and next research steps, see
[docs/CLC_ARCHITECTURE_STATUS.md](docs/CLC_ARCHITECTURE_STATUS.md).

For the Hermes calibration handover, see
[docs/HERMES_RETRIEVAL_CALIBRATION_HANDOVER.md](docs/HERMES_RETRIEVAL_CALIBRATION_HANDOVER.md).

## Quick Commands

```powershell
py main.py config
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
py eval/build_combined_selector_training_report.py
py eval/build_guarded_continual_selector_report.py
py eval/selector_runtime_config_eval.py
py eval/guarded_continual_live_endpoint_eval.py
py eval/selector_explain_endpoint_eval.py
py eval/selector_retrieval_feature_eval.py
py eval/selector_live_retrieval_pipeline_eval.py
py eval/selector_retrieval_calibration_eval.py --embedding-backend hash --top-k 8
py eval/mechanism_component_eval.py
py eval/memory_maintenance_eval.py
py eval/maintenance_impact_eval.py
py eval/maintenance_multi_case_eval.py
py eval/memory_training_run.py --fast-hash
py eval/memory_training_run_smoke.py
py eval/report_issue_regression.py
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
py eval/session_memory_eval.py
py eval/session_topic_filter_smoke.py
py eval/usage_confidence_eval.py
py eval/teach_correct_smoke.py
py eval/authority_chain_regression.py
py eval/authority_endpoint_smoke.py
py eval/chat_smoke.py
py eval/agent_bug_report_regression.py
py eval/agent_corpus_experiment.py
py eval/session_short_topic_switch_eval.py --use-config-embedding
py eval/correction_target_validation_eval.py
py eval/ask_conflict_surface_eval.py
py eval/live_fact_conflict_variants_eval.py
py eval/long_memory_abilities_eval.py
py eval/long_memory_benchmark_eval.py
py eval/long_memory_benchmark_eval.py --preset medium --save-report logs/long_memory_benchmark_medium_report.json --include-rows
py eval/long_memory_benchmark_eval.py --configured-embedding --cases-per-ability 15 --noise-count 120
py eval/long_memory_messy_eval.py --save-report logs/long_memory_messy_hash_report.json --include-rows
py eval/long_memory_messy_eval.py --configured-embedding --noise-count 40
py eval/embedding_cache_smoke.py
py eval/cleanup_generated_artifacts.py
py chat.py --agent-id agent_alpha
py serve.py --host 127.0.0.1 --port 8765
```

After changing resolver or retrieval code, restart any long-running server before evaluating answers. The report regression covers short natural questions such as `who am i`, `what does G-CL maintain`, CSD contradiction questions, CLC definition questions, and consolidation questions.

`long_memory_benchmark_eval.py` supports `--preset smoke|medium|full`, timing breakdowns, `--save-report`, `--weak-case-limit`, and `--include-rows` for persistent benchmark artifacts. Saved reports are useful for comparing retrieval changes, configured embedding runtime, and weak cases across versions.

`long_memory_messy_eval.py` is a harder local pressure test inspired by long-memory benchmarks. It checks buried facts in noisy conversation turns, temporal updates, multi-hop association, session topic switching, and abstention for unknown sensitive data.

Configured GGUF embeddings use a persistent SQLite cache at `logs/embedding_cache.sqlite`. Delete that file if you intentionally change embedding model behavior and want a completely cold run.

If local disk space gets tight after repeated benchmark runs, use `py eval/cleanup_generated_artifacts.py`. It removes ignored long-memory benchmark artifacts, the generated embedding cache, the generated memory event log, and Python bytecode caches.

## API Endpoints

- `GET /health`
- `GET /stats`
- `GET /config`
- `GET /sessions`
- `GET /memory_usage`
- `POST /ingest`
- `POST /ingest_batch`
- `POST /teach`
- `POST /correct`
- `POST /retrieve`
- `POST /query` (alias for `/retrieve`)
- `POST /learn`
- `POST /learn/document`
- `POST /agent_plan`
- `POST /authority`
- `POST /ask`
- `POST /session`
- `POST /sessions`
- `POST /session_history`
- `POST /session_memory`
- `POST /feedback`
- `GET /feedback`
- `POST /memory_usage`
- `POST /migration_validate`
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

Agent-friendly aliases are supported for common guesses: `/query` is accepted as `/retrieve`, `question` or `q` can be used wherever a retrieval `query` is expected, and `content` can be used instead of `text` for `/teach`, `/ingest`, and `/learn`.

For migrations, `POST /ingest_batch` accepts structured `items` or `memories` as well as plain `texts`. Structured items can carry their own `namespace`, `source`, `memory_type`, `domain`, `priority`, and `metadata`; the namespace fallback is item namespace, then batch namespace, then `global`. This avoids accidentally importing a full corpus into the wrong agent namespace.

Ask for an extractive answer with cited memory evidence:

```powershell
$body = @{ query = "can the assistant push to GitHub automatically"; top_k = 4 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ask" -Method Post -ContentType "application/json" -Body $body
```

Inspect active retrieval and symbolic vocabulary:

```powershell
py main.py config
Invoke-RestMethod -Uri "http://127.0.0.1:8765/config"
```

Agent-controlled LLM learning is available through `POST /learn`, but it is disabled by default in `config.yaml`. Agents should call it only when a selected text snippet contains durable facts worth extracting. The implementation supports `dry_run`, `extract_only`, and `extract_and_store`; `teach`, `store`, and `store_facts` are accepted as aliases for `extract_and_store`. Dry-run and extract-only responses include a warning that no facts were persisted. The learner routes extracted facts to `teach`, `correct`, or `skip` after similarity checks, and callers can pass `memory_type` or `domain` hints when they need to override LLM/symbolic classification. `POST /learn/document` chunks longer content on paragraph and sentence boundaries where possible, then runs the same learning flow per chunk. Real document learning uses `llm.chunk_delay` between chunks and `llm.max_retries`/`llm.retry_backoff` for transient 429/5xx provider failures. `llm.fallback_models` can list comma-separated backup model names, and `/learn` responses include `llm_model`/`llm_models_by_chunk` so agents can see which model was used. Keep `llm.enabled: false` until an OpenAI-compatible provider and API key environment variable are configured. The default provider settings use `glm-5` at `https://opencode.ai/zen/go/v1`; set `OPENCODE_GO_API_KEY` before enabling real calls.

`POST /agent_plan` lets the configured LLM propose memory API actions from a natural-language instruction. It is deliberately plan-only: it returns endpoints, payloads, reasons, warnings, and `requires_confirmation=true`, but it does not execute the actions. Use this before any future autonomous execution mode.

Continue a session:

```powershell
$body = @{ query = "what should I remember next"; agent_id = "agent_alpha"; session_id = "sess_example" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ask" -Method Post -ContentType "application/json" -Body $body
```

When `session_id` is supplied, `/ask` uses topic-filtered recent session turns plus a small `active_topic` session memory as retrieval context. This lets follow-up questions such as "what about that?" inherit the current topic and pinned evidence without dragging every recent topic into the retrieval query. Pronoun-based follow-ups apply a bounded exact-evidence boost to the active topic's memory ids and mark those evidence rows with `session_exact_evidence`. The active topic is updated by `/teach`, `/correct`, and `/ask`. Short topic-switch questions such as "what is CSD" or "what is G-CL" no longer inherit the previous active topic unless they overlap the active topic or contain a real follow-up marker.

Normal new-topic questions use the raw query for retrieval even when a session has prior context. Session context is blended into the retrieval query only for true vague follow-ups such as "what about that?" or "what should I remember about that label?".

Inspect session memory:

```powershell
$body = @{ session_id = "sess_example" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/session_memory" -Method Post -ContentType "application/json" -Body $body
```

Teach or correct memory:

```powershell
$teach = @{ text = "Remember: the agent should keep API evidence ids visible."; agent_id = "agent_alpha" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/teach" -Method Post -ContentType "application/json" -Body $teach

$correct = @{ correction = "The assistant must not push to GitHub automatically."; target_query = "GitHub push policy"; agent_id = "agent_alpha" } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/correct" -Method Post -ContentType "application/json" -Body $correct
```

When explicit `target_memory_ids` are provided, `/correct` validates that each target exists and is visible in the requested namespace scope before storing the correction. Missing or out-of-scope ids return an error so agents do not accidentally create unlinked correction chains. When no explicit target, target query, or session evidence is supplied, `/correct` can use the correction text as a fallback target query, but only when there is meaningful subject/topic overlap. Explicit orphan/no-target corrections remain unlinked.

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
/session            show active session memory
/new                start a new session
/quit               exit
```

Manual feedback session:

```powershell
py eval/interactive_retrieval_test.py --top-k 3
```

Stored feedback is used as a bounded reranking signal. Useful and excellent results receive a small boost, while wrong, stale, wrong-domain, or missing-source results are downranked. Feedback also contributes small source/domain reliability signals that can help fresh memories from trusted sources rank better. Retrieval use is logged after `/ask`, updates `last_recalled`, appears in `/stats`, and can be inspected with `POST /memory_usage`. Prior usage contributes a small confidence signal without directly boosting retrieval rank. Retrieval also includes a supersession signal: when versioned sources such as `agent_memory_v1` and `agent_memory_v2` are both present, current/correction queries prefer the newer corrected source while preserving older memories as historical context. `/ask` responses keep primary evidence focused, prefer snippets from current/corrected evidence when stale evidence is also present, then expose extra `source_context` for additional relevant files and `stale_context` for superseded relation-linked memories.

Feedback can be audited with `GET /feedback?label=wrong&limit=20` or `GET /feedback?max_rating=0&limit=50`.

For simple factual questions, answer synthesis uses stricter snippet selection so unrelated evidence is not concatenated into a single answer. Extra retrieved material remains inspectable through `source_context`, `stale_context`, and `/why`.

If `/ask` or `/retrieve` finds no evidence in the searched namespace but other namespaces contain memories, responses include `namespace_warning` with the searched namespace scope and available namespaces. `POST /migration_validate` reports namespace counts, vector dimensions, embedding signature, and an optional smoke query so agents can verify a migrated database before trusting it.

Retrieval ranking weights live in `config.yaml` under `retrieval_weights`. The current profile was selected with `py eval/retrieval_weight_optimization.py` and emphasizes source, feedback, supersession, manifest relation, consolidation-summary, and intent signals over raw vector similarity. CLC controller thresholds live under `thresholds`; `py eval/clc_threshold_calibration.py` compares the configured profile against nearby alternatives. Symbolic domain aliases, memory type keywords, and retrieval intent labels live under `symbolic` and can be inspected with `py main.py config` or `GET /config`. Retrieved evidence now also carries stored CSD contradiction metadata, so `/ask` can surface unresolved correction pressure even when the contradictory memory is not part of the top evidence set. Queries containing exact alphanumeric identifiers such as `TemporalItem027`, ticket ids, or numbered codenames receive a conservative identifier-match boost and broader lexical backfill so nearby IDs do not outrank the exact item.

CSD includes lexical preference conflict checks for common daily-use facts such as `likes tea` versus `hates tea` or `never drinks tea`. These conflicts protect the new memory and store contradiction pressure even when embeddings alone consider the sentences similar.

Consolidation is non-destructive. `/consolidate create` and `POST /consolidate` create a new embedded summary memory and connect it to originals with `summarizes` relations. Original memories remain available as evidence, and `POST /consolidation_sources` or `/consolidate sources <summary-id>` can show the source memories behind a summary.

Relation semantics are intentionally conservative: `corrects` and `supersedes` create true authority chains where older target memories can be treated as superseded or stale for current answers. `updates` links supplemental improvements to an original memory without automatically replacing the original definition or making it stale. Use `corrects` or `supersedes` for changed truth; use `updates` for clarifications, annotations, and maintenance improvements.

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

This repo keeps code, docs, schemas, and test corpora in Git. Runtime databases, logs, caches, local models, and generated experiment artifacts are intentionally ignored.
