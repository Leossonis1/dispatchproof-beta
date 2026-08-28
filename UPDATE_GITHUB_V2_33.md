# Upgrade V2.32 to V2.33 — Crew Directory

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_33.md
- static/app.css
- templates/base.html
- templates/new_job.html
- templates/edit_job.html
- templates/_crew_picker.html
- templates/crew_directory.html
- templates/edit_crew_member.html
- templates/backup_restore.html
- templates/help.html

## After Render deploys

1. Confirm Version 2.33.
2. Restore the latest validated V2.32 backup if Render resets.
3. Open **Crew**.
4. Existing V2.32 crew names should automatically appear as reusable records.
5. With the current test data, expect Mike Davis, Jordan Lee, and Chris Smith to migrate into Crew Directory.
6. Open **Bob Project Test 2 → Edit Crew Assignment**.
7. Confirm the existing people are checked and Mike Davis is selected as Crew Lead.
8. Return without changing anything.
9. Add one temporary test crew member in Crew Directory.
10. Open **DispatchProof Online Test duplicate → Edit Crew Assignment** and select that test member.
11. Save and confirm Schedule / crew search still work.
12. Deactivate the test crew member and confirm the existing job assignment remains, while the person no longer appears for new jobs.
13. Open **Backup & Restore** and confirm Crew Member / Crew Assignment counts appear.
14. Open Help & Tutorials and search `crew directory`.
15. Save a fresh V2.33 backup after validation.
