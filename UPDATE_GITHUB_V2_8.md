# Upgrade V2.7.1 to V2.8 — Internal Job Notes

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_8.md
- static/app.css
- templates/job_detail.html
- templates/help.html
- templates/backup_restore.html

## After Render deploys

1. Confirm the sidebar/footer shows Version 2.8.
2. Restore the latest validated V2.7.1 backup if Render resets.
3. Open one existing job.
4. Scroll to **Office Notes**.
5. Add a short test note.
6. Confirm the note shows your signed-in name/role and timestamp.
7. Refresh the job and confirm the note remains.
8. Open that job's public Client Report and confirm the internal note is NOT visible.
9. Open a Combined Client Report containing that job and confirm the internal note is NOT visible.
10. Open Help & Tutorials and search for `note`; confirm **Add an Internal Job Note** appears.
11. As Owner/Admin, open Backup & Restore and confirm **Internal Job Notes** shows the expected count.
12. Save a fresh V2.8 live backup after validation.
