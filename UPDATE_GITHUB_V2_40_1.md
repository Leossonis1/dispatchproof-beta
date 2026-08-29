# DispatchProof V2.40.1 — Workspace Setup Backup / Restore Fix

- Operator workspace ZIPs now include shared Clients, Projects, Crew, crew unavailability, Client documents, and Project documents in addition to authorized jobs and job files.
- Restore preview now considers missing setup records, not only jobs, when deciding whether Restore My Workspace is available.
- Zero-job backups created in V2.40 are clearly identified as older archives that did not contain standalone setup data.
- Shared setup restore is additive only: existing Clients, Projects, Crew, and equivalent setup documents are reused/skipped and never overwritten.
- Another PM's private jobs remain excluded.
- Team jobs still restore as private personal copies.
- Full-system database restore remains Owner/Administrator-only.
