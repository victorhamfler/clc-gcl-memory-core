# User Preference Update

This document restates Mira's current preferences for Git commits and GitHub uploads.

Current Git commit preference:
- Mira wants commits made from Windows PowerShell.
- Mira does not want Git commits made from WSL.
- WSL may be used for model files, embedding runtimes, and Linux tools, but repository commits should remain Windows-side.

Current GitHub upload preference:
- GitHub uploads happen only when Mira explicitly asks.
- The assistant must not push automatically after documentation edits.
- The assistant should keep changes local and report the local file list until Mira asks for a push.

This v2 preference update agrees with the safe parts of v1 but supersedes any old rule that allowed automatic pushes.

