# Agent User Manual

This manual explains how an AI agent should use the CLC-GCL Memory Core as an external memory brain. The program stores durable knowledge, retrieves relevant context, tracks corrections, separates agents with namespaces, and provides maintenance tools that help memory improve without destructively rewriting old evidence.

## 1. What This Program Is

The memory core is a local service and chat tool for agents. It lets an agent:

- Store knowledge with `/teach`, `/remember`, `/correct`, or the HTTP API.
- Ask questions against stored memory with evidence.
- Keep each agent's memory isolated in its own namespace.
- Share common rules through the `global` namespace when desired.
- Mark stale or wrong memories by linking corrections instead of deleting history.
- Review weak memories and domain health.
- Create non-destructive summaries that point back to original source memories.

The main mechanisms are:

- `CLC`: chooses the learning state for each new memory, such as recall, focus, protect, or split-domain.
- `CSD`: diagnoses semantic distance, novelty, surprise, and contradiction pressure.
- `G-CL`: maintains domain geometry, anchors, drift, curvature, and stability.

Together they make the memory more than a vector database. The program keeps evidence, tracks change over time, and exposes repair operations that an agent can use as part of training.

## 2. Current Baseline

The default configuration is in `config.yaml`.

- Database: `memory_experiment_180_best.db`
- Embedding backend from Windows: `wsl_llama_cpp`
- Embedding backend from WSL/Hermes: `llama_cpp`
- Embedding model: `embeddinggemma-300M-Q8_0.gguf`
- Embedding dimension: `768`
- Default server URL: `http://127.0.0.1:8765`
- Default chat namespace: `global`

The configured model path is:

```text
\\wsl.localhost\Ubuntu\home\victo\models\embeddinggemma-300M-Q8_0.gguf
```

For fast tests, some evals use deterministic hash embeddings instead of the GGUF model.

The default config is Windows-first and uses `wsl_llama_cpp` to call into WSL. When the server or chat runs inside WSL/Hermes, the runtime automatically switches to native `llama_cpp` using `/home/victo/models/embeddinggemma-300M-Q8_0.gguf`. A DB created with `wsl_llama_cpp` can be reused from WSL as long as the GGUF model name and embedding dimension match.

The Hermes agent-facing deployment keeps its live DB in:

```text
\\wsl.localhost\Ubuntu\home\victo\.hermes\clc-gcl-memory-core\memory_experiment_180_best.db
```

After source changes, restart the long-running server before judging behavior. A stale server can retrieve the right raw memories but still answer with old resolver logic.

## 3. Agent Memory Model

Each memory is a text node with:

- `memory_id`: stable id such as `mem_...`
- `namespace`: the agent or shared memory space
- `domain`: symbolic topic cluster, such as `agent_memory`, `CSD`, or `G-CL`
- `source`: provenance label, file, client, or maintenance origin
- `memory_type`: inferred semantic type
- `CLC state`: learning decision
- `CSD scores`: novelty, contradiction, surprise, recall
- `G-CL geometry`: domain drift, curvature, anchor updates
- `relations`: links such as `corrects`, `updates`, `supersedes`, and `summarizes`
- `usage_count` and `last_recalled`: traces created when a memory is used as `/ask` evidence

An agent should treat memory as evidence-linked knowledge. Do not overwrite important facts silently. Use corrections and updates so the memory can explain why a newer answer replaced an older one.

## 4. Namespaces

Namespaces are the main boundary between agents.

Recommended pattern:

```text
agent:<agent_name>
```

Examples:

```text
agent:planner
agent:geometry_controller
agent:research_assistant
```

Use `global` for shared rules or common reference knowledge that many agents can read.

Important behavior:

- `/ask` and `/retrieve` can include `global` memory by default when an agent namespace is used.
- Maintenance and consolidation are scoped to the active namespace by default.
- `include_global=true` can be used with API maintenance/consolidation calls when shared memories should be included.
- Corrections, improvements, and summaries are written into the active namespace.

For real agents, always launch chat with a namespace:

```powershell
py chat.py --agent-id planner --namespace agent:planner
```

## 5. Starting The Chat Interface

The chat interface is the easiest way for an agent or tester to interact with memory.

```powershell
py chat.py --agent-id planner --namespace agent:planner
```

Useful options:

```powershell
py chat.py --agent-id planner --namespace agent:planner --top-k 8
py chat.py --agent-id planner --namespace agent:planner --source agent_bootstrap
py chat.py --agent-id planner --namespace agent:planner --fast-hash
```

When chat starts, it creates or continues a session. Session turns and active session memory help vague follow-up questions inherit the current topic and evidence.

The active session memory stores the latest topic, short answer context, and pinned evidence ids. It is updated by `/teach`, `/correct`, and `/ask`, then used when prompts such as `what about that?`, `this`, `it`, or `previous` need the current topic.

## 6. Core Chat Commands

Ask memory:

```text
/ask What should this agent remember about GitHub uploads?
```

Natural text without a slash also asks memory:

```text
What does the user prefer for agent manuals?
```

Short natural questions are supported, including identity, CLC/G-CL mechanism, CSD contradiction, and consolidation questions:

```text
who am i
what does G-CL maintain
what happens when facts contradict
how does memory consolidation work
what CLC states exist
does the system remember previous questions
```

These query types use stricter intent matching and a broader lexical candidate scan so important short prompts are not swallowed by unrelated high-vector-score technical memories.

Teach durable knowledge:

```text
/teach The planner agent should propose steps before making large repository changes.
```

Priority and CLC controls can be placed at the beginning of `/teach`:

```text
/teach priority=high The planner agent should never hide evidence ids from reports.
/teach clc=PROTECT The planner agent must treat explicit upload permission as a protected user policy.
```

Alias:

```text
/remember The planner agent should keep namespace agent:planner isolated from other agents.
```

Correct stale or wrong memory:

```text
/correct The planner agent may upload to GitHub only when the user explicitly asks.
```

Corrections default to high priority so they are not lost behind low-signal repetition. A correction is assigned to the domain of the correction text, not blindly to the target memory's domain.

Best workflow for correction:

1. Ask a question that retrieves the wrong or stale evidence.
2. Use `/correct <new truth>`.
3. The correction links to the last evidence as a `corrects` relation.
4. Future answers prefer the correction while preserving the old memory as historical context.

Train retrieval with feedback:

```text
/feedback useful 1
/feedback wrong 2
/feedback excellent all
/feedback stale mem_abc123
```

Inspect the last answer:

```text
/sources
/why
```

Session commands:

```text
/history
/session
/new
```

`/session` shows the active session topic and pinned evidence ids. `/history` shows recent turns.

Exit:

```text
/quit
```

## 7. Memory Maintenance Commands

Maintenance helps an agent find weak, stale, contradictory, sparse, or poorly sourced memories.

Run a full namespace-scoped review:

```text
/memory review
```

This reports:

- Namespace being reviewed.
- Domain health flags.
- Weak memory candidates.
- Safe consolidation candidates.
- Recommended next actions.

List weak memories:

```text
/memory weak
/memory weak 12
```

List repaired or resolved weak memories:

```text
/memory resolved
```

Plan improvements:

```text
/memory improve
/memory improve mem_abc123
```

Store a clarifying update:

```text
/memory improve mem_abc123 This memory should be treated as a historical note, not current policy.
```

This creates a new memory and links it to the target with an `updates` relation.

## 8. Consolidation Commands

Consolidation compresses stable repeated memories into a summary memory. It is non-destructive: original memories remain in the database, and the summary links back to them with `summarizes` relations.

Preview safe summary groups:

```text
/consolidate plan
```

Create one or more summaries:

```text
/consolidate create
/consolidate create min=4 max=8 groups=1
```

Inspect the source memories behind a summary:

```text
/consolidate sources mem_summary_id
```

Use consolidation after a namespace has enough stable, repeated, source-linked memories. Avoid consolidation when a domain has unresolved contradictions or protected memories.

## 9. HTTP API

Start the server:

```powershell
py serve.py --host 127.0.0.1 --port 8765
```

If testing the WSL/Hermes deployment, start the server from the WSL project folder so it uses the WSL `llama_cpp` backend and the Hermes DB:

```powershell
wsl -e sh -lc "cd /home/victo/.hermes/clc-gcl-memory-core && /home/victo/.openclaw/workspace/module/.venv_mlcpu/bin/python serve.py"
```

Health and stats:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8765/health"
Invoke-RestMethod -Uri "http://127.0.0.1:8765/stats"
```

Inspect active session memory:

```powershell
$body = @{
  session_id = "sess_example"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/session_memory" -Method Post -ContentType "application/json" -Body $body
```

Teach:

```powershell
$body = @{
  text = "The planner agent should ask before irreversible operations."
  agent_id = "planner"
  namespace = "agent:planner"
  source = "manual_seed"
  priority = "high"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/teach" -Method Post -ContentType "application/json" -Body $body
```

To force a CLC state for critical operator-controlled memories:

```powershell
$body = @{
  text = "The planner may push to GitHub only after explicit user instruction."
  agent_id = "planner"
  namespace = "agent:planner"
  source = "manual_policy"
  force_clc_state = "PROTECT"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/teach" -Method Post -ContentType "application/json" -Body $body
```

Ask:

```powershell
$body = @{
  query = "What should the planner do before irreversible operations?"
  agent_id = "planner"
  namespace = "agent:planner"
  include_global = $true
  top_k = 5
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ask" -Method Post -ContentType "application/json" -Body $body
```

Continue a session with follow-up memory:

```powershell
$body = @{
  query = "What about that?"
  agent_id = "planner"
  namespace = "agent:planner"
  session_id = "sess_example"
  top_k = 5
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ask" -Method Post -ContentType "application/json" -Body $body
```

When a session id is supplied, `/ask` returns `session_context_used`, `session_context`, and `retrieval_query`. The context may include a `session_memory` item for the active topic.

Correct:

```powershell
$body = @{
  correction = "The planner may push to GitHub only after explicit user instruction."
  target_query = "GitHub push policy"
  agent_id = "planner"
  namespace = "agent:planner"
  source = "manual_correction"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/correct" -Method Post -ContentType "application/json" -Body $body
```

Retrieve raw evidence:

```powershell
$body = @{
  query = "GitHub push policy"
  namespace = "agent:planner"
  include_global = $true
  top_k = 5
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/retrieve" -Method Post -ContentType "application/json" -Body $body
```

Inspect correction/update authority:

```powershell
$body = @{
  memory_id = "mem_example"
  namespace = "agent:planner"
  include_global = $true
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/authority" -Method Post -ContentType "application/json" -Body $body
```

You can also inspect the authority chain for the top memories returned by a query:

```powershell
$body = @{
  query = "What is the current GitHub push policy?"
  namespace = "agent:planner"
  include_global = $true
  top_k = 5
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/authority" -Method Post -ContentType "application/json" -Body $body
```

Use `/authority` before adding another correction when you are unsure whether a memory is already superseded. It returns the current authoritative memory ids, the relation graph, and per-node states such as `current`, `superseded`, or `standalone`.

Inspect retrieval usage:

```powershell
$body = @{
  namespace = "agent:planner"
  include_global = $false
  limit = 10
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/memory_usage" -Method Post -ContentType "application/json" -Body $body
```

Direct ingest has the same nested memory shape as teach while preserving flat compatibility fields:

```powershell
$body = @{
  text = "Mercury is the smallest planet."
  namespace = "agent:planner"
  source = "manual_ingest"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ingest" -Method Post -ContentType "application/json" -Body $body
```

Batch ingest returns both `results` and `memories` so clients can inspect the created chunks:

```powershell
$body = @{
  texts = @(
    "Neptune has the strongest winds in the solar system."
    "Venus is the hottest planet in the solar system."
  )
  namespace = "agent:planner"
  source = "manual_batch"
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/ingest_batch" -Method Post -ContentType "application/json" -Body $body
```

Review memory:

```powershell
$body = @{
  namespace = "agent:planner"
  include_global = $false
  weak_limit = 8
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/memory_review" -Method Post -ContentType "application/json" -Body $body
```

Plan consolidation:

```powershell
$body = @{
  namespace = "agent:planner"
  include_global = $false
  min_domain_memories = 4
  max_candidates_per_domain = 8
} | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8765/consolidation_plan" -Method Post -ContentType "application/json" -Body $body
```

## 10. Recommended Agent Training Workflow

Use this loop when training a new agent's memory.

1. Create a namespace.

```powershell
py chat.py --agent-id planner --namespace agent:planner --source planner_training_v1
```

2. Seed identity and operating rules.

```text
/teach The planner agent helps plan coding tasks, tests, repository checkpoints, and agent memory experiments.
/teach The planner agent should keep high-risk operations explicit and evidence-linked.
/teach The planner agent should separate proposed plans from completed actions.
```

3. Seed user preferences.

```text
/teach The user prefers GitHub uploads only when explicitly requested.
/teach The user wants concise reports after tests, commits, and uploads.
/teach The user is developing the memory program as an agent brain assistant.
```

4. Ask verification questions.

```text
/ask What should you do before uploading to GitHub?
/ask What kind of program are we building?
/ask How should you handle a correction?
```

5. Correct errors immediately.

```text
/correct The user wants GitHub uploads only after explicit instruction in the current conversation.
```

6. Add feedback to evidence.

```text
/feedback excellent 1
/feedback wrong 2
```

7. Run maintenance.

```text
/memory review
/memory weak
```

8. Add clarifying improvements for weak memories.

```text
/memory improve mem_abc123 This should be treated as a current user preference, not a historical note.
```

9. Consolidate only after enough stable memories accumulate.

```text
/consolidate plan
/consolidate create groups=1
```

10. Re-ask the verification questions and compare answers.

## 11. How To Read Results

Ask results include:

- `answer`: extractive answer synthesized from memory evidence
- `confidence`: answer confidence
- `conflict`: whether evidence conflicts
- `usage_events`: retrieval-use events logged for the evidence used by the answer
- `session_context`: recent turn or active-topic context used for a session follow-up
- `live_conflicts`: query-time conflict details found inside retrieved evidence
- `evidence`: primary supporting memories
- `source_context`: additional memories from related sources
- `stale_context`: superseded or historical context

Evidence objects include `namespace`, `domain_id`, `domain_name`, `source`, scoring fields, and a text preview. This lets an agent audit whether an answer came from its own namespace, shared `global` memory, or another allowed scope.

Retrieval details include:

- `score`: final ranked score
- `vector_score`: embedding similarity
- `domain_score`: symbolic/domain affinity
- `text_score`: lexical signal
- `feedback_score`: learned usefulness or failure signal
- `usage_count`: how many times the memory has been used as answer evidence
- `last_recalled`: most recent retrieval-use timestamp
- `supersession_score`: current versus historical source signal
- `authority_state`: whether a memory is `current`, `superseded`, or `standalone`
- `authoritative_memory_ids`: current memory ids that should be preferred for the chain
- `superseded_by_memory_ids`: newer memories that replace this one
- `supersedes_memory_ids`: older memories this one replaces
- `correction_chain_depth`: distance from this memory to the current authority
- `summary_relation_score`: summary/source relation signal

Authority results include:

- `requested_memory_ids`: memory ids inspected directly or found through the query
- `authoritative_memory_ids`: final current ids for the inspected graph
- `nodes`: memory previews with source, namespace, authority state, chain depth, and full text
- `relations`: `corrects`, `updates`, and `supersedes` links used to build the graph
- `query_results`: retrieval results when the request included `query`

Maintenance reasons include:

- `missing_source`: provenance should be improved
- `low_confidence`: weak inferred memory
- `low_stability_low_recall`: memory may not retrieve reliably yet
- `high_novelty_or_surprise`: memory may need examples or domain clarification
- `negative_feedback`: users or agents marked it as bad evidence
- `contradiction_chain`: memory participates in contradiction history
- `unlinked_important_state`: protected or split-domain memory lacks relation context
- `resolved_by_update`: an update/correction already repairs it

Domain health actions include:

- `monitor`: no immediate action
- `seed_or_merge`: sparse domain needs more examples or merging
- `split_or_reanchor`: high drift or curvature suggests mixed topics
- `protect_and_review`: contradictions or protected memories require review
- `consolidate`: stable enough for summary creation
- `add_examples`: high-dimensional domain needs more samples

## 12. Safety Rules For Agents

Use these rules when another agent connects to this memory program.

- Always set `namespace` for agent-specific memory.
- Use `global` only for intentionally shared rules.
- Prefer `/correct` over re-teaching a conflicting fact without relation context.
- Use `priority=high` for important durable instructions and `clc=PROTECT` or `force_clc_state=PROTECT` only for policies that must be protected.
- Keep `source` labels meaningful.
- Do not delete old evidence to hide mistakes; link updates and corrections.
- Use `/authority` to inspect correction/update chains before trusting or adding another correction to surprising evidence.
- Review `/sources` and `/why` before trusting surprising answers.
- Use feedback whenever evidence is clearly useful, stale, wrong, or wrong-domain.
- Run `/memory review` before consolidation.
- Treat summaries as acceleration, not replacement for original evidence.
- Keep real user preferences current with corrections when they change.

## 13. CLC, CSD, And G-CL In Practice

The mechanisms should be tested through behavior, not just raw scores.

CLC is working well when:

- Familiar memories enter recall-like states.
- Novel topics create or split domains.
- Contradictory memories move toward protected handling.
- Important new rules do not vanish into unrelated domains.

CSD is working well when:

- Direct corrections produce contradiction pressure.
- Retrieved contradictory factual evidence can raise `conflict=True` at query time.
- Similar but not identical memories remain retrievable together.
- Novel examples raise surprise without breaking stable domains.
- Weak memories with high novelty become visible in maintenance.

G-CL is working well when:

- Domains keep related memories together.
- Drift and curvature rise when topics are mixed or unstable.
- Stable domains become consolidation candidates.
- Agent namespaces do not contaminate each other's domains.

## 14. Useful Test Commands

Run core health checks:

```powershell
py main.py stats
py eval\agent_namespace_workflow_smoke.py
py eval\agent_namespace_workflow_smoke.py --use-config-embedding
py eval\maintenance_namespace_isolation_eval.py
py eval\namespace_isolation_eval.py
py eval\namespace_geometry_eval.py
py eval\gcl_domain_health_eval.py
py eval\maintenance_false_repair_eval.py
py eval\report_issue_regression.py
py eval\consolidation_safety_smoke.py
py eval\wsl_backend_compat_eval.py
py eval\session_memory_eval.py
py eval\usage_confidence_eval.py
py eval\api_hardening_regression.py
py eval\authority_chain_regression.py
py eval\authority_endpoint_smoke.py
py eval\chat_smoke.py
py eval\server_smoke.py
```

Run broader behavior checks:

```powershell
py eval\mechanism_component_eval.py
py eval\answer_quality_eval.py
py eval\summary_answer_quality_eval.py
py eval\summary_retrieval_eval.py
py eval\subtle_contradiction_eval.py
py eval\long_run_drift_eval.py --cycles 10
py -m compileall core storage eval chat.py main.py serve.py
```

## 15. Troubleshooting

If the model path is missing:

- Confirm the WSL path exists.
- Confirm `config.yaml` points to the right `gguf_path` and `wsl_model_path`.
- Use `--fast-hash` only for tests, not final quality evaluation.

If an answer ignores agent memory:

- Check the namespace.
- Use `/sources` to see what was retrieved.
- Use `/why` to inspect scoring.
- Ask with a more specific query.
- Teach a clearer memory with a source label.
- Confirm the server was restarted after code changes.

If a follow-up such as `what about that?` follows the wrong topic:

- Run `/session` and check the active topic.
- Run `/history` and inspect the most recent turns.
- Ask the topic explicitly once, then ask the follow-up again.
- Confirm `session_id` is being reused in API calls.
- Run `py eval\session_memory_eval.py`.

If wrong memories keep appearing:

- Ask a query that retrieves the wrong memory.
- Use `/correct`.
- Add `/feedback wrong <number>` to the wrong evidence.
- Run `/memory review`.

If maintenance shows many weak memories:

- Add source labels.
- Add clarifying examples.
- Use `/memory improve` for important memories.
- Consolidate only after contradictions and weak evidence are handled.

If namespaces seem mixed:

- Run `py main.py stats` and inspect `namespaces_detail`.
- Run `py eval\maintenance_namespace_isolation_eval.py`.
- Make sure all API calls pass the intended `namespace`.

If a short natural query retrieves unrelated technical chunks:

- Restart the server so it loads the latest resolver.
- Run `py eval\report_issue_regression.py`.
- Check that the query has an intent-specific memory in the active namespace or `global`.
- Use `/teach` or `/correct` with clear wording such as "My name is ..." or "CSD detects contradictions ..." when the memory is missing.

Verified live WSL/Hermes questions after the resolver fixes:

- `who am i` returns the Victor identity memory.
- `what does G-CL maintain` returns G-CL domain geometry evidence.
- `what happens when facts contradict` returns CSD contradiction evidence.
- `how does memory consolidation work` returns consolidation summary evidence.
- `what CLC states exist` returns CLC state evidence without a false current/stale conflict.
- `does the system remember previous questions` returns session/history command evidence.

## 16. Minimal Real-Agent Integration Pattern

For an external agent, use the HTTP API in this order:

1. On startup, set `agent_id` and `namespace`.
2. For every task, call `/ask` with the user query and `include_global=true`.
3. Use returned evidence in the agent's reasoning context.
4. When the user gives durable instruction, call `/teach`.
5. When the user corrects something, call `/correct` with a target query or target memory ids.
6. After important answers, call `/feedback` if the outcome is known.
7. Periodically call `/memory_review`.
8. Use `/memory_improve` or `/consolidate` only after review.

The memory program should behave like a trainable assistant brain: it remembers, retrieves, exposes evidence, accepts correction, and adapts through feedback and maintenance rather than silently mutating its history.
