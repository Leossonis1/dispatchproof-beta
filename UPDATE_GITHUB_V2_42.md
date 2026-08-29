# DispatchProof V2.42 — Field Updates + Daily Progress

## What changed
- Added a job-level **Field Updates & Daily Progress** workspace.
- PMs can create a secure field link for an assigned installer/subcontractor or a manually entered recipient.
- Each request stores the PM note and can be copied directly or generated as an email/outbox preview.
- Field recipients need no DispatchProof account. They can respond to the PM with notes/photos or submit a **Daily Progress Log**.
- Daily Progress captures work date, work completed, optional crew size/hours/issues/notes, and one or more progress photos.
- Progress entries stay ordered by work date in the job record.
- Daily Progress is included automatically in the single-job Client Report; ordinary PM-request responses remain internal.
- Field links can be revoked independently without rotating readiness, arrival, or client-report links.
- Completed jobs close field submissions while preserving all prior field evidence.
- Email Outbox and job Communication History now include Field Update Requests.
- User Workspace Backup/Restore includes field links, progress entries, and their photos; restored links receive fresh secure tokens.

## Database migration
Automatic and additive. V2.42 creates `field_update_links` and `field_progress_entries`. Existing jobs and evidence are unchanged.

## Deploy
Use the patch ZIP on top of V2.41, or deploy the full V2.42 build. No manual database work is required.
