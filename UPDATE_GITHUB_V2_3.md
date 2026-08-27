# Upgrade Existing Render Beta to V2.3

You already saved a verified V2.2 code + data checkpoint.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/backup_restore.html
- templates/job_detail.html
- templates/activity_log.html

Commit and let Render deploy.

After deployment:

1. Confirm Version 2.3.
2. Restore the V2.2 backup if Render resets the data.
3. Sign in as Owner/admin.
4. Confirm **Activity Log** appears in the admin sidebar.
5. Open Activity Log and confirm the V2.3 "Activity Log Enabled" system event exists.
6. Create a small test job.
7. Open that job and confirm **Job Activity** shows "Job Created."
8. Generate a readiness email/outbox entry and confirm it appears in Job Activity.
9. Submit the public readiness form and confirm the site contact is named in the activity.
10. Test an installer arrival and confirm the arrival activity appears.
11. Sign in as an Operations user and confirm the global Activity Log link is hidden.
12. Confirm Operations can still see the Job Activity timeline for jobs they can access.
13. Save a fresh V2.3 backup after validation.
