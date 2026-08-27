# Upgrade Existing Render Beta to V1.9

Download a fresh backup before deploying.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/dashboard.html
- templates/job_detail.html
- templates/backup_restore.html
- templates/public_arrival_submitted.html
- templates/completed_jobs.html
- templates/public_job_closed.html

Commit and let Render deploy.

After deployment:

1. Confirm the sidebar says Version 1.9.
2. Restore your latest verified backup if Render resets.
3. Use a READY job and submit a successful installer arrival.
4. Dashboard should change the job to ON SITE, not READY.
5. Open the job and confirm **Crew On Site — Installation in Progress**.
6. Click **Mark Job Complete**.
7. The job should disappear from Upcoming Installations.
8. Open **Completed Jobs** in the sidebar.
9. Confirm the completed job appears and its evidence is still viewable.
10. Confirm the old installer-arrival link no longer opens the prior form.
