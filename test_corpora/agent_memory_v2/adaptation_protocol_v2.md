# Adaptation Protocol

This document answers how the memory system should test adaptation after instructions change.

The memory system should test adaptation with this workflow:
1. Build a temporary memory database from the v1 documents.
2. Run recall questions about agent identity, user preferences, tool rules, and project priorities.
3. Import the v2 update documents into the same temporary database.
4. Re-run the same recall questions and compare v1 terms with v2 terms.
5. Mark v2 memories useful when they represent the current instruction.
6. Mark old conflicting v1 memories stale when they are historical but no longer current.
7. Re-run retrieval and check whether v2 memories become preferred while old v1 memories remain available as history.

The expected result is not deletion. The expected result is adaptive ranking: current v2 knowledge should be retrieved above stale v1 knowledge for corrected facts.

Adaptation should be measured with term score, source score, conflict preference, and whether stale memories move down after feedback.

