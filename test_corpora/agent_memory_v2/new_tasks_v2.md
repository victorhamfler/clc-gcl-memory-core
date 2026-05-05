# New Tasks For LoomGuide

LoomGuide should now support adaptation experiments.

Adaptation experiment tasks:
- Build a temporary memory database from v1 documents.
- Evaluate recall for agent identity, user preferences, tool rules, and project priorities.
- Import v2 update documents.
- Re-evaluate the same questions.
- Add feedback marking v2 answers useful and v1 answers stale when they conflict.
- Check whether v2 memories become preferred.

Expected adaptation behavior:
- For stable facts, v1 and v2 should agree.
- For corrected facts, v2 should be preferred.
- Old conflicting v1 memories should not be deleted automatically.
- Old conflicting v1 memories should be downranked after stale or wrong feedback.

