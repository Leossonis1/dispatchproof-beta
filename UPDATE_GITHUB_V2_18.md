# Upgrade V2.17 to V2.18 — Job Documents

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_18.md
- static/app.css
- templates/job_detail.html
- templates/backup_restore.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.18.
2. Restore the latest validated V2.17 backup if Render resets.
3. Open a test installation and scroll to **Job Documents**.
4. Upload a small supported test file.
5. Confirm filename, size, uploader, and Eastern timestamp appear.
6. Click **Download** and confirm the file downloads.
7. Confirm **Job Document Uploaded** appears in Job Activity.
8. Confirm the file does not appear in public/client reports.
9. Sign in as Operations: Upload/Download should work, Delete should not appear.
10. Sign back in as Owner/Admin: Delete should appear.
11. Open Backup & Restore and confirm **Job Documents** count appears.
12. Search Help & Tutorials for `documents` and confirm **Attach Job Documents** appears.
13. Save a fresh V2.18 backup after validation.
