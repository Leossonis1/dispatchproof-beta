# Upgrade V2.21 to V2.22 — Reminder History & Repeat Guard

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_22.md
- static/app.css
- templates/dashboard.html
- templates/readiness_request.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.22.
2. Restore the latest validated V2.21 backup if Render resets.
3. Open Dashboard.
4. Bob Project Test 2 should show **1 reminder generated**, its latest EDT timestamp/status, and **Generate Another Reminder**.
5. Click **Generate Another Reminder** and confirm the repeat-reminder warning appears.
6. Cancel the warning first; confirm no new reminder is created.
7. Click again, confirm the warning, and generate the second reminder.
8. Confirm the Dashboard history becomes **2 reminders generated**.
9. Open Readiness Request for the job and confirm **Reminder History** shows the same count/latest activity.
10. Open Help & Tutorials and search `attention`; confirm repeat-reminder guidance is present.
11. Save a fresh V2.22 backup after validation.
