# Project Memory

The synthetic project is called Atlas Loom.

Atlas Loom is a local AI memory testing project. It has three goals:
- Build a memory core that stores agent knowledge as chunks with embeddings.
- Evaluate whether feedback can improve retrieval quality.
- Test how memory behaves when instructions change over time.

Known project decisions:
- Experiments should use temporary databases first.
- The active baseline database should not be modified during evaluation unless the user asks.
- Feedback labels include useful, excellent, wrong, stale, wrong_domain, and missing_source.
- Memory retrieval should show source, domain, score, feedback score, and reliability signals.

Current baseline:
- The first stable memory corpus is version v1.
- A later version v2 will intentionally change some instructions.
- The system should be able to retrieve both old and new knowledge, but newer corrections should become preferred after feedback.

