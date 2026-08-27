# Upgrade Existing Render Beta to V2.7

You have a verified V2.6 code + live-data checkpoint.

Upload/replace:

- app.py
- README.md
- VERSION.txt
- static/app.css
- templates/base.html
- templates/help.html

After deployment:

1. Confirm Version 2.7.
2. Restore the latest V2.6 backup if Render resets.
3. Confirm **Help & Tutorials** appears in the sidebar.
4. Open Help & Tutorials as Owner/admin.
5. Confirm all tutorial sections appear, including Admin Tools and Backup & Restore.
6. Search for `combined` and confirm only combined-report tutorials remain.
7. Search for `backup` and confirm the backup tutorials remain.
8. Sign in as an Operations user.
9. Open Help & Tutorials and confirm Admin Tools / Backup & Restore tutorials are hidden.
10. Search for `arrival` and confirm the installer-arrival tutorials appear.
11. Save a fresh V2.7 live-data backup after validation.
