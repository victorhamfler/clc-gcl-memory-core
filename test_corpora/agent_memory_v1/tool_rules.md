# Tool Rules

NovaDesk should follow these tool rules.

Git and GitHub:
- Commit from Windows, not WSL.
- Do not push to GitHub unless the user explicitly says to upload, push, or publish.
- Keep local changes uncommitted until the user asks for a commit.

Filesystem:
- Read relevant files before editing.
- Use explicit absolute paths in reports.
- Avoid deleting or overwriting user data.
- Use temporary databases for risky memory tests.

Server behavior:
- If the local memory API changes, restart it and health-check it.
- Report the local URL and process id when a server is running.
- Do not leave hidden assumptions about which database the server uses.

Experiment behavior:
- Compare before and after metrics.
- Keep the active database unchanged during experiments unless instructed.
- Save synthetic test corpora as plain text documents so their chunks can be inspected.

