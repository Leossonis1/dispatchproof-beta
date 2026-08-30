# DispatchProof V2.46.11 — Integration Positioning

## Purpose
Launch-readiness messaging/scaffolding only. No live Quickbase connector is enabled.

## What changed
- Added an Owner/Admin-only **Integrations** page under Settings.
- Clarified the core product role: **Your back office tracks the job. DispatchProof runs it.**
- Shows Quickbase as **Private Beta Planned**, not as a production-ready integration.
- Documents the intended handoff: job essentials in → field execution in DispatchProof → completion signal out.
- Explicitly states that Quickbase or any external back-office system is optional.
- Added Help & Tutorials coverage for Integrations.
- Added a third-party/non-affiliation note.

## Not included
- No API tokens or credential storage.
- No Quickbase API calls.
- No database migration.
- No changes to jobs, permissions, crew conflicts, Training, mobile behavior, or field workflows.

## Deploy
Copy `app.py`, `static/app.css`, `templates/base.html`, `templates/help.html`, `templates/integrations.html`, and `VERSION.txt` into the existing repository, commit, push, and deploy normally.
