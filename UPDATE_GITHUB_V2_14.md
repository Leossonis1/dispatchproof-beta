# Upgrade V2.13 to V2.14 — Backup Reminder

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_14.md
- static/app.css
- templates/dashboard.html
- templates/backup_restore.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.14.
2. Restore the latest validated V2.13 backup if Render resets.
3. Open **Backup & Restore** as Owner/Admin.
4. Confirm the new **Backup Status** card appears and shows a Last Backup date.
5. Return to Dashboard. Because the restored backup is recent, no stale-backup banner should be visible.
6. Click **Backup & Restore → Download Backup ZIP**.
7. Return to Backup & Restore and confirm Last Backup updates to the new time.
8. Open Help & Tutorials and search `backup reminder`; confirm **Respond to a Backup Reminder** appears.
9. Sign in as Operations and confirm no backup reminder/admin backup controls are shown.
10. Save the fresh V2.14 ZIP as the validated checkpoint.

## Reminder thresholds

- Under 3 days: current / no Dashboard warning
- 3–6 days: Backup recommended
- 7+ days: Backup overdue
