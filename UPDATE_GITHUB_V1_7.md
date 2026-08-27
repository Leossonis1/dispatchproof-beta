# Upgrade Existing Render Beta to V1.7

Upload/replace these paths in the existing `dispatchproof-beta` GitHub repository:

- `app.py`
- `render.yaml`
- `README.md`
- `VERSION.txt`
- `static/app.css`
- `static/favicon.svg`
- `templates/base.html`
- `templates/login.html`
- `templates/backup_restore.html`

Commit the changes. Render should auto-deploy.

After V1.7 goes live:
1. Sign in.
2. Sidebar should show Version 1.7.
3. Open Backup & Restore.
4. Download a backup ZIP after creating test data.
5. On the next Render reset/deploy, restore that ZIP if needed.
