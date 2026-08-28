# Upgrade V2.25 to V2.26 — Document Center

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_26.md
- static/app.css
- templates/base.html
- templates/help.html
- templates/documents.html

## After Render deploys

1. Confirm Version 2.26.
2. Restore the latest validated V2.25 backup if Render resets.
3. Click **Documents** in the sidebar.
4. With the current test data, confirm the page shows at least one Client Document, one Project Document, and one Job Document.
5. Click the **Client** summary card and confirm only client files remain.
6. Click **Clear All**.
7. Search `old_indeed` and confirm matching files appear across their different scopes.
8. Filter Client = **Bob Construction** and confirm its related files remain.
9. Click **Download** on one result and confirm it opens.
10. Click **Open Client →**, **Open Project →**, or **Open Job →** on a result and confirm it jumps to the correct parent section.
11. Sign in as Operations and confirm Documents remains available.
12. Preview a client-facing report and confirm Document Center/internal files are not exposed.
13. Open Help & Tutorials and search `document center`.
14. Save a fresh V2.26 backup after validation.
