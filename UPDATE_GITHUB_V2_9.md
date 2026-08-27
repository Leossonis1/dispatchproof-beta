# Upgrade V2.8 to V2.9 — Dashboard Search & Filters

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_9.md
- static/app.css
- templates/dashboard.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.9.
2. Restore the latest validated V2.8 backup if Render resets.
3. Open Dashboard.
4. Confirm **Search & Filter** appears below the status tiles.
5. Search for part of an existing job name and click **Apply Filters**.
6. Confirm only the matching active job appears.
7. Click **Clear All**.
8. Choose an existing Client and confirm the Project dropdown only shows that client's projects.
9. Choose a Status and confirm the matching job count/list is correct.
10. Click one of the status summary tiles while another filter is active and confirm the other filters are preserved.
11. Open Help & Tutorials and search for `dashboard`; confirm **Find a Job on the Dashboard** appears.
12. Save a fresh V2.9 live backup after validation.
