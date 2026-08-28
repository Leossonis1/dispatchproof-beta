# Upgrade V2.27 to V2.28 — Schedule Board

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_28.md
- static/app.css
- templates/base.html
- templates/help.html
- templates/schedule.html

## After Render deploys

1. Confirm Version 2.28.
2. Restore the latest validated V2.27 backup only if Render resets.
3. Click **Schedule** in the sidebar.
4. With the current test data, confirm the active counts show:
   - Overdue: 0
   - Today: 0
   - Next 7 Days: 1
   - Later: 1
5. Confirm the default board shows the two active test jobs grouped by their install dates.
6. Click **Next 7 Days** and confirm only **Bob Project Test 2** remains.
7. Click **Clear All**.
8. Turn on **Include Completed** and confirm the completed DispatchProof Online Test appears.
9. Filter Client = **Bob Construction** and confirm the related jobs remain.
10. Click **Open Job →** and confirm navigation reaches the correct installation.
11. Sign in as Operations and confirm Schedule is available.
12. Open Help & Tutorials and search `schedule board`.
13. Save a fresh V2.28 backup after validation.
