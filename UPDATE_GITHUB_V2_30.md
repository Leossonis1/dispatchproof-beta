# Upgrade V2.29 to V2.30 — Crew Assignment

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_30.md
- static/app.css
- templates/new_job.html
- templates/edit_job.html
- templates/job_detail.html
- templates/schedule.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.30.
2. Restore the latest validated V2.29 backup only if Render resets.
3. Open **Bob Project Test 2** and click **Edit Job Details**.
4. Confirm a new **Crew Assignment** section appears.
5. Enter test values:
   - Crew Lead: Mike Davis
   - Planned Crew Size: 3
   - Crew / Installers: Mike Davis, Chris Smith, Jordan Lee
6. Save.
7. Confirm the Job Detail shows the new internal **Field Assignment** panel with those values.
8. Open **Schedule** and confirm Bob Project Test 2 shows Lead / Crew / Assigned information.
9. Search Schedule for `Mike Davis` and confirm Bob Project Test 2 remains.
10. Export Schedule CSV and confirm the new crew columns are present.
11. Preview the single-job Client Report and confirm crew assignment does not appear.
12. Sign in as Operations and confirm crew assignment is visible internally and can be edited on an active job.
13. Open Help & Tutorials and search `crew assignment`.
14. Save a fresh V2.30 backup after validation.
