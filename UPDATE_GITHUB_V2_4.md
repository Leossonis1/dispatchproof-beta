# Upgrade Existing Render Beta to V2.4

You have a verified V2.3 code + live-data checkpoint.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/job_detail.html
- templates/email_outbox.html
- templates/email_outbox_detail.html
- templates/client_report.html
- templates/public_client_report.html

Commit and let Render deploy.

After deployment:

1. Confirm Version 2.4.
2. Restore the latest V2.3 backup if Render resets.
3. Open the existing test job.
4. Confirm **Installation Report** appears on Job Detail.
5. Open **Client Report & Email**.
6. Open the secure Client Report in a private/incognito browser and confirm no login is required.
7. Confirm the report shows only that job: readiness, photos, arrival result, and Job Activity.
8. Generate a client-report email. In Outbox Mode confirm it appears as **Client Report** in Email Outbox.
9. Open the Outbox email preview and confirm the View Installation Report link works.
10. Rotate the report link.
11. Confirm the old report URL returns 404 and the new URL works.
12. Sign in as an Operations user and confirm they can generate/share the job Client Report.
13. Save a fresh V2.4 live-data backup after validation.
