# Task Playbook

NovaDesk should be able to perform the following task families.

1. Memory design tasks
   - Explain how a memory system stores and retrieves information.
   - Design experiments that test recall, adaptation, contradiction handling, and source reliability.
   - Compare baseline retrieval with feedback-adjusted retrieval.

2. Local development tasks
   - Inspect files before editing.
   - Use temporary databases for experiments.
   - Restart local servers after runtime changes.
   - Report exact commands and test outcomes.

3. Project continuity tasks
   - Remember the active database.
   - Remember whether changes were local-only or pushed to GitHub.
   - Track open next steps.
   - Identify which files changed and why.

4. Agent support tasks
   - Maintain a compact user preference profile.
   - Answer questions about the user's current projects.
   - Detect when a new instruction supersedes an older instruction.
   - Ask for confirmation only when a safe assumption is not possible.

Success means NovaDesk gives useful project-aware answers without needing the user to restate the same context every time.

