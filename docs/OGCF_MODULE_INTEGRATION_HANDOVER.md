# OGCF Module Integration Handover

**Date:** 2026-05-23  
**Status:** Module implemented, integration eval passing  
**Deliverables:** 4 new core modules + 1 eval script  

---

## 1. What Was Built

A new OGCF-inspired memory geometry module was created and integrated with the existing CLC-GCL memory program and selector module.

### New Files

| File | Purpose | Lines |
|---|---|---|
| `core/ogcf_geometry.py` | OGCF geometry engine: clustering, SVD bases, loop detection, interaction excess, z-scores, bridge cluster detection | ~350 |
| `core/ogcf_signals.py` | Signal provider that maps OGCF geometry metadata to selector-friendly scalar signals | ~150 |
| `core/ogcf_selector.py` | Integration layer: augments `CLCPolicyFeatures` with OGCF signals before selector decisions | ~100 |
| `core/ogcf_api.py` | HTTP API handlers for `/ogcf_review` and `/ogcf_cluster_detail` endpoints | ~140 |
| `eval/ogcf_selector_integration_eval.py` | End-to-end test: signal provider, feature augmentation, selector decisions, real DB geometry | ~400 |

### Where They Live

```
clc_gcl_memory_core/
├── core/
│   ├── ogcf_geometry.py          # geometry engine
│   ├── ogcf_signals.py             # retrieval signal provider
│   ├── ogcf_selector.py            # selector integration
│   └── ogcf_api.py                 # HTTP API handlers
├── eval/
│   └── ogcf_selector_integration_eval.py
└── docs/
    └── OGCF_MODULE_INTEGRATION_HANDOVER.md   # this file
```

---

## 2. Architecture

### OGCF Geometry Engine (`core/ogcf_geometry.py`)

```
memory embeddings
→ KMeans clustering (n_clusters)
→ per-cluster SVD basis (rank_k)
→ nearest-neighbor adjacency graph
→ triangle loop discovery
→ transport projectors U_ab = SVD(U_a^T @ U_b)
→ interaction_excess = ||U_ac - U_bc @ U_ab||_F
→ z-score vs shuffled baselines
→ bridge cluster detection (high domain diversity)
→ risk region ranking
```

Key classes:
- `OGCFGeometryEngine` — runs the full pipeline
- `OGCFMemoryReviewer` — high-level reviewer that produces actionable reports
- `OGCFLoop`, `OGCFCluster`, `OGCFGeometryResult` — data containers

### Signal Provider (`core/ogcf_signals.py`)

```
OGCF metadata (from periodic background run)
+ retrieval rows
→ ogcf_bridge_overload_score
→ ogcf_max_interaction_z
→ ogcf_affected_memory_ratio
→ per-row ogcf_cluster_id, ogcf_in_bridge_cluster flags
```

The signal provider is **stateless and lightweight** — it reads cached OGCF metadata and computes signals per-query without recomputing geometry.

### Selector Integration (`core/ogcf_selector.py`)

```
base CLCPolicyFeatures
+ OGCF signals
→ adjusted_memory_bad_rate  (+0.15 * bridge_score)
→ adjusted_probe_drop       (+0.10 * affected_ratio)
→ adjusted_csd_ratio       (+0.3 * bridge_score + 0.2 * affected_ratio)
→ new CLCPolicyFeatures
→ selector.select()
```

This is the **main integration point**. Any code that calls `selector.select(features)` can instead call `select_with_ogcf(selector, features, rows, ogcf_meta)` to get OGCF-augmented decisions.

### API Layer (`core/ogcf_api.py`)

Provides two endpoints ready to wire into `serve.py`:

- `POST /ogcf_review` — run full geometry on a sample, return bridge clusters, risk regions, loop stats
- `POST /ogcf_cluster_detail` — inspect memories in a specific cluster

---

## 3. How to Use

### 3.1 Run a geometry review from Python

```python
from core.ogcf_geometry import OGCFGeometryEngine, OGCFMemoryReviewer
from storage.db import MemoryDB
import numpy as np

db = MemoryDB("memory_experiment_180_best.db")
# ... load embeddings and memory_ids into numpy array ...

engine = OGCFGeometryEngine(n_clusters=60, rank_k=8, neighbors=5)
reviewer = OGCFMemoryReviewer(engine)
report = reviewer.review(embeddings, memory_ids, db.db_path)

print(f"Loops: {report['loop_count']}")
print(f"Max interaction_z: {report['max_interaction_z']}")
print(f"Bridge clusters: {len(report['bridge_clusters'])}")
```

### 3.2 Augment selector features with OGCF

```python
from core.clc_policy_selector import CLCPolicySelector
from core.selector_runtime import selector_features_from_retrieval_context
from core.ogcf_selector import select_with_ogcf

rows = [...]  # retrieval rows
base_features, base_diag = selector_features_from_retrieval_context(rows)

ogcf_meta = {...}  # from periodic background analysis
selector = CLCPolicySelector()
decision, diagnostics = select_with_ogcf(
    selector, base_features, rows, ogcf_meta, base_diag
)
```

### 3.3 Add OGCF flags to retrieval rows

```python
from core.ogcf_signals import merge_ogcf_into_retrieval_rows

rows_with_ogcf = merge_ogcf_into_retrieval_rows(rows, ogcf_meta)
# rows now have:
#   ogcf_cluster_id, ogcf_in_bridge_cluster,
#   ogcf_in_risk_region, ogcf_bridge_penalty
```

### 3.4 Wire into serve.py

```python
# In serve.py, near the other api initializations:
from core.ogcf_api import OGCFReviewAPI
ogcf_api = OGCFReviewAPI(pipeline.db, pipeline.encoder)

# In Handler.do_POST:
elif path == "/ogcf_review":
    self._send_json(200, ogcf_api.review(payload))
elif path == "/ogcf_cluster_detail":
    self._send_json(200, ogcf_api.cluster_detail(payload))
```

---

## 4. Test Results

Run the integration eval:

```bash
cd clc_gcl_memory_core
python3 eval/ogcf_selector_integration_eval.py
```

### Current Results (passing all tests)

| Test | Description | Status |
|---|---|---|
| Signal Provider | OGCFSignalProvider computes correct bridge overload scores | PASS |
| Feature Augmentation | memory_bad_rate and csd_ratio increase under bridge overload | PASS |
| Selector Decision | OGCF-augmented features influence policy selection | PASS |
| Real Geometry | OGCF engine runs on 500-memory DB sample and finds loops | PASS |

Output saved to:
```
experiments/ogcf_selector_integration_eval_results.json
```

### Dry-Run Maintenance Candidate Gate

The selector session added a dry-run candidate generator and gate:

```bash
python eval/ogcf_maintenance_candidate_gate.py
```

New files:

- `eval/ogcf_maintenance_candidates.py`
- `eval/ogcf_maintenance_candidates_regression.py`
- `eval/ogcf_maintenance_candidate_gate.py`

The generated artifact schema is:

```text
ogcf_maintenance_candidates/v1
```

The report always includes:

```json
{
  "mutates_db": false
}
```

Candidate action types currently include:

- `exact_duplicate_group`
- `semantic_duplicate_group`
- `stale_version_candidate`
- `bridge_cluster_review`

This is the required path before any endpoint or maintenance action is allowed to mutate the memory DB.

---

## 5. How This Connects to the Selector

The existing selector already computes `memory_bad_rate`, `probe_drop`, and `csd_ratio` from retrieval context. The OGCF module feeds **structural memory-graph instability** into these same features:

| Existing Signal | OGCF Addition | Effect on Selector |
|---|---|---|
| `stale_ratio` | `affected_memory_ratio` from bridge clusters | Increases `memory_bad_rate` → more likely to select LONG_SEVERE |
| `contradiction_peak` | `bridge_overload_score` as a proxy for composition conflict | Increases `probe_drop` → selector becomes more cautious |
| `csd_ratio` | `csd_ratio_boost` from high interaction_z | Increases CSD sensitivity → more aggressive novelty detection |

The result: when the memory graph has bridge overload (e.g., cluster 15 with 25 copies across 25 domains), the selector will recommend a more active maintenance policy instead of staying in PROTECT_PERIODIC.

---

## 6. Recommended Periodic Background Job

To keep OGCF metadata fresh, run this periodically (e.g., daily or after every 100 new memories):

```python
from core.ogcf_geometry import OGCFGeometryEngine, OGCFMemoryReviewer
from core.ogcf_signals import OGCFSignalProvider

engine = OGCFGeometryEngine(n_clusters=60, rank_k=8, neighbors=5)
reviewer = OGCFMemoryReviewer(engine)
report = reviewer.review(embeddings, memory_ids, db_path)

# Cache the metadata for the signal provider
provider = OGCFSignalProvider(report)
# ... store report in a JSON file or memory cache ...
```

The cached report can then be passed into `select_with_ogcf()` for every retrieval query.

---

## 7. Next Steps for Full Production

1. **Deduplication preprocessor** — before running OGCF geometry, merge exact duplicates (like the 25 copies of "Cedar Map") to prevent artificial bridge clusters.
2. **LLM contradiction classifier** — replace the rule-based claim extractor with an LLM that labels pairs as: duplicate / paraphrase / outdated / contradiction.
3. **Cluster splitting action** — when `interaction_z >= 3.0`, actually split the bridge cluster by domain tag or semantic subcluster.
4. **Larger retrieval benchmark** — test with 50–100 queries across beverage, location, style, project, weather, and theory topics.
5. **Full-database run** — run OGCF on all 6,955 memories with 80–120 clusters.
6. **Adaptive cluster count** — automatically scale `n_clusters` with database size.

---

## 8. What Was Verified

- ✅ OGCF geometry engine runs end-to-end on real DB samples
- ✅ Bridge cluster detection finds cross-domain duplication
- ✅ Signal provider produces scalar scores compatible with selector
- ✅ Selector features are correctly augmented under bridge overload
- ✅ API handlers are ready for integration into serve.py
- ✅ All integration tests pass

---

*Built by Hermes Agent based on the dev team's OGCF handover report and prior diagnostic test results.*
