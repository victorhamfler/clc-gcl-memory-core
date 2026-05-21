# Claim Scope Alias Candidates Handover

Date: 2026-05-20

This note is for the selector-module session. The memory-program session mined the current linked outcome log and produced a first claim-scope alias candidate file.

## Outputs

Generated files:

```text
../experiments/claim_scope_alias_candidates.json
../experiments/claim_scope_alias_candidates_report.md
```

Source log:

```text
logs/memory_outcomes.jsonl
```

Current sample size:

- Ask events: 18
- Feedback events: 17
- Linked feedback events: 17
- Candidate slots: 9

## Strongest Candidates

The most usable candidates from this small sample are:

- `method`: `weather`, `accuweather`, `url`, `radar_method`
- `policy`: `wants`, `uploads`, `explicitly`, `requested`, `conversation`
- `status`: `outcome`, `logging`
- `filename`: `accuweather_radar_report`
- `backend_port`: `8765`

Useful but more domain-specific:

- `codename`: `cedar`, `map`, `guardrails`, `enabled`
- `drink`: `sparkling`
- `pizza`: `cheese`

Needs caution:

- `mechanism`: current aliases include broad terms such as `domain`, `maintains`, `geometry`, `anchor`, `drift`, `curvature`, `stability`, `helps`. These may help CSD/G-CL tests but could be too broad for general agent memory.

## Tool Added In Memory Session

The memory-program session added:

```text
eval/claim_scope_alias_candidate_mining.py
```

It parses linked `ask` and `feedback` events from `logs/memory_outcomes.jsonl`, groups feedback by `linked_operation_id`, and writes compact JSON plus a readable Markdown report.

Run:

```powershell
..\.venv-torch\Scripts\python.exe .\eval\claim_scope_alias_candidate_mining.py
```

## Recommendation For Selector Session

Do not merge all candidates blindly. Start with one or two narrow slots and add regressions:

1. `method` versus `filename`
2. `policy` versus unrelated tool/method memories
3. `backend_port` versus stale backend-port corrections

The current sample is small, so treat the JSON as candidate evidence, not final config.
