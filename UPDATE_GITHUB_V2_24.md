# Upgrade V2.23 to V2.24 — Project Documents

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_24.md
- static/app.css
- templates/project_detail.html
- templates/job_detail.html
- templates/backup_restore.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.24.
2. Restore the latest validated V2.23 backup if Render resets.
3. Open **Bob Retail Rollout**.
4. Confirm the new **Project Documents** panel appears.
5. Upload one small test PDF or TXT file.
6. Confirm the project page shows filename, size, uploader, timestamp, Download, and (Owner only) Delete.
7. Open **Bob Project Test 2** and confirm the same file appears under **Project Reference Files**.
8. Download it from the job and confirm it opens.
9. Preview the Client Report and confirm the project document is not exposed.
10. Sign in as Operations: confirm upload/download are available on the project, but Delete is not.
11. As Owner, open Backup & Restore and confirm **Project Documents = 1** and Uploaded Files increased.
12. Download a backup, delete the project file, restore the backup, and confirm the file returns.
13. Open Help & Tutorials and search `project documents`.
14. Save a fresh V2.24 backup after validation.
