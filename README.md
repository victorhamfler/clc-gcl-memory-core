# CLC-GCL Memory Core

Experimental AI agent memory core based on CLC, CSD, and G-CL ideas.

The program stores text memories as embedding-backed nodes, assigns them to symbolic domains, tracks source files, applies novelty and contradiction diagnostics, and retrieves memories with domain/source-aware ranking. The active baseline database is `memory_experiment_180_best.db`.

## Current Baseline

- Embedding backend: WSL `llama_cpp`
- Model: `embeddinggemma-300M-Q8_0.gguf`
- Vector dimension: `768`
- Active database: `memory_experiment_180_best.db`
- HTTP API default: `http://127.0.0.1:8765`

## Quick Commands

```powershell
python main.py stats
python retrieve.py --top-k 3 "geometry controller effective dimension curvature regime"
python eval/query_eval.py
python serve.py --host 127.0.0.1 --port 8765
```

## API Endpoints

- `GET /health`
- `GET /stats`
- `POST /ingest`
- `POST /ingest_batch`
- `POST /retrieve`

Example:

```powershell
$body = @{ query = "what can the geometry controller contribute to the AI memory program"; top_k = 3 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/retrieve" -Method Post -ContentType "application/json" -Body $body
```

## Experiment Workflow

Build or rebuild an experiment DB:

```powershell
python eval/corpus_experiment.py --max-words 180 --overlap-words 30 --db-path memory_experiment_180_best.db --reset
```

Promote a validated DB into `config.yaml`:

```powershell
python promote_db.py memory_experiment_180_best.db
```

## Notes

This repo keeps only the current best baseline database in Git. Older scratch databases, logs, caches, and local runtime files are ignored.
