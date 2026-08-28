# Upgrade V2.35.1 to V2.36 — Crew Staffing Gaps

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_36.md
- static/app.css
- templates/schedule.html
- templates/job_detail.html
- templates/dashboard.html
- templates/help.html

## Expected first test with current validated data

`Bob Project Test 2` currently has:

- Planned Crew Size: 4
- Named assigned crew: Mike Davis, Jordan Lee, Chris Smith
- Expected staffing gap: 1

After Render deploys:

1. Confirm **Version 2.36**.
2. Restore the latest validated V2.35.1 backup only if Render resets the data.
3. Open **Schedule**.
4. Confirm **Staffing Gaps = 1**.
5. Confirm `Bob Project Test 2` shows Planned 4 · Assigned 3 · 1 Crew Member Needed.
6. Click **Staffing Gaps** and confirm only the short-staffed job remains.
7. Open `Bob Project Test 2` and confirm Field Assignment shows **Staffing Gap**.
8. Open Dashboard and confirm Needs Attention includes the staffing-gap warning and summary.
9. Temporarily change Planned Crew Size from 4 to 3 and save.
10. Confirm Staffing Gaps returns to 0.
11. Restore Planned Crew Size to 4 to return the test job to its original data.
12. Open Help & Tutorials and search `staffing gap`.
13. Save a fresh V2.36 backup after validation.
