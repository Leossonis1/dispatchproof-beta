# Upgrade V2.37 to V2.38 — User Workspace Backup / Export

V2.38 adds self-service backup/export for Operations users while preserving Owner/Admin-only full-system restore.

## Upload / replace

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_38.md
- templates/my_account.html
- static/app.css

## What changes

### Operations users

Open **My Account → Backup My Workspace** and click **Download My Workspace ZIP**.

The ZIP includes only jobs the current Operations user can access at download time:

- personal jobs owned by that PM;
- team jobs currently shared with that PM;
- readiness and mobilization history;
- notes;
- Email Outbox history tied to those jobs;
- job activity;
- crew assignments;
- job documents; and
- readiness / arrival evidence photos.

It also includes JSON plus CSV copies of the scoped records and an index of included/missing files.

### Owner / Administrator

The existing **Backup & Restore** page remains unchanged and remains the only place that can create/restore the complete company database backup.

Operations users cannot restore a ZIP over the shared system.

## Privacy

The user export reuses the V2.37 job access predicate. It does not include another PM's private jobs, even when those PMs work for the same company.

A team job is included only when the signed-in PM currently has team access and that team's sharing toggle is ON.

## Database migration

None. V2.38 does not add or change database tables.

## Recommended validation

1. Confirm the footer / Health endpoint reports **Version 2.38**.
2. Sign in as an Operations test user.
3. Open **My Account** and confirm **Backup My Workspace** appears.
4. Confirm the job/file counts match that user's accessible workspace.
5. Download the ZIP and confirm it contains `workspace_manifest.json`, `workspace_data.json`, `data/`, and `files/` when files exist.
6. With PM1 and PM2, confirm PM1's export does not contain PM2's personal job.
7. Put both PMs on a shared team and confirm an accessible Team job appears in both exports while sharing is ON.
8. Turn team sharing OFF and confirm the other PM's Team job disappears from the export.
9. Sign in as Owner/Admin and confirm **Backup & Restore** is still available and system restore still works only for Owner/Admin.
