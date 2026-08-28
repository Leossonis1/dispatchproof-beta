# Upgrade V2.33.2 to V2.34 — Crew Conflict Detection

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_34.md
- static/app.css
- templates/schedule.html
- templates/job_detail.html
- templates/dashboard.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.34.
2. Restore the latest validated V2.33.2 backup only if Render resets.
3. Open Schedule and confirm **Crew Conflicts = 0** with the normal test data.
4. To create a temporary test conflict:
   - Edit **DispatchProof Online Test duplicate**
   - change Installation Date to Aug 31, 2026
   - add **Mike Davis** to Crew / Installers
   - save
5. Return to Schedule.
6. Confirm **Crew Conflicts** shows the affected conflicted jobs and both Aug 31 jobs display a red Mike Davis conflict warning.
7. Click **Crew Conflicts** and confirm only the conflicted jobs remain.
8. Open **Bob Project Test 2** and confirm Field Assignment shows **Crew Conflict Detected**.
9. Open Dashboard and confirm the conflict surfaces in Needs Attention.
10. Resolve the temporary conflict by returning the duplicate to Sep 14, 2026 and removing Mike Davis from that job.
11. Confirm Crew Conflicts returns to 0.
12. Open Help & Tutorials and search `crew conflict`.
13. Save a fresh V2.34 backup after validation.
