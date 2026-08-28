# Upgrade V2.11 to V2.12 — Completed Jobs Search & Filters

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_12.md
- static/app.css
- templates/completed_jobs.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.12.
2. Restore the latest validated V2.11 backup if Render resets.
3. Open **Completed Jobs**.
4. Confirm **Search Completed Jobs** appears above the history table.
5. If there are no completed test jobs, mark one safe test job complete first.
6. Search for part of that completed Job Name and click **Apply Filters**.
7. Confirm only the matching completed job appears.
8. Click **Clear All**.
9. Choose the job's Client and confirm the result remains visible.
10. Confirm the Project dropdown only shows projects belonging to the selected Client.
11. Open Help & Tutorials and search `completed`; confirm **Find a Completed Job** appears.
12. Save a fresh V2.12 backup after validation.
