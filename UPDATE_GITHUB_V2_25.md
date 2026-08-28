# Upgrade V2.24 to V2.25 — Client Documents

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_25.md
- static/app.css
- templates/client_detail.html
- templates/project_detail.html
- templates/job_detail.html
- templates/backup_restore.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.25.
2. Restore the latest validated V2.24 backup if Render resets.
3. Open **Bob Construction**.
4. Confirm the new **Client Documents** panel appears.
5. Upload one small test PDF or TXT file.
6. Confirm the client page shows filename, size, uploader, timestamp, Download, and (Owner only) Delete.
7. Open **Bob Retail Rollout** and confirm the file appears under **Client Reference Files**.
8. Open **Bob Project Test 2** and confirm the same file appears under **Client Reference Files**.
9. Download it from the job and confirm it opens.
10. Preview the Client Report and confirm the client document is not exposed.
11. Sign in as Operations: confirm upload/download are available on the client, but Delete is not.
12. As Owner, open Backup & Restore and confirm **Client Documents = 1** and Uploaded Files increased.
13. Download a backup, delete the client file, restore the backup, and confirm the file returns.
14. Open Help & Tutorials and search `client documents`.
15. Save a fresh V2.25 backup after validation.
