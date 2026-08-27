# V1.8.1 Installer Copy Link Fix

Upload/replace:

- app.py
- VERSION.txt
- README.md
- templates/job_detail.html

Commit and let Render redeploy.

After deployment:
1. Confirm Version 1.8.1.
2. Restore your backup if Render reset the database.
3. Open the READY job.
4. Click Copy Installer Link.
5. The button should briefly change to "Copied!".
6. Paste into a new browser tab or text message to verify the complete `/a/...` URL copied.
