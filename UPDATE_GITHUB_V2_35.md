# Upgrade V2.34 to V2.35 — Crew Availability

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_35.md
- static/app.css
- templates/crew_directory.html
- templates/edit_crew_member.html
- templates/schedule.html
- templates/job_detail.html
- templates/dashboard.html
- templates/backup_restore.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.35.
2. Restore the latest validated V2.34 backup only if Render resets.
3. Open **Crew → Mike Davis**.
4. Under **Crew Availability**, add a temporary unavailable range that includes **Aug 31, 2026**. Use reason **PTO**.
5. Confirm the availability record appears on Mike's profile.
6. Open **Bob Project Test 2** and confirm **Crew Availability Warning** appears for Mike Davis.
7. Open **Schedule** and confirm **Crew Unavailable = 1** and Bob Project Test 2 shows the purple availability warning.
8. Click **Crew Unavailable** and confirm only the affected job is shown.
9. Open **Dashboard** and confirm Needs Attention shows the availability issue and the summary says **1 crew availability issue detected**.
10. Return to **Mike Davis → Crew Availability** and remove the temporary PTO record.
11. Confirm Schedule returns to **Crew Unavailable = 0** and the warnings clear.
12. Open **Backup & Restore** and confirm **Crew Availability Records = 0** after removing the temporary test record.
13. Open **Help & Tutorials** and search `crew availability`; confirm **Manage Crew Availability** appears.
14. Download a fresh V2.35 Backup ZIP after validation.
