# Upgrade V2.14 to V2.14.1 — Eastern Time Display Fix

Upload/replace:

- app.py
- README.md
- VERSION.txt
- UPDATE_GITHUB_V2_14_1.md

## After Render deploys

1. Confirm Version 2.14.1.
2. Restore the latest V2.14 backup if Render resets.
3. Open **Backup & Restore**.
4. Confirm **Last Backup** displays the correct Eastern local time and shows `EDT` during daylight saving time or `EST` during standard time.
5. Open a Job Activity section and confirm its timestamps are also corrected.
6. Save a fresh V2.14.1 backup after validation.

No database migration is required.
