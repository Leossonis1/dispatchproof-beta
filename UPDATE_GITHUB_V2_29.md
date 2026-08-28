# Upgrade V2.28 to V2.29 — Schedule Export

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_29.md
- static/app.css
- templates/schedule.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.29.
2. Restore the latest validated V2.28 backup only if Render resets.
3. Open **Schedule**.
4. Confirm **Export CSV** and **Print / Save PDF** appear beside **+ New Job**.
5. Leave the default active Schedule view and click **Export CSV**.
6. Open the CSV and confirm it contains the two active test installs.
7. Back on Schedule, click **Next 7 Days**, then **Export CSV** again.
8. Confirm that CSV contains only **Bob Project Test 2**.
9. Click **Clear All**, turn on **Include Completed**, and click **Print / Save PDF**.
10. Confirm the browser print preview shows the three installs but not the sidebar/filter controls.
11. Sign in as Operations and confirm both export actions remain available.
12. Open Help & Tutorials and search `schedule export`.
13. Save a fresh V2.29 backup after validation.
