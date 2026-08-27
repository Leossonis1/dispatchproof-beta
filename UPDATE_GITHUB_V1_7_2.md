# Upgrade Existing Render Beta to V1.7.2

You already have a backup saved before this deployment.

Upload/replace these paths in the existing `dispatchproof-beta` GitHub repository:

- `app.py`
- `README.md`
- `VERSION.txt`
- `static/app.css`
- `templates/login.html`
- `templates/backup_restore.html`
- `templates/arrival.html`

Commit the changes. Render should auto-deploy.

After deployment:

1. Confirm the sidebar says Version 1.7.2.
2. If the dashboard resets, restore your most recent backup.
3. Sign out and verify the login page has **Stay signed in on this device**.
4. Open Backup & Restore and verify the record counts match your current data.
5. Record a Site Not Ready arrival and verify Crew Affected + Hours Lost cannot be left blank.
