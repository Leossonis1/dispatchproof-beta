# Upgrade V2.22 to V2.23 — Job Communication History

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_23.md
- static/app.css
- templates/job_detail.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.23.
2. Restore the latest validated V2.22 backup if Render resets.
3. Open **Bob Project Test 2**.
4. Confirm **Communication History** appears below Installation Report.
5. With the current test data, confirm the job shows the two Reminder entries generated during V2.22 testing.
6. Confirm each row shows recipient, OUTBOX status, Eastern timestamp, and subject.
7. Click **View Preview →** on the newest reminder and confirm the Email Outbox detail opens for that exact message.
8. Return to the job and confirm the history does not show unrelated combined client/project reports.
9. Sign in as Operations and confirm Communication History and View Preview remain available.
10. Open Help & Tutorials and search `communication`; confirm **Review Job Communication History** appears.
11. Save a fresh V2.23 backup after validation.
