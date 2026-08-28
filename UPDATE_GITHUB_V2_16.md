# Upgrade V2.15.1 to V2.16 — CSV Export

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_16.md
- static/app.css
- templates/dashboard.html
- templates/completed_jobs.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.16.
2. Restore the latest validated V2.15.1 backup if Render resets.
3. Open Dashboard and confirm **Export CSV** appears in Search & Filter.
4. Filter to **Next 7 Days** and click Export CSV.
5. Open the downloaded CSV and confirm it contains only the matching active job.
6. Clear filters and export again; confirm both active jobs are included.
7. Open Completed Jobs and confirm **Export CSV** appears there too.
8. If a completed test job exists, export it and confirm the completed record is present.
9. Open Help & Tutorials and search `export`; confirm **Export Jobs to CSV** appears.
10. Save a fresh V2.16 backup after validation.
