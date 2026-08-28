# Upgrade V2.14.1 to V2.15 — Schedule Alerts & Date Filters

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_15.md
- static/app.css
- templates/dashboard.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.15.
2. Restore the latest validated V2.14.1 backup if Render resets.
3. Open Dashboard.
4. Confirm Overdue / Today / Next 7 Days / Later schedule chips appear.
5. Confirm the schedule counts match the active installation dates.
6. Click **Next 7 Days** and confirm only jobs in that date window remain.
7. Confirm the Schedule dropdown also shows **Next 7 Days** selected.
8. Combine the schedule filter with Client or Status and confirm both remain active.
9. Confirm Next 7 Days / Today / Overdue jobs show a small alert under Install Date.
10. Open Help & Tutorials and search `schedule`; confirm **Use Schedule Alerts** appears.
11. Save a fresh V2.15 backup after validation.
