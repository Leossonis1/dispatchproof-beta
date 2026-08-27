# Upgrade Existing Render Beta to V1.8

KEEP YOUR CURRENT BACKUP ZIP.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/job_detail.html
- templates/public_arrival.html
- templates/public_arrival_submitted.html
- templates/public_arrival_unavailable.html

Commit and let Render deploy.

After deployment:

1. Confirm the sidebar says Version 1.8.
2. If Render reset the data, restore your latest verified backup.
3. Open a READY job.
4. Confirm the new **Installer Arrival Link** card appears.
5. Copy the installer link.
6. Open it on a phone/incognito browser with no admin session.
7. Confirm the arrival form opens without login.
8. Submit Site Ready once and verify the job page locks the arrival.
9. Start a new mobilization and confirm the old installer link no longer controls the new attempt.
10. For the next attempt, test Site Not Ready with two phone photos, Crew Affected, and Hours Lost.
