# Upgrade V2.31 to V2.32 — Crew Coverage

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_32.md
- static/app.css
- templates/schedule.html
- templates/dashboard.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.32.
2. Restore the latest validated V2.31 backup only if Render resets.
3. Open **Schedule**.
4. Confirm new **Crew Assigned** and **Crew Unassigned** cards appear.
5. With the current test data, Bob Project Test 2 should count as Assigned and DispatchProof Online Test duplicate should count as Unassigned.
6. Click **Crew Unassigned** and confirm only the unassigned active install remains.
7. Click **Clear All**.
8. Set **Crew Coverage = Assigned** and Apply Filters; confirm only Bob Project Test 2 remains.
9. Export CSV from the Assigned view and confirm it downloads.
10. Open **Dashboard** and confirm near-term unassigned jobs surface in Needs Attention or show a **Crew not assigned** warning when another attention reason is primary.
11. Search Dashboard for `Mike Davis` and confirm Bob Project Test 2 is found.
12. Open Help & Tutorials and search `crew coverage`.
13. Save a fresh V2.32 backup after validation.
