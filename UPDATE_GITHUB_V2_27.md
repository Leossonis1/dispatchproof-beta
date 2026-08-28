# Upgrade V2.26.1 to V2.27 — Document Center Quick Upload

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_27.md
- static/app.css
- templates/documents.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.27.
2. Restore the latest validated V2.26.1 backup only if Render resets.
3. Open **Documents**.
4. Confirm **Quick Upload** appears above Search & Filter.
5. Choose **Client Document** and confirm only the Client selector appears.
6. Choose **Project Document** and confirm only the Project selector appears.
7. Choose **Job Document** and confirm only the Job selector appears.
8. Upload a small test TXT or PDF as a **Job Document** to **Bob Project Test 2**.
9. Confirm Document Center returns filtered to Job Documents and the new file appears.
10. Click **Open Job →** and confirm the file is in that job's Job Documents section.
11. As Operations, confirm Quick Upload works but Delete is still unavailable on parent document pages.
12. Open Help & Tutorials and search `quick upload`.
13. Save a fresh V2.27 backup after validation.
