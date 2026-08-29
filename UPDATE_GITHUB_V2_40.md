# DispatchProof V2.40 — Operator Workspace Restore

## What changed
- Operators can now upload their own **My Workspace** ZIP from My Account.
- Restore is a two-step **Preview → Restore** workflow.
- Existing live jobs are never overwritten.
- Jobs are restored as private personal jobs owned by the signed-in Operator.
- Team jobs from a backup are restored as personal copies, never written back over a live Team job.
- Clients, Projects, and Crew are reused by name when they already exist and created only when missing.
- Readiness history, mobilization history, notes, crew assignments, job documents, and site-evidence files are restored when available.
- Old email-delivery and activity-log rows are intentionally not replayed.
- Duplicate protection remembers restored source jobs and skips them on later imports.
- Workspace restore is limited to ZIPs exported for the currently signed-in username.
- Added ZIP/path/expanded-size safety checks and fresh filenames/tokens during restore.

## Database
One additive table is created automatically: `workspace_restore_items`. No reset is required.
