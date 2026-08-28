# Upgrade V2.18 to V2.18.1 — Job Document Backup Count Fix

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_18_1.md

## After Render deploys

1. Confirm Version 2.18.1.
2. Restore the current V2.18 data only if Render resets during the deploy.
3. Open **Backup & Restore**.
4. Confirm **Job Documents = 1** for the uploaded `old_indeed.pdf` test file.
5. Confirm **Uploaded Files** increases to include that document.
6. Do not delete the test document yet; we still need to finish V2.18 permission/backup validation.
