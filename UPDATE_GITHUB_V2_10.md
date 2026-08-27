# Upgrade V2.9 to V2.10 — Duplicate Job

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_10.md
- static/app.css
- templates/new_job.html
- templates/job_detail.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.10.
2. Restore the latest validated V2.9 backup if Render resets.
3. Open an existing job.
4. Confirm **Duplicate Job** appears at the top.
5. Click Duplicate Job.
6. Confirm Client, Project, Job Name, Project / Site, Contact, Checklist, and Reminder settings are prefilled.
7. Confirm Installation Date is blank.
8. Enter a new test Job Name / Installation Date and create the duplicate.
9. Confirm the new job starts at **NO RESPONSE** with a fresh readiness workflow.
10. Open Job Activity and confirm **Job Created** and **Job Duplicated** appear.
11. Confirm old readiness responses/photos, arrival evidence, and Office Notes are NOT present on the duplicate.
12. Open Help & Tutorials and search `duplicate`; confirm **Duplicate a Job** appears.
13. Save a fresh V2.10 backup after validation.
