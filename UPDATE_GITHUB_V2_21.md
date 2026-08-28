# Upgrade V2.20 to V2.21 — Priority Quick Actions

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_21.md
- static/app.css
- templates/dashboard.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.21.
2. Restore the latest validated V2.20 backup if Render resets.
3. Open Dashboard.
4. Confirm the No Response item in **Needs Attention** now shows **Generate Reminder** and **Open Job →**.
5. Click **Generate Reminder**.
6. Confirm DispatchProof returns to Dashboard with the Outbox Mode confirmation.
7. Open Email Outbox and confirm a new REMINDER entry exists for the correct job/contact.
8. Open the job and confirm Job Activity contains **Readiness Reminder Generated**.
9. Open Help & Tutorials and search `attention`; confirm the tutorial mentions **Generate Reminder**.
10. Save a fresh V2.21 backup after validation.
